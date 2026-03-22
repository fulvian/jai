"""Web Search Tools Package."""

from me4brain.domains.web_search.tools.search_api import (
    AVAILABLE_TOOLS,
    duckduckgo_instant,
    execute_tool,
    get_executors,
    get_tool_definitions,
)

__all__ = [
    "AVAILABLE_TOOLS",
    "execute_tool",
    "get_tool_definitions",
    "get_executors",
    "duckduckgo_instant",
]
