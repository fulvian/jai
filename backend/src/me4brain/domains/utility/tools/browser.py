"""Browser Tools - Tool per l'agente per browser automation."""

from __future__ import annotations

from typing import Optional

import structlog

from me4brain.core.browser.manager import get_browser_manager
from me4brain.core.browser.types import BrowserConfig

logger = structlog.get_logger(__name__)

# Session ID corrente (per continuità)
_current_session_id: Optional[str] = None


async def browser_open(
    url: str,
    headless: bool = True,
) -> dict:
    """
    Apre browser e naviga a URL.

    Args:
        url: URL da aprire
        headless: Modalità headless (default True)

    Returns:
        Stato sessione
    """
    global _current_session_id

    manager = get_browser_manager()
    if manager is None:
        return {"error": "Browser manager not initialized"}

    try:
        config = BrowserConfig(headless=headless)
        session = await manager.create_session(config=config, start_url=url)
        _current_session_id = session.id

        return {
            "session_id": session.id,
            "url": session.current_url,
            "title": session.current_title,
            "status": session.status.value,
        }

    except Exception as e:
        return {"error": str(e)}


async def browser_act(
    instruction: str,
    session_id: Optional[str] = None,
) -> dict:
    """
    Esegue azione descritta in linguaggio naturale.

    Esempi:
    - "Click the login button"
    - "Type 'hello@example.com' in the email field"
    - "Scroll down to see more content"

    Args:
        instruction: Descrizione azione
        session_id: ID sessione (usa corrente se None)

    Returns:
        Risultato azione
    """
    manager = get_browser_manager()
    if manager is None:
        return {"error": "Browser manager not initialized"}

    sid = session_id or _current_session_id
    if not sid:
        return {"error": "No active browser session. Call browser_open first."}

    wrapper = await manager.get_wrapper(sid)
    if wrapper is None:
        return {"error": f"Session {sid} not found"}

    result = await wrapper.act(instruction)

    return {
        "success": result.success,
        "url": result.url,
        "error": result.error,
        "data": result.data,
    }


async def browser_extract(
    what: str,
    schema: Optional[dict] = None,
    session_id: Optional[str] = None,
) -> dict:
    """
    Estrae dati strutturati dalla pagina.

    Esempi:
    - "Extract all product names and prices"
    - "Get the main article text"
    - "Find all links in the navigation"

    Args:
        what: Cosa estrarre
        schema: JSON Schema per output strutturato
        session_id: ID sessione

    Returns:
        Dati estratti
    """
    manager = get_browser_manager()
    if manager is None:
        return {"error": "Browser manager not initialized"}

    sid = session_id or _current_session_id
    if not sid:
        return {"error": "No active browser session"}

    wrapper = await manager.get_wrapper(sid)
    if wrapper is None:
        return {"error": f"Session {sid} not found"}

    result = await wrapper.extract(what, schema=schema)

    return {
        "success": result.success,
        "extracted": result.data.get("extracted") if result.data else None,
        "error": result.error,
    }


async def browser_screenshot(session_id: Optional[str] = None) -> dict:
    """
    Cattura screenshot pagina corrente.

    Args:
        session_id: ID sessione

    Returns:
        Path screenshot
    """
    manager = get_browser_manager()
    if manager is None:
        return {"error": "Browser manager not initialized"}

    sid = session_id or _current_session_id
    if not sid:
        return {"error": "No active browser session"}

    wrapper = await manager.get_wrapper(sid)
    if wrapper is None:
        return {"error": f"Session {sid} not found"}

    result = await wrapper.screenshot()

    return {
        "success": result.success,
        "screenshot_path": result.screenshot_path,
        "error": result.error,
    }


async def browser_navigate(
    url: str,
    session_id: Optional[str] = None,
) -> dict:
    """
    Naviga a nuovo URL.

    Args:
        url: URL destinazione
        session_id: ID sessione

    Returns:
        Risultato navigazione
    """
    manager = get_browser_manager()
    if manager is None:
        return {"error": "Browser manager not initialized"}

    sid = session_id or _current_session_id
    if not sid:
        return {"error": "No active browser session"}

    wrapper = await manager.get_wrapper(sid)
    if wrapper is None:
        return {"error": f"Session {sid} not found"}

    result = await wrapper.navigate(url)

    return {
        "success": result.success,
        "url": result.url,
        "title": result.title,
        "error": result.error,
    }


