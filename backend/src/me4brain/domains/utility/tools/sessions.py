"""Sessions Tools - Tool per l'agente per comunicazione inter-agente."""

from __future__ import annotations

import uuid
from datetime import datetime

import structlog

from me4brain.core.agents.messenger import get_agent_messenger
from me4brain.core.agents.registry import get_agent_registry
from me4brain.core.agents.supervisor import get_supervisor
from me4brain.core.agents.types import (
    AgentMessage,
    HandoffRequest,
)

logger = structlog.get_logger(__name__)

# Default caller ID (il main agent)
MAIN_AGENT_ID = "main"


async def sessions_list(capability: str | None = None) -> list[dict]:
    """
    Lista agenti attivi e loro status.

    Pattern OpenClaw: sessions_list.

    Args:
        capability: Filtra per capability (opzionale)

    Returns:
        Lista agenti con status
    """
    registry = get_agent_registry()
    if registry is None:
        logger.warning("agent_registry_not_initialized")
        return []

    agents = await registry.list_agents(capability=capability)

    return [
        {
            "id": agent.id,
            "name": agent.name,
            "type": agent.type.value,
            "capabilities": agent.capabilities,
            "status": agent.status.value,
            "current_task": agent.current_task,
            "success_rate": agent.success_rate,
        }
        for agent in agents
    ]


async def sessions_history(
    agent_id: str,
    limit: int = 20,
) -> list[dict]:
    """
    Storico messaggi per agente.

    Pattern OpenClaw: sessions_history.

    Args:
        agent_id: ID agente
        limit: Max messaggi

    Returns:
        Lista messaggi
    """
    messenger = get_agent_messenger()
    if messenger is None:
        logger.warning("agent_messenger_not_initialized")
        return []

    messages = await messenger.history(agent_id, limit=limit)

    return [
        {
            "id": msg.id,
            "from_agent": msg.from_agent,
            "to_agent": msg.to_agent,
            "content": msg.content,
            "timestamp": msg.timestamp.isoformat(),
            "context_keys": list(msg.context.keys()),
        }
        for msg in messages
    ]


async def sessions_send(
    to_agent: str,
    message: str,
    context: dict | None = None,
    reply_skip: bool = False,
) -> dict:
    """
    Invia messaggio ad altro agente.

    Pattern OpenClaw: sessions_send.

    Args:
        to_agent: ID agente destinatario
        message: Contenuto messaggio
        context: Context aggiuntivo
        reply_skip: Se True, non aspetta risposta

    Returns:
        Conferma invio
    """
    messenger = get_agent_messenger()
    if messenger is None:
        return {"error": "Agent messenger not initialized"}

    msg = AgentMessage(
        id=str(uuid.uuid4()),
        from_agent=MAIN_AGENT_ID,
        to_agent=to_agent,
        content=message,
        context=context or {},
        timestamp=datetime.now(),
    )

    redis_id = await messenger.send(msg)

    return {
        "sent": True,
        "message_id": msg.id,
        "to_agent": to_agent,
        "redis_id": redis_id,
        "reply_skip": reply_skip,
    }


async def sessions_handoff(
    task: str,
    to_agent: str | None = None,
    context: dict | None = None,
    priority: int = 0,
) -> dict:
    """
    Delega task ad altro agente.

    Se to_agent non specificato, il supervisor sceglie l'agente migliore.

    Args:
        task: Descrizione task
        to_agent: ID agente (opzionale, auto-route)
        context: Context per il task
        priority: 0=normale, 1+=alta priorità

    Returns:
        Stato handoff
    """
    supervisor = get_supervisor()
    if supervisor is None:
        return {"error": "Supervisor not initialized"}

    request = HandoffRequest(
        id=str(uuid.uuid4()),
        from_agent=MAIN_AGENT_ID,
        to_agent=to_agent or "auto",
        task=task,
        context=context or {},
        priority=priority,
    )

    result = await supervisor.handoff(request)

    return {
        "handoff_id": result.id,
        "status": result.status,
        "to_agent": result.to_agent,
        "task": result.task[:100],
    }


async def sessions_monitor() -> dict:
    """
    Status tutti gli agenti.

    Returns:
        Dict con status di tutti gli agenti
    """
    supervisor = get_supervisor()
    if supervisor is None:
        return {"error": "Supervisor not initialized"}

    return await supervisor.monitor()


async def sessions_recall(handoff_id: str) -> dict:
    """
    Richiama risultato di un handoff.

    Args:
        handoff_id: ID handoff

    Returns:
        Risultato handoff
    """
    supervisor = get_supervisor()
    if supervisor is None:
        return {"error": "Supervisor not initialized"}

    result = await supervisor.recall(handoff_id)
    if result is None:
        return {"error": f"Handoff not found: {handoff_id}"}

    return result


# Tool definitions per registrazione in Procedural Memory
SESSIONS_TOOLS = [
    {
        "name": "sessions_list",
        "description": "Lista agenti attivi con loro status e capabilities",
        "parameters": {
            "type": "object",
            "properties": {
                "capability": {
                    "type": "string",
                    "description": "Filtra per capability (es. 'research', 'coding')",
                },
            },
        },
    },
    {
        "name": "sessions_send",
        "description": "Invia messaggio ad altro agente",
        "parameters": {
            "type": "object",
            "properties": {
                "to_agent": {
                    "type": "string",
                    "description": "ID agente destinatario",
                },
                "message": {
                    "type": "string",
                    "description": "Contenuto messaggio",
                },
                "context": {
                    "type": "object",
                    "description": "Context aggiuntivo",
                },
            },
            "required": ["to_agent", "message"],
        },
    },
    {
        "name": "sessions_handoff",
        "description": "Delega task ad altro agente specializzato",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Descrizione del task da delegare",
                },
                "to_agent": {
                    "type": "string",
                    "description": "ID agente (opzionale, auto-route se non specificato)",
                },
                "context": {
                    "type": "object",
                    "description": "Context per il task",
                },
                "priority": {
                    "type": "integer",
                    "description": "Priorità: 0=normale, 1+=alta",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "sessions_monitor",
        "description": "Ottiene status di tutti gli agenti",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "sessions_recall",
        "description": "Richiama risultato di un handoff precedente",
        "parameters": {
            "type": "object",
            "properties": {
                "handoff_id": {
                    "type": "string",
                    "description": "ID del handoff",
                },
            },
            "required": ["handoff_id"],
        },
    },
]
