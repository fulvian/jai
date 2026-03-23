"""Agents API Routes - Endpoint REST per gestione agenti e comunicazione."""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException

from me4brain.core.agents.context import get_shared_context
from me4brain.core.agents.messenger import get_agent_messenger
from me4brain.core.agents.registry import get_agent_registry
from me4brain.core.agents.supervisor import get_supervisor
from me4brain.core.agents.types import (
    AgentMessage,
    AgentResponse,
    HandoffRequest,
    HandoffTaskRequest,
    MessageResponse,
    RegisterAgentRequest,
    SendMessageRequest,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/agents", tags=["agents"])


def _get_registry():
    registry = get_agent_registry()
    if registry is None:
        raise HTTPException(503, "Agent registry not initialized")
    return registry


def _get_messenger():
    messenger = get_agent_messenger()
    if messenger is None:
        raise HTTPException(503, "Agent messenger not initialized")
    return messenger


# --- Agent Registration ---


@router.post("", response_model=AgentResponse)
async def register_agent(request: RegisterAgentRequest) -> AgentResponse:
    """
    Registra nuovo agente.

    Args:
        request: Dati registrazione

    Returns:
        Profilo agente creato
    """
    registry = _get_registry()
    agent_id = str(uuid.uuid4())[:12]

    profile = await registry.register(request, agent_id)

    logger.info("agent_registered_via_api", agent_id=agent_id, name=profile.name)
    return AgentResponse.from_profile(profile)


@router.get("", response_model=list[AgentResponse])
async def list_agents(
    capability: str | None = None,
    status: str | None = None,
) -> list[AgentResponse]:
    """
    Lista agenti registrati.

    Args:
        capability: Filtra per capability
        status: Filtra per status

    Returns:
        Lista agenti
    """
    registry = _get_registry()
    agents = await registry.list_agents(capability=capability)

    if status:
        agents = [a for a in agents if a.status.value == status]

    return [AgentResponse.from_profile(a) for a in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str) -> AgentResponse:
    """
    Dettaglio agente.

    Args:
        agent_id: ID agente

    Returns:
        Profilo agente
    """
    registry = _get_registry()
    profile = await registry.get(agent_id)

    if profile is None:
        raise HTTPException(404, "Agent not found")

    return AgentResponse.from_profile(profile)


@router.delete("/{agent_id}")
async def unregister_agent(agent_id: str) -> dict[str, str]:
    """
    Rimuovi agente dal registro.

    Args:
        agent_id: ID agente

    Returns:
        Conferma
    """
    registry = _get_registry()
    success = await registry.unregister(agent_id)

    if not success:
        raise HTTPException(404, "Agent not found")

    return {"message": f"Agent {agent_id} unregistered"}


# --- Messaging ---


@router.post("/{agent_id}/messages", response_model=MessageResponse)
async def send_message(
    agent_id: str,
    request: SendMessageRequest,
) -> MessageResponse:
    """
    Invia messaggio ad agente.

    Args:
        agent_id: ID agente destinatario
        request: Dati messaggio

    Returns:
        Messaggio inviato
    """
    messenger = _get_messenger()

    message = AgentMessage(
        id=str(uuid.uuid4()),
        from_agent="api",  # Chiamante API
        to_agent=agent_id,
        content=request.content,
        context=request.context,
        reply_to=request.reply_to,
    )

    await messenger.send(message)

    return MessageResponse(
        id=message.id,
        from_agent=message.from_agent,
        to_agent=message.to_agent,
        content=message.content,
        timestamp=message.timestamp,
        acknowledged=False,
    )


@router.get("/{agent_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    agent_id: str,
    limit: int = 50,
) -> list[MessageResponse]:
    """
    Storico messaggi agente.

    Args:
        agent_id: ID agente
        limit: Max messaggi

    Returns:
        Lista messaggi
    """
    messenger = _get_messenger()
    messages = await messenger.history(agent_id, limit=limit)

    return [
        MessageResponse(
            id=m.id,
            from_agent=m.from_agent,
            to_agent=m.to_agent,
            content=m.content,
            timestamp=m.timestamp,
            acknowledged=m.acknowledged,
        )
        for m in messages
    ]


# --- Handoff ---


@router.post("/handoff")
async def request_handoff(request: HandoffTaskRequest) -> dict:
    """
    Richiedi handoff task.

    Args:
        request: Richiesta handoff

    Returns:
        Stato handoff
    """
    supervisor = get_supervisor()
    if supervisor is None:
        raise HTTPException(503, "Supervisor not initialized")

    handoff = HandoffRequest(
        id=str(uuid.uuid4()),
        from_agent="api",
        to_agent=request.to_agent or "auto",
        task=request.task,
        context=request.context,
        priority=request.priority,
    )

    result = await supervisor.handoff(handoff)

    return {
        "handoff_id": result.id,
        "status": result.status,
        "to_agent": result.to_agent,
    }


@router.get("/handoff/{handoff_id}")
async def get_handoff(handoff_id: str) -> dict:
    """
    Stato handoff.

    Args:
        handoff_id: ID handoff

    Returns:
        Stato handoff
    """
    supervisor = get_supervisor()
    if supervisor is None:
        raise HTTPException(503, "Supervisor not initialized")

    result = await supervisor.recall(handoff_id)
    if result is None:
        raise HTTPException(404, "Handoff not found")

    return result


# --- Context ---


@router.get("/context/{task_id}")
async def get_context(task_id: str) -> dict:
    """
    Legge shared context per task.

    Args:
        task_id: ID task

    Returns:
        Context completo
    """
    ctx = get_shared_context()
    if ctx is None:
        raise HTTPException(503, "Shared context not initialized")

    return await ctx.get_all(task_id)


@router.put("/context/{task_id}")
async def update_context(
    task_id: str,
    data: dict,
) -> dict[str, str]:
    """
    Aggiorna shared context.

    Args:
        task_id: ID task
        data: Dati da mergiare

    Returns:
        Conferma
    """
    ctx = get_shared_context()
    if ctx is None:
        raise HTTPException(503, "Shared context not initialized")

    await ctx.merge(task_id, data)

    return {"message": f"Context {task_id} updated"}


# --- Monitor ---


@router.get("/monitor/status")
async def monitor_status() -> dict:
    """
    Status tutti gli agenti.

    Returns:
        Status globale
    """
    supervisor = get_supervisor()
    if supervisor is None:
        raise HTTPException(503, "Supervisor not initialized")

    return await supervisor.monitor()
