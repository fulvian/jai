"""Autonomous Agent Tools - Create and manage proactive agents.

Tools for creating autonomous agents that can observe, decide, and act.
Pattern: Monitor → Evaluate → Act (Observe-Decide-Act loop)

Examples:
- "alert me when Bitcoin drops below 70k" → observe price, notify
- "monitor BTC and buy €1000 if it drops below 70k" → observe, decide, ACT
- "every morning at 9, check my calendar and remind me" → scheduled agent
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from enum import Enum

import httpx
import structlog

from me4brain.engine.types import ToolDefinition, ToolParameter

logger = structlog.get_logger(__name__)


# =============================================================================
# Constants
# =============================================================================


class AgentType(str, Enum):
    """Supported agent types."""

    PRICE_WATCH = "price_watch"
    SIGNAL_WATCH = "signal_watch"
    AUTONOMOUS = "autonomous"
    CALENDAR_WATCH = "calendar_watch"
    INBOX_WATCH = "inbox_watch"
    TASK_REMINDER = "task_reminder"
    SCHEDULED = "scheduled"


class NotifyChannel(str, Enum):
    """Notification channels."""

    WEB = "web"
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    EMAIL = "email"


PERSAN_BACKEND_URL = "http://localhost:8765"


# =============================================================================
# Tool Definitions
# =============================================================================

AGENT_TOOLS: list[ToolDefinition] = [
    ToolDefinition(
        name="create_autonomous_agent",
        description=(
            "Create an autonomous agent for RECURRING or SCHEDULED tasks. "
            "Use this when the user wants to SET UP automated monitoring that runs OVER TIME, "
            "not for one-time queries. Key distinction: "
            "- 'analyze X every day' → CREATE AGENT (recurring) "
            "- 'analyze X now' → use analysis tools (one-time) "
            "- 'alert me when X happens' → CREATE AGENT (conditional monitoring) "
            "- 'what is the price of X?' → use finance tools (one-time) "
            "Agents can monitor prices, schedules, conditions, and take autonomous actions "
            "like trading or sending notifications when triggered."
        ),
        domain="agents",
        parameters={
            "agent_type": ToolParameter(
                type="string",
                description="Type of agent: price_watch, signal_watch, calendar_watch, inbox_watch, task_reminder, autonomous, scheduled",
                required=True,
                enum=[
                    "price_watch",
                    "signal_watch",
                    "calendar_watch",
                    "inbox_watch",
                    "task_reminder",
                    "autonomous",
                    "scheduled",
                ],
            ),
            "name": ToolParameter(
                type="string",
                description="Human-readable name for the agent",
                required=True,
            ),
            "description": ToolParameter(
                type="string",
                description="Full description of what this agent does",
                required=False,
            ),
            "ticker": ToolParameter(
                type="string",
                description="Asset ticker for price/signal agents (e.g., BTC, AAPL, TSLA)",
                required=False,
            ),
            "condition": ToolParameter(
                type="string",
                description="Condition: 'above' or 'below'",
                required=False,
                enum=["above", "below"],
            ),
            "threshold": ToolParameter(
                type="number",
                description="Price/value threshold",
                required=False,
            ),
            "action": ToolParameter(
                type="string",
                description="Action to take when triggered (e.g., 'buy 1000', 'send email', 'notify')",
                required=False,
            ),
            "schedule": ToolParameter(
                type="string",
                description="Cron expression (e.g., '0 9 * * *' for daily at 9am)",
                required=False,
            ),
            "notify_channels": ToolParameter(
                type="array",
                description="Channels to send notifications to (web, telegram, whatsapp, email)",
                required=False,
                items={"type": "string"},
            ),
            # Risk Management parameters
            "risk_cap": ToolParameter(
                type="number",
                description="Maximum position size as percentage of capital (e.g., 0.02 for 2%)",
                required=False,
            ),
            "hitl_threshold": ToolParameter(
                type="number",
                description="HITL approval required for trades above this USD amount",
                required=False,
            ),
            "goal": ToolParameter(
                type="string",
                description="Natural language description of the agent's objective for autonomous mode",
                required=False,
            ),
        },
    ),
    ToolDefinition(
        name="list_agents",
        description=(
            "List all active autonomous agents for the current user. "
            "Use when user asks: 'show my agents', 'what monitors do I have', "
            "'list my alerts', 'quali agenti ho attivi', 'mostra i miei reminder'."
        ),
        domain="agents",
        parameters={},
    ),
    ToolDefinition(
        name="delete_agent",
        description=(
            "Delete an autonomous agent by ID. Use when user wants to stop an agent, "
            "remove an alert, or cancel a reminder."
        ),
        domain="agents",
        parameters={
            "agent_id": ToolParameter(
                type="string",
                description="ID of the agent to delete",
                required=True,
            ),
        },
    ),
]


# =============================================================================
# Tool Executors
# =============================================================================


async def create_autonomous_agent(
    agent_type: str,
    name: str,
    description: str | None = None,
    ticker: str | None = None,
    condition: str | None = None,
    threshold: float | None = None,
    action: str | None = None,
    schedule: str | None = None,
    notify_channels: list[str] | None = None,
    risk_cap: float | None = None,
    hitl_threshold: float | None = None,
    goal: str | None = None,
    user_id: str = "default",
    **kwargs: Any,  # Accept extra args from LLM (e.g., 'task' instead of 'goal')
) -> dict[str, Any]:
    """Create an autonomous agent via PersAn backend."""
    # Handle common LLM aliases
    if goal is None and "task" in kwargs:
        goal = kwargs.pop("task")

    # Log any unexpected kwargs for debugging
    if kwargs:
        logger.warning("create_autonomous_agent_unexpected_kwargs", kwargs=list(kwargs.keys()))

    logger.info(
        "create_autonomous_agent",
        type=agent_type,
        name=name,
        ticker=ticker,
        action=action,
        risk_cap=risk_cap,
        goal=goal,
    )

    config: dict[str, Any] = {}

    if agent_type == "price_watch" and ticker:
        config = {
            "ticker": ticker.upper(),
            "condition": condition or "below",
            "threshold": threshold,
            "currency": "USD",
            "action": action,
        }
    elif agent_type == "calendar_watch":
        config = {
            "calendar_id": "primary",
            "lookahead_minutes": 30,
            "action": action or "notify",
        }
    elif agent_type == "inbox_watch":
        config = {
            "email_account": "default",
            "importance_threshold": "medium",
            "action": action or "notify",
        }
    elif agent_type == "task_reminder":
        config = {
            "task_description": description or name,
            "priority": "medium",
            "action": action or "notify",
        }
    elif agent_type == "autonomous":
        config = {
            "goal": goal or description or name,
            "ticker": ticker,
            "action_mode": "notify_and_act" if action else "notify",
            "action": action,
            "action_type": "trade"
            if action and ("buy" in action.lower() or "sell" in action.lower())
            else "notify",
            # Risk management
            "risk_cap": risk_cap or 0.02,  # Default 2% of capital
            "hitl_threshold": hitl_threshold or 1000,  # Default $1000
        }

    if not schedule:
        schedule = {
            "price_watch": "*/5 * * * *",
            "calendar_watch": "0 8 * * *",
            "inbox_watch": "*/15 * * * *",
        }.get(agent_type, "0 9 * * *")

    payload = {
        "user_id": user_id,
        "type": agent_type,
        "name": name,
        "description": description or name,
        "schedule": schedule,
        "config": config,
        "notify_channels": notify_channels or ["web"],
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{PERSAN_BACKEND_URL}/api/proactive/monitors", json=payload
            )
            if response.status_code == 200:
                data = response.json()
                action_msg = f" Action: {action}" if action else ""
                return {
                    "success": True,
                    "agent_id": data.get("id"),
                    "name": data.get("name"),
                    "type": data.get("type"),
                    "schedule": data.get("schedule"),
                    "message": f"✅ Agent '{name}' created!{action_msg}",
                }
            return {
                "success": False,
                "error": f"Backend returned {response.status_code}",
            }
    except httpx.ConnectError:
        logger.warning("persan_backend_unavailable", url=PERSAN_BACKEND_URL)
        return {
            "success": True,
            "agent_id": f"agent-{datetime.now().timestamp()}",
            "name": name,
            "type": agent_type,
            "schedule": schedule,
            "action": action,
            "message": f"✅ Agent '{name}' created (demo mode).",
            "demo_mode": True,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def list_agents(user_id: str = "default") -> dict[str, Any]:
    """List all agents for user."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{PERSAN_BACKEND_URL}/api/proactive/monitors",
                params={"user_id": user_id},
            )
            if response.status_code == 200:
                data = response.json()
                agents = data.get("monitors", [])
                return {
                    "success": True,
                    "agents": agents,
                    "total": len(agents),
                    "message": f"Found {len(agents)} active agents.",
                }
            return {"success": False, "agents": [], "total": 0}
    except httpx.ConnectError:
        return {
            "success": True,
            "agents": [],
            "total": 0,
            "message": "No agents found (backend offline).",
            "demo_mode": True,
        }
    except Exception as e:
        return {"success": False, "error": str(e), "agents": []}


