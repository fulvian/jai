"""Productivity Tools API - Bridge to Skills."""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# This domain mainly delegates to skills.
# We define AVAILABLE_TOOLS broadly or dynamically if possible.
# For now, we'll keep it simple to support the execute_tool pattern.

AVAILABLE_TOOLS = {}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Esegue tool di produttività delegando alle skills se necessario."""
    if tool_name in AVAILABLE_TOOLS:
        tool_func = AVAILABLE_TOOLS[tool_name]
        return await tool_func(**arguments)

    # Se il tool non è in AVAILABLE_TOOLS, loggeremo un avvertimento.
    # In un sistema GraphRAG, l'executor risolverà il tool tramite il registro delle skills.
    logger.warning("productivity_tool_not_in_local_registry", tool=tool_name)
    return {
        "error": f"Tool {tool_name} not registered in productivity_api (Skill delegation required)"
    }


def get_tool_definitions() -> list:
    return []


def get_executors() -> dict:
    return AVAILABLE_TOOLS
