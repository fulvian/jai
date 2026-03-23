"""Contract Generator - Generate ToolContracts from existing domain tools.

This module generates ToolContract entries from existing tool definitions.
It bridges the old ToolDefinition format to the new ToolContract format.

Usage:
    from me4brain.engine.contract_generator import generate_all_contracts

    # Generate all contracts from all domains
    contracts = generate_all_contracts()

    # Register them in the registry
    registry = ToolContractRegistry.get_instance()
    registry.register_batch(contracts)
"""

from __future__ import annotations

import importlib
from typing import Any

import structlog

from me4brain.engine.tool_contract import (
    LatencyClass,
    RiskLevel,
    ToolContract,
    ToolContractRegistry,
)

logger = structlog.get_logger(__name__)

# Domain modules to scan for tool definitions
DOMAIN_TOOLS_MODULES: dict[str, str] = {
    "finance_crypto": "me4brain.domains.finance_crypto.tools.finance_api",
    "sports_nba": "me4brain.domains.sports_nba.tools.nba_api",
    "google_workspace": "me4brain.domains.google_workspace.tools.google_api",
    "web_search": "me4brain.domains.web_search.tools.search_api",
    "utility": "me4brain.domains.utility.tools.browser",
}


def _get_parameters_schema(parameters: dict[str, Any]) -> dict[str, Any]:
    """Convert parameters dict to JSON Schema format.

    Handles both legacy dict format and ToolParameter objects.
    """
    properties = {}
    required = []

    for param_name, param_info in parameters.items():
        if isinstance(param_info, dict):
            # Legacy dict format
            prop = {
                "type": param_info.get("type", "string"),
                "description": param_info.get("description", ""),
            }
            if "enum" in param_info:
                prop["enum"] = param_info["enum"]
            if param_info.get("required"):
                required.append(param_name)
        else:
            # ToolParameter object (has type, description, required attributes)
            prop = {
                "type": getattr(param_info, "type", "string"),
                "description": getattr(param_info, "description", ""),
            }
            if getattr(param_info, "enum", None):
                prop["enum"] = param_info.enum
            if getattr(param_info, "required", False):
                required.append(param_name)

        properties[param_name] = prop

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema


def _infer_risk_level(domain: str, category: str | None) -> RiskLevel:
    """Infer risk level from domain and category.

    Returns:
        RiskLevel based on domain characteristics.
    """
    # High risk domains
    high_risk_keywords = {"payment", "transfer", "buy", "sell", "trade", "delete", "admin"}
    if category and any(kw in category.lower() for kw in high_risk_keywords):
        return RiskLevel.HIGH

    # Read-only/utility domains
    low_risk_keywords = {"search", "get", "list", "fetch", "price", "quote", "weather"}
    if category and any(kw in category.lower() for kw in low_risk_keywords):
        return RiskLevel.LOW

    # Domain-specific defaults
    domain_defaults: dict[str, RiskLevel] = {
        "finance_crypto": RiskLevel.MEDIUM,
        "google_workspace": RiskLevel.MEDIUM,
        "sports_nba": RiskLevel.LOW,
        "web_search": RiskLevel.LOW,
        "travel": RiskLevel.MEDIUM,
        "food": RiskLevel.LOW,
        "medical": RiskLevel.HIGH,
        "shopping": RiskLevel.HIGH,
    }

    return domain_defaults.get(domain, RiskLevel.MEDIUM)


def _infer_latency_class(category: str | None, domain: str | None) -> LatencyClass:
    """Infer latency class from category and domain.

    Returns:
        LatencyClass based on expected response time.
    """
    # Fast operations
    fast_keywords = {"price", "quote", "weather", "search", "get"}
    if category and any(kw in category.lower() for kw in fast_keywords):
        return LatencyClass.FAST

    # Slow operations
    slow_keywords = {"history", "chart", "historical", "analysis", "report"}
    if category and any(kw in category.lower() for kw in slow_keywords):
        return LatencyClass.SLOW

    # Variable for external APIs
    variable_keywords = {"external", "api", "http"}
    if category and any(kw in category.lower() for kw in variable_keywords):
        return LatencyClass.VARIABLE

    return LatencyClass.NORMAL


