"""Tool Catalog - Registry of all available tools.

The catalog is responsible for:
1. Registering tools with their definitions and executors
2. Auto-discovering tools from domain modules
3. Generating OpenAI-compatible function schemas
4. Providing executors for tool execution
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from typing import Any

import structlog

from me4brain.engine.types import ToolDefinition

logger = structlog.get_logger(__name__)


class ToolCatalog:
    """Registry of all tools available for the LLM.

    Generates OpenAI-compatible function schemas automatically.

    Example:
        catalog = ToolCatalog()
        await catalog.discover_from_domains()

        # Get schemas for LLM
        schemas = catalog.get_function_schemas()

        # Get executor
        executor = catalog.get_executor("coingecko_price")
        result = await executor(ids="bitcoin")
    """

    def __init__(self) -> None:
        """Initialize empty catalog."""
        self._tools: dict[str, ToolDefinition] = {}
        self._executors: dict[str, Callable[..., Any]] = {}
        self._initialized = False

    def register(
        self,
        tool: ToolDefinition,
        executor: Callable[..., Any],
    ) -> None:
        """Register a tool with its executor.

        Args:
            tool: Tool definition with schema
            executor: Async callable that executes the tool

        Raises:
            ValueError: If tool with same name already registered
        """
        if tool.name in self._tools:
            logger.warning(
                "tool_already_registered",
                tool_name=tool.name,
                action="overwriting",
            )

        self._tools[tool.name] = tool
        self._executors[tool.name] = executor

        logger.debug(
            "tool_registered",
            tool_name=tool.name,
            domain=tool.domain,
            has_executor=True,
        )

    def register_batch(
        self,
        tools: list[ToolDefinition],
        executors: dict[str, Callable[..., Any]],
    ) -> int:
        """Register multiple tools at once.

        Args:
            tools: List of tool definitions
            executors: Dict mapping tool names to executors

        Returns:
            Number of tools registered
        """
        count = 0
        for tool in tools:
            if tool.name in executors:
                self.register(tool, executors[tool.name])
                count += 1
            else:
                logger.warning(
                    "tool_missing_executor",
                    tool_name=tool.name,
                    skipped=True,
                )
        return count

    def get_tool(self, name: str) -> ToolDefinition | None:
        """Get tool definition by name."""
        return self._tools.get(name)

    def get_executor(self, tool_name: str) -> Callable[..., Any] | None:
        """Get the executor callable for a tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Async callable or None if not found
        """
        return self._executors.get(tool_name)

    def get_all_tools(self) -> list[ToolDefinition]:
        """Get all registered tool definitions."""
        return list(self._tools.values())

    def get_tools_by_domain(self, domain: str) -> list[ToolDefinition]:
        """Get tools filtered by domain."""
        return [t for t in self._tools.values() if t.domain == domain]

    def get_tool_domains(self) -> dict[str, str]:
        """Get mapping of tool_name -> domain for all tools.

        Used by HybridToolRouter for domain-based retrieval.
        """
        return {name: tool.domain for name, tool in self._tools.items() if tool.domain}

    def get_all_domains(self) -> list[str]:
        """Get list of all unique domains.

        Used by HybridToolRouter for domain classification.
        """
        domains = set()
        for tool in self._tools.values():
            if tool.domain:
                domains.add(tool.domain)
        return sorted(list(domains))

    def get_function_schemas(
        self,
        tool_names: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate OpenAI-compatible function schemas.

        Args:
            tool_names: Optional list of tool names to include.
                        If None, includes all tools.

        Returns:
            List of function schemas ready for LLM 'tools' parameter
        """
        tools = self._tools.values()
        if tool_names:
            tools = [t for t in tools if t.name in tool_names]

        return [tool.to_openai_function() for tool in tools]

    async def discover_from_domains(
        self,
        package: str = "me4brain.domains",
    ) -> int:
        """Auto-discover and register tools from domain modules.

        Scans domain packages for:
        - get_tool_definitions() -> list[ToolDefinition]
        - get_executors() -> dict[str, Callable]

        Args:
            package: Package path to scan

        Returns:
            Number of tools discovered and registered
        """
        if self._initialized:
            logger.debug("catalog_already_initialized", skipping=True)
            return len(self._tools)

        total_registered = 0

        try:
            pkg = importlib.import_module(package)
        except ImportError as e:
            logger.error("domain_package_import_failed", package=package, error=str(e))
            return 0

        # Iterate over submodules
        for importer, modname, ispkg in pkgutil.iter_modules(
            pkg.__path__,
            prefix=f"{package}.",
        ):
            if not ispkg:
                continue

            domain_name = modname.split(".")[-1]

            try:
                # Try to import tools module
                tools_module = importlib.import_module(f"{modname}.tools")

                # Check for required functions
                get_definitions = getattr(tools_module, "get_tool_definitions", None)
                get_executors = getattr(tools_module, "get_executors", None)

                if not (get_definitions and get_executors):
                    logger.debug(
                        "domain_missing_tool_interface",
                        domain=domain_name,
                        has_definitions=bool(get_definitions),
                        has_executors=bool(get_executors),
                    )
                    continue

                # Get definitions and executors
                definitions = get_definitions()
                executors = get_executors()

                # Register all tools
                count = self.register_batch(definitions, executors)
                total_registered += count

                logger.info(
                    "domain_tools_discovered",
                    domain=domain_name,
                    tools_count=count,
                )

            except ImportError:
                # No tools module - check for legacy handler interface
                try:
                    handler_module = importlib.import_module(f"{modname}.handler")
                    get_handler = getattr(handler_module, "get_handler", None)

                    if get_handler:
                        # Legacy handler - will be migrated later
                        logger.debug(
                            "domain_uses_legacy_handler",
                            domain=domain_name,
                        )
                except ImportError:
                    logger.debug(
                        "domain_no_tools_or_handler",
                        domain=domain_name,
                    )

            except Exception as e:
                logger.error(
                    "domain_discovery_error",
                    domain=domain_name,
                    error=str(e),
                )

        self._initialized = True

        logger.info(
            "catalog_discovery_complete",
            total_tools=total_registered,
            domains_scanned=len(list(pkgutil.iter_modules(pkg.__path__))),
        )

        return total_registered

    def __len__(self) -> int:
        """Return number of registered tools."""
        return len(self._tools)

    def __contains__(self, tool_name: str) -> bool:
        """Check if tool is registered."""
        return tool_name in self._tools
