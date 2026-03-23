"""Agent Registry - Registro agenti attivi."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

import structlog
from redis.asyncio import Redis

from me4brain.core.agents.types import (
    AgentProfile,
    AgentStatus,
    AgentType,
    RegisterAgentRequest,
)

logger = structlog.get_logger(__name__)


class AgentRegistry:
    """
    Registro agenti attivi.

    Pattern OpenClaw: sessions_list, sessions_describe.
    Storage: Redis hash per ogni agente.
    """

    PREFIX = "me4brain:agents:profiles"
    INDEX_KEY = "me4brain:agents:index"
    CAPABILITY_INDEX = "me4brain:agents:capabilities"

    def __init__(self, redis: Redis):
        """
        Inizializza registry.

        Args:
            redis: Client Redis async
        """
        self.redis = redis

    def _agent_key(self, agent_id: str) -> str:
        """Genera chiave Redis per agente."""
        return f"{self.PREFIX}:{agent_id}"

    async def register(self, request: RegisterAgentRequest, agent_id: str) -> AgentProfile:
        """
        Registra nuovo agente.

        Args:
            request: Dati registrazione
            agent_id: ID assegnato

        Returns:
            Profilo agente creato
        """
        profile = AgentProfile(
            id=agent_id,
            name=request.name,
            type=request.type,
            capabilities=request.capabilities,
            metadata=request.metadata,
        )

        # Salva profilo
        key = self._agent_key(agent_id)
        await self.redis.set(key, profile.model_dump_json())

        # Aggiungi a indice
        await self.redis.sadd(self.INDEX_KEY, agent_id)

        # Indice capabilities
        for cap in profile.capabilities:
            await self.redis.sadd(f"{self.CAPABILITY_INDEX}:{cap}", agent_id)

        logger.info(
            "agent_registered",
            agent_id=agent_id,
            name=profile.name,
            type=profile.type.value,
            capabilities=profile.capabilities,
        )

        return profile

    async def unregister(self, agent_id: str) -> bool:
        """
        Rimuovi agente dal registro.

        Args:
            agent_id: ID agente

        Returns:
            True se rimosso
        """
        profile = await self.get(agent_id)
        if profile is None:
            return False

        key = self._agent_key(agent_id)

        # Rimuovi da indici
        await self.redis.srem(self.INDEX_KEY, agent_id)
        for cap in profile.capabilities:
            await self.redis.srem(f"{self.CAPABILITY_INDEX}:{cap}", agent_id)

        # Elimina profilo
        await self.redis.delete(key)

        logger.info("agent_unregistered", agent_id=agent_id)
        return True

    async def get(self, agent_id: str) -> Optional[AgentProfile]:
        """
        Recupera profilo agente.

        Args:
            agent_id: ID agente

        Returns:
            Profilo o None
        """
        key = self._agent_key(agent_id)
        data = await self.redis.get(key)

        if data is None:
            return None

        return AgentProfile.model_validate_json(data)

    async def list_agents(
        self,
        capability: Optional[str] = None,
        status: Optional[AgentStatus] = None,
        agent_type: Optional[AgentType] = None,
    ) -> list[AgentProfile]:
        """
        Lista agenti con filtri.

        Args:
            capability: Filtra per capability
            status: Filtra per stato
            agent_type: Filtra per tipo

        Returns:
            Lista agenti
        """
        # Usa indice capability se specificato
        if capability:
            agent_ids = await self.redis.smembers(f"{self.CAPABILITY_INDEX}:{capability}")
        else:
            agent_ids = await self.redis.smembers(self.INDEX_KEY)

        profiles: list[AgentProfile] = []

        for agent_id in agent_ids:
            profile = await self.get(agent_id)
            if profile is None:
                continue

            # Filtri
            if status and profile.status != status:
                continue
            if agent_type and profile.type != agent_type:
                continue

            profiles.append(profile)

        return profiles

    async def update_status(
        self,
        agent_id: str,
        status: AgentStatus,
        current_task: Optional[str] = None,
    ) -> None:
        """
        Aggiorna stato agente.

        Args:
            agent_id: ID agente
            status: Nuovo stato
            current_task: Task corrente
        """
        profile = await self.get(agent_id)
        if profile is None:
            return

        profile.status = status
        profile.current_task = current_task
        profile.last_active = datetime.now()

        key = self._agent_key(agent_id)
        await self.redis.set(key, profile.model_dump_json())

        logger.debug(
            "agent_status_updated",
            agent_id=agent_id,
            status=status.value,
        )

    async def record_task_completion(
        self,
        agent_id: str,
        success: bool,
    ) -> None:
        """
        Registra completamento task.

        Args:
            agent_id: ID agente
            success: Esito task
        """
        profile = await self.get(agent_id)
        if profile is None:
            return

        if success:
            profile.tasks_completed += 1
        else:
            profile.tasks_failed += 1

        profile.status = AgentStatus.IDLE
        profile.current_task = None
        profile.last_active = datetime.now()

        key = self._agent_key(agent_id)
        await self.redis.set(key, profile.model_dump_json())

    async def find_best_agent(
        self,
        capability: str,
        exclude: Optional[list[str]] = None,
    ) -> Optional[AgentProfile]:
        """
        Trova miglior agente per capability.

        Criteri:
        1. Ha la capability
        2. È idle
        3. Miglior success rate

        Args:
            capability: Capability richiesta
            exclude: Agenti da escludere

        Returns:
            Miglior agente o None
        """
        exclude = exclude or []

        candidates = await self.list_agents(
            capability=capability,
            status=AgentStatus.IDLE,
        )

        # Escludi agenti
        candidates = [c for c in candidates if c.id not in exclude]

        if not candidates:
            return None

        # Ordina per success rate
        candidates.sort(key=lambda a: a.success_rate, reverse=True)

        return candidates[0]


# Singleton
_agent_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> Optional[AgentRegistry]:
    """Ottiene registry globale."""
    return _agent_registry


def set_agent_registry(registry: AgentRegistry) -> None:
    """Imposta registry globale."""
    global _agent_registry
    _agent_registry = registry


async def initialize_agent_registry(
    redis_url: str = "redis://localhost:6379",
) -> AgentRegistry:
    """
    Inizializza agent registry.

    Args:
        redis_url: URL connessione Redis

    Returns:
        AgentRegistry inizializzato
    """
    redis = Redis.from_url(redis_url, decode_responses=True)
    registry = AgentRegistry(redis)
    set_agent_registry(registry)
    logger.info("agent_registry_initialized", redis_url=redis_url)
    return registry
