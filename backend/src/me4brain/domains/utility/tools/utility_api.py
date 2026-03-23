"""Utility API Tools."""

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


async def get_ip() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get("https://httpbin.org/ip")
        return {"ip": resp.json().get("origin"), "source": "httpbin"}


async def get_headers() -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get("https://httpbin.org/headers")
        return {"headers": resp.json().get("headers"), "source": "httpbin"}


AVAILABLE_TOOLS = {"get_ip": get_ip, "get_headers": get_headers}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool utility per nome, filtrando parametri non accettati."""
    import inspect

    if tool_name not in AVAILABLE_TOOLS:
        return {"error": f"Unknown utility tool: {tool_name}"}

    tool_func = AVAILABLE_TOOLS[tool_name]
    sig = inspect.signature(tool_func)
    valid_params = set(sig.parameters.keys())
    filtered_args = {k: v for k, v in arguments.items() if k in valid_params}

    if len(filtered_args) < len(arguments):
        ignored = set(arguments.keys()) - valid_params
        logger.warning(
            "execute_tool_ignored_params",
            tool=tool_name,
            ignored=list(ignored),
            hint="LLM hallucinated parameters not in function signature",
        )

    return await tool_func(**filtered_args)


# =============================================================================
# Tool Engine Integration
# =============================================================================


def get_tool_definitions() -> list:
    """Generate ToolDefinition objects for all Utility tools."""
    from me4brain.engine.types import ToolDefinition

    return [
        ToolDefinition(
            name="get_ip",
            description="Get the current public IP address. Use when user asks 'what is my IP', 'my IP address', 'show IP'.",
            parameters={},
            domain="system",
            category="network",
        ),
        ToolDefinition(
            name="get_headers",
            description="Get the HTTP request headers. Use when user asks 'show my headers', 'HTTP request info', 'browser headers'.",
            parameters={},
            domain="system",
            category="network",
        ),
    ]


def get_executors() -> dict:
    """Return mapping of tool names to executor functions."""
    return AVAILABLE_TOOLS