async def browser_close(session_id: Optional[str] = None) -> dict:
    """
    Chiude sessione browser.

    Args:
        session_id: ID sessione

    Returns:
        Conferma
    """
    global _current_session_id

    manager = get_browser_manager()
    if manager is None:
        return {"error": "Browser manager not initialized"}

    sid = session_id or _current_session_id
    if not sid:
        return {"error": "No active browser session"}

    await manager.close_session(sid)

    if sid == _current_session_id:
        _current_session_id = None

    return {"closed": True, "session_id": sid}


# Tool definitions per registrazione in Procedural Memory
BROWSER_TOOLS = [
    {
        "name": "browser_open",
        "description": "Opens a browser and navigates to the specified URL",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to open",
                },
                "headless": {
                    "type": "boolean",
                    "description": "Run in headless mode (default: true)",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_act",
        "description": "Executes an action described in natural language (click, type, scroll, etc.)",
        "parameters": {
            "type": "object",
            "properties": {
                "instruction": {
                    "type": "string",
                    "description": "Natural language description of the action to perform",
                },
            },
            "required": ["instruction"],
        },
    },
    {
        "name": "browser_extract",
        "description": "Extracts structured data from the current page",
        "parameters": {
            "type": "object",
            "properties": {
                "what": {
                    "type": "string",
                    "description": "What data to extract from the page",
                },
                "schema": {
                    "type": "object",
                    "description": "Optional JSON Schema for structured output",
                },
            },
            "required": ["what"],
        },
    },
    {
        "name": "browser_screenshot",
        "description": "Captures a screenshot of the current page",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "browser_navigate",
        "description": "Navigates to a new URL in the current browser session",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to navigate to",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "browser_close",
        "description": "Closes the current browser session",
        "parameters": {"type": "object", "properties": {}},
    },
]


# =============================================================================
# Tool Engine Integration
# =============================================================================


def get_tool_definitions() -> list:
    """Generate ToolDefinition objects for all browser tools."""
    from me4brain.engine.types import ToolDefinition, ToolParameter

    return [
        ToolDefinition(
            name="browser_open",
            description="Opens a browser and navigates to the specified URL. Use for web scraping, form filling, or automation tasks.",
            parameters={
                "url": ToolParameter(
                    type="string",
                    required=True,
                    description="URL to open",
                ),
                "headless": ToolParameter(
                    type="boolean",
                    required=False,
                    description="Run in headless mode (default: true)",
                ),
            },
            domain="web_data",
            category="browser",
        ),
        ToolDefinition(
            name="browser_act",
            description="Executes an action described in natural language on the current page. Examples: 'Click the login button', 'Type hello@example.com in the email field', 'Scroll down'.",
            parameters={
                "instruction": ToolParameter(
                    type="string",
                    required=True,
                    description="Natural language description of the action to perform",
                ),
            },
            domain="web_data",
            category="browser",
        ),
        ToolDefinition(
            name="browser_extract",
            description="Extracts structured data from the current page. Examples: 'Extract all product names and prices', 'Get the main article text'.",
            parameters={
                "what": ToolParameter(
                    type="string",
                    required=True,
                    description="What data to extract from the page",
                ),
                "schema": ToolParameter(
                    type="object",
                    required=False,
                    description="Optional JSON Schema for structured output",
                ),
            },
            domain="web_data",
            category="browser",
        ),
        ToolDefinition(
            name="browser_screenshot",
            description="Captures a screenshot of the current page.",
            parameters={},
            domain="web_data",
            category="browser",
        ),
        ToolDefinition(
            name="browser_navigate",
            description="Navigates to a new URL in the current browser session.",
            parameters={
                "url": ToolParameter(
                    type="string",
                    required=True,
                    description="URL to navigate to",
                ),
            },
            domain="web_data",
            category="browser",
        ),
        ToolDefinition(
            name="browser_close",
            description="Closes the current browser session.",
            parameters={},
            domain="web_data",
            category="browser",
        ),
    ]


def get_executors() -> dict:
    """Return mapping of tool names to executor functions."""
    return {
        "browser_open": browser_open,
        "browser_act": browser_act,
        "browser_extract": browser_extract,
        "browser_screenshot": browser_screenshot,
        "browser_navigate": browser_navigate,
        "browser_close": browser_close,
    }