def _tool_def_to_contract(
    tool_def: Any,
    domain: str,
    skill: str | None = None,
) -> ToolContract | None:
    """Convert a ToolDefinition to ToolContract.

    Args:
        tool_def: ToolDefinition object or dict with tool info
        domain: Domain name
        skill: Optional skill name override

    Returns:
        ToolContract if conversion successful, None otherwise
    """
    try:
        # Handle both ToolDefinition objects and dicts
        if hasattr(tool_def, "name"):
            # It's a ToolDefinition object
            name = tool_def.name
            description = getattr(tool_def, "description", "")
            parameters = getattr(tool_def, "parameters", {})
            category = getattr(tool_def, "category", None) or "general"
            domain = getattr(tool_def, "domain", None) or domain
        elif isinstance(tool_def, dict):
            # It's a dict
            name = tool_def.get("name")
            description = tool_def.get("description", "")
            parameters = tool_def.get("parameters", {})
            category = tool_def.get("category", None) or "general"
            domain = tool_def.get("domain", domain)
        else:
            logger.warning("unknown_tool_def_type", tool_def=type(tool_def))
            return None

        if not name:
            logger.warning("tool_definition_missing_name", tool_def=tool_def)
            return None

        # Generate tool_id from name
        tool_id = name.replace("-", "_")

        # Convert parameters to schema format
        parameters_schema = _get_parameters_schema(parameters)

        # Truncate description if too long for ToolContract (max 500 chars)
        if len(description) > 500:
            description = description[:497] + "..."

        # Generate embedding hint from description
        embedding_hint = description[:200] if description else name

        # Infer classification from domain/category
        risk_level = _infer_risk_level(domain, category)
        latency_class = _infer_latency_class(category, domain)

        return ToolContract(
            tool_id=tool_id,
            domain=domain or "unknown",
            category=category or "general",
            skill=skill or category or "general",
            name=name,
            description=description,
            parameters=parameters_schema,
            risk_level=risk_level,
            latency_class=latency_class,
            embedding_hint=embedding_hint,
        )

    except Exception as e:
        logger.error(
            "contract_conversion_failed",
            tool_def=getattr(tool_def, "name", str(tool_def)),
            error=str(e),
        )
        return None


def generate_from_module(module_name: str, domain: str) -> list[ToolContract]:
    """Generate ToolContracts from a specific module.

    Args:
        module_name: Full module path (e.g., 'me4brain.domains.finance_crypto.tools.finance_api')
        domain: Domain name

    Returns:
        List of ToolContract generated from the module
    """
    contracts = []

    try:
        module = importlib.import_module(module_name)

        # Check for get_tool_definitions function
        if hasattr(module, "get_tool_definitions"):
            tool_defs = module.get_tool_definitions()

            for tool_def in tool_defs:
                contract = _tool_def_to_contract(tool_def, domain)
                if contract:
                    contracts.append(contract)

            logger.info(
                "contracts_generated_from_module",
                module=module_name,
                domain=domain,
                count=len(contracts),
            )
        else:
            logger.warning("module_has_no_get_tool_definitions", module=module_name)

    except ImportError as e:
        logger.error("failed_to_import_module", module=module_name, error=str(e))
    except Exception as e:
        logger.error("error_processing_module", module=module_name, error=str(e))

    return contracts


def generate_all_contracts() -> list[ToolContract]:
    """Generate ToolContracts from all known domain modules.

    Returns:
        List of all ToolContract from all domains
    """
    all_contracts = []

    for domain, module_name in DOMAIN_TOOLS_MODULES.items():
        contracts = generate_from_module(module_name, domain)
        all_contracts.extend(contracts)

    logger.info(
        "all_contracts_generated",
        total_count=len(all_contracts),
        domains=list(DOMAIN_TOOLS_MODULES.keys()),
    )

    return all_contracts


def register_all_contracts() -> int:
    """Generate and register all contracts in the global registry.

    Returns:
        Number of contracts registered
    """
    registry = ToolContractRegistry.get_instance()
    contracts = generate_all_contracts()
    count = registry.register_batch(contracts)

    logger.info("contracts_registered", count=count)

    return count


def get_registry_keywords() -> dict[str, list[str]]:
    """Get domain keywords from all registered contracts.

    Returns:
        Dictionary mapping domain -> list of keywords
    """
    registry = ToolContractRegistry.get_instance()
    return registry.get_domain_keywords()
