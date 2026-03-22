"""Utility Tools Package."""

from me4brain.domains.utility.tools.utility_api import (
    AVAILABLE_TOOLS,
    execute_tool,
    get_executors as get_api_executors,
    get_headers,
    get_ip,
    get_tool_definitions as get_api_tool_definitions,
)

from me4brain.domains.utility.tools.browser import (
    BROWSER_TOOLS,
    browser_act,
    browser_close,
    browser_extract,
    browser_navigate,
    browser_open,
    browser_screenshot,
    get_executors as get_browser_executors,
    get_tool_definitions as get_browser_tool_definitions,
)

from me4brain.domains.utility.tools.proactive import (
    AGENT_TOOLS,
    create_autonomous_agent,
    list_agents,
    delete_agent,
    get_executors as get_proactive_executors,
    get_tool_definitions as get_proactive_tool_definitions,
)


def get_tool_definitions() -> list:
    """Get all utility tool definitions (API + Browser + Proactive)."""
    return (
        get_api_tool_definitions()
        + get_browser_tool_definitions()
        + get_proactive_tool_definitions()
    )


def get_executors() -> dict:
    """Get all utility tool executors (API + Browser + Proactive)."""
    return {
        **get_api_executors(),
        **get_browser_executors(),
        **get_proactive_executors(),
    }


__all__ = [
    # API Tools
    "AVAILABLE_TOOLS",
    "execute_tool",
    "get_tool_definitions",
    "get_executors",
    "get_ip",
    "get_headers",
    # Browser Tools
    "BROWSER_TOOLS",
    "browser_open",
    "browser_act",
    "browser_extract",
    "browser_screenshot",
    "browser_navigate",
    "browser_close",
    # Agent Tools
    "AGENT_TOOLS",
    "create_autonomous_agent",
    "list_agents",
    "delete_agent",
]
