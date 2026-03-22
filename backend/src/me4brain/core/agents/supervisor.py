"""Agent Supervisor - Coordinamento e routing task tra agenti."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import structlog
from redis.asyncio import Redis

from me4brain.core.agents.messenger import AgentMessenger, get_agent_messenger
from me4brain.core.agents.registry import AgentRegistry, get_agent_registry
from me4brain.core.agents.types import (
    AgentMessage,
    AgentProfile,
    AgentStatus,
    HandoffRequest,
    MessageFlag,
)

logger = structlog.get_logger(__name__)


class SupervisorAgent:
    """
    Supervisor per coordinamento multi-agente.

    Responsabilità:
    - Routing task ad agenti specializzati
    - Orchestrazione handoff
    - Monitoring stato agenti
    - Recall risultati
    """

    HANDOFF_PREFIX = "me4brain:agents:handoffs"
    SUPERVISOR_ID = "supervisor"

    def __init__(
        self,
        registry: Optional[AgentRegistry] = None,
        messenger: Optional[AgentMessenger] = None,
        redis: Optional[Redis] = None,
    ):
        """
        Inizializza supervisor.

        Args:
            registry: AgentRegistry
            messenger: AgentMessenger
            redis: Client Redis per handoff storage
        """
        self.registry = registry
        self.messenger = messenger
        self.redis = redis

    def _get_registry(self) -> AgentRegistry:
        return self.registry or get_agent_registry()

    def _get_messenger(self) -> AgentMessenger:
        return self.messenger or get_agent_messenger()

    async def route(
        self,
        task: str,
        context: dict,
        required_capability: Optional[str] = None,
    ) -> Optional[AgentProfile]:
        """
        Seleziona miglior agente per task.

        Strategia:
        1. Se specificata capability, cerca agente con quella capability
        2. Altrimenti, analizza task per inferire capability
        3. Seleziona agente idle con miglior success rate

        Args:
            task: Descrizione task
            context: Context task
            required_capability: Capability richiesta (opzionale)

        Returns:
            Agente selezionato o None
        """
        registry = self._get_registry()

        # Determina capability richiesta
        capability = required_capability or self._infer_capability(task)

        if capability:
            agent = await registry.find_best_agent(capability)
            if agent:
                logger.info(
                    "agent_routed",
                    task=task[:50],
                    agent_id=agent.id,
                    capability=capability,
                )
                return agent

        # Fallback: qualsiasi agente idle
        agents = await registry.list_agents(status=AgentStatus.IDLE)
        if agents:
            # Ordina per success rate
            agents.sort(key=lambda a: a.success_rate, reverse=True)
            return agents[0]

        logger.warning("no_agent_available", task=task[:50])
        return None

    def _infer_capability(self, task: str) -> Optional[str]:
        """
        Inferisce capability da task description.

        Semplice pattern matching per ora.
        """
        task_lower = task.lower()

        patterns = {
            "research": ["search", "find", "research", "look up", "analyze"],
            "coding": ["code", "implement", "fix", "debug", "refactor"],
            "assistant": ["help", "explain", "summarize", "answer"],
            "data": ["data", "database", "query", "extract"],
        }

        for capability, keywords in patterns.items():
            if any(kw in task_lower for kw in keywords):
                return capability

        return None

    async def handoff(self, request: HandoffRequest) -> HandoffRequest:
        """
        Delega task ad altro agente.

        Args:
            request: Richiesta handoff

        Returns:
            Handoff aggiornato con stato
        """
        registry = self._get_registry()
        messenger = self._get_messenger()

        # Trova agente target se non specificato
        if not request.to_agent or request.to_agent == "auto":
            target = await self.route(request.task, request.context)
            if target is None:
                request.status = "rejected"
                return request
            request.to_agent = target.id

        # Verifica agente esiste
        target_profile = await registry.get(request.to_agent)
        if target_profile is None:
            request.status = "rejected"
            return request

        # Aggiorna stato agente
        await registry.update_status(
            request.to_agent,
            AgentStatus.BUSY,
            current_task=request.task[:100],
        )

        # Invia messaggio
        message = AgentMessage(
            id=str(uuid.uuid4()),
            from_agent=request.from_agent,
            to_agent=request.to_agent,
            content=f"HANDOFF: {request.task}",
            context={
                "handoff_id": request.id,
                "priority": request.priority,
                **request.context,
            },
            flags=[MessageFlag.PRIORITY_HIGH] if request.priority > 0 else [],
        )

        await messenger.send(message)

        # Salva handoff
        request.status = "accepted"
        request.accepted_at = datetime.now()

        if self.redis:
            key = f"{self.HANDOFF_PREFIX}:{request.id}"
            await self.redis.set(key, request.model_dump_json())

        logger.info(
            "handoff_sent",
            handoff_id=request.id,
            from_agent=request.from_agent,
            to_agent=request.to_agent,
        )

        return request

    async def monitor(self) -> dict[str, dict]:
        """
        Status tutti gli agenti.

        Returns:
            Dict agent_id -> status info
        """
        registry = self._get_registry()
        agents = await registry.list_agents()

        status = {}
        for agent in agents:
            status[agent.id] = {
                "name": agent.name,
                "type": agent.type.value,
                "status": agent.status.value,
                "current_task": agent.current_task,
                "success_rate": agent.success_rate,
                "last_active": (
                    agent.last_active.isoformat() if agent.last_active else None
                ),
            }

        return status

    async def recall(
        self,
        handoff_id: str,
    ) -> Optional[dict]:
        """
        Richiama risultato da handoff.

        Args:
            handoff_id: ID handoff

        Returns:
            Risultato o None
        """
        if not self.redis:
            return None

        key = f"{self.HANDOFF_PREFIX}:{handoff_id}"
        data = await self.redis.get(key)

        if data is None:
            return None

        handoff = HandoffRequest.model_validate_json(data)

        return {
            "id": handoff.id,
            "status": handoff.status,
            "to_agent": handoff.to_agent,
            "task": handoff.task,
            "result": handoff.result,
            "created_at": handoff.created_at.isoformat(),
            "completed_at": (
                handoff.completed_at.isoformat() if handoff.completed_at else None
            ),
        }

    async def complete_handoff(
        self,
        handoff_id: str,
        result: dict,
        success: bool = True,
    ) -> None:
        """
        Completa handoff con risultato.

        Args:
            handoff_id: ID handoff
            result: Risultato task
            success: Esito task
        """
        if not self.redis:
            return

        key = f"{self.HANDOFF_PREFIX}:{handoff_id}"
        data = await self.redis.get(key)

        if data is None:
            return

        handoff = HandoffRequest.model_validate_json(data)
        handoff.status = "completed"
        handoff.result = result
        handoff.completed_at = datetime.now()

        await self.redis.set(key, handoff.model_dump_json())

        # Aggiorna stats agente
        registry = self._get_registry()
        await registry.record_task_completion(handoff.to_agent, success)

        logger.info(
            "handoff_completed",
            handoff_id=handoff_id,
            agent_id=handoff.to_agent,
            success=success,
        )


# Singleton
_supervisor: Optional[SupervisorAgent] = None


def get_supervisor() -> Optional[SupervisorAgent]:
    """Ottiene supervisor globale."""
    return _supervisor


def set_supervisor(supervisor: SupervisorAgent) -> None:
    """Imposta supervisor globale."""
    global _supervisor
    _supervisor = supervisor