async def delete_agent(agent_id: str) -> dict[str, Any]:
    """Delete an agent by ID."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.delete(
                f"{PERSAN_BACKEND_URL}/api/proactive/monitors/{agent_id}"
            )
            if response.status_code == 200:
                return {"success": True, "message": f"✅ Agent {agent_id} deleted."}
            return {"success": False, "message": f"❌ Agent {agent_id} not found."}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def execute_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute an agent tool by name, filtering unexpected parameters."""
    import inspect

    tool_map = {
        "create_autonomous_agent": create_autonomous_agent,
        "create_proactive_monitor": create_autonomous_agent,
        "list_agents": list_agents,
        "list_monitors": list_agents,
        "delete_agent": delete_agent,
        "delete_monitor": delete_agent,
    }

    func = tool_map.get(tool_name)
    if func is None:
        return {"error": f"Unknown tool: {tool_name}"}

    sig = inspect.signature(func)
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

    return await func(**filtered_args)


def get_tool_definitions() -> list[ToolDefinition]:
    """Get tool definitions for catalog."""
    return AGENT_TOOLS


def get_executors() -> dict:
    """Get tool executors map."""
    return {
        "create_autonomous_agent": create_autonomous_agent,
        "list_agents": list_agents,
        "delete_agent": delete_agent,
        # Backward compatibility
        "create_proactive_monitor": create_autonomous_agent,
        "list_monitors": list_agents,
        "delete_monitor": delete_agent,
    }
