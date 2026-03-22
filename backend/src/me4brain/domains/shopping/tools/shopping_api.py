"""Shopping Tools API - Bridge to Skills."""

from typing import Any
import structlog

logger = structlog.get_logger(__name__)

AVAILABLE_TOOLS = {}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool di shopping delegando alle skills."""
    if tool_name in AVAILABLE_TOOLS:
        tool_func = AVAILABLE_TOOLS[tool_name]
        return await tool_func(**arguments)

    logger.warning("shopping_tool_not_in_local_registry", tool=tool_name)
    return {"error": f"Tool {tool_name} not registered in shopping_api (Skill delegation required)"}


def get_tool_definitions() -> list:
    return []


def get_executors() -> dict:
    return AVAILABLE_TOOLS
