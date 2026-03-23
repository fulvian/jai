"""Agent Messenger - Comunicazione inter-agente via Redis Streams."""

from __future__ import annotations

import json
from datetime import datetime

import structlog
from redis.asyncio import Redis

from me4brain.core.agents.types import (
    AgentMessage,
    MessageFlag,
)

logger = structlog.get_logger(__name__)


class AgentMessenger:
    """
    Messenger per comunicazione tra agenti via Redis Streams.

    Pattern OpenClaw: sessions_send, sessions_history.
    Usa Redis Streams con consumer groups per delivery garantita.
    """

    STREAM_PREFIX = "me4brain:agents:stream"
    GROUP_NAME = "agent_consumers"

    def __init__(self, redis: Redis):
        """
        Inizializza messenger.

        Args:
            redis: Client Redis async
        """
        self.redis = redis
        self._stream_created: set[str] = set()

    def _stream_key(self, agent_id: str) -> str:
        """Genera chiave stream per agente."""
        return f"{self.STREAM_PREFIX}:{agent_id}"

    async def _ensure_stream(self, agent_id: str) -> None:
        """Crea stream e consumer group se non esistono."""
        stream_key = self._stream_key(agent_id)

        if stream_key in self._stream_created:
            return

        try:
            # Crea consumer group (crea stream se non esiste)
            await self.redis.xgroup_create(
                stream_key,
                self.GROUP_NAME,
                id="0",
                mkstream=True,
            )
            self._stream_created.add(stream_key)
        except Exception as e:
            # Group già esiste (BUSYGROUP)
            if "BUSYGROUP" in str(e):
                self._stream_created.add(stream_key)
            else:
                logger.warning("stream_create_error", error=str(e))

    async def send(self, message: AgentMessage) -> str:
        """
        Invia messaggio ad agente.

        Args:
            message: Messaggio da inviare

        Returns:
            Message ID assegnato da Redis
        """
        # Assicura che lo stream esista
        await self._ensure_stream(message.to_agent)

        stream_key = self._stream_key(message.to_agent)

        # Serializza messaggio
        message_data = {
            "id": message.id,
            "from_agent": message.from_agent,
            "to_agent": message.to_agent,
            "content": message.content,
            "context": json.dumps(message.context),
            "reply_to": message.reply_to or "",
            "flags": ",".join(f.value for f in message.flags),
            "timestamp": message.timestamp.isoformat(),
        }

        # XADD
        redis_id = await self.redis.xadd(stream_key, message_data)

        logger.info(
            "message_sent",
            message_id=message.id,
            from_agent=message.from_agent,
            to_agent=message.to_agent,
            redis_id=redis_id,
        )

        return redis_id

    async def receive(
        self,
        agent_id: str,
        consumer_name: str | None = None,
        count: int = 10,
        block_ms: int = 0,
    ) -> list[tuple[str, AgentMessage]]:
        """
        Ricevi messaggi per agente.

        Args:
            agent_id: ID agente destinatario
            consumer_name: Nome consumer (default: agent_id)
            count: Max messaggi da leggere
            block_ms: Tempo di blocking (0 = no block)

        Returns:
            Lista di (redis_id, messaggio)
        """
        await self._ensure_stream(agent_id)

        stream_key = self._stream_key(agent_id)
        consumer = consumer_name or agent_id

        try:
            # XREADGROUP
            results = await self.redis.xreadgroup(
                groupname=self.GROUP_NAME,
                consumername=consumer,
                streams={stream_key: ">"},
                count=count,
                block=block_ms if block_ms > 0 else None,
            )
        except Exception as e:
            logger.error("receive_error", error=str(e))
            return []

        messages: list[tuple[str, AgentMessage]] = []

        for _stream, stream_messages in results:
            for redis_id, data in stream_messages:
                try:
                    message = self._parse_message(data)
                    messages.append((redis_id, message))
                except Exception as e:
                    logger.warning("parse_message_error", redis_id=redis_id, error=str(e))

        return messages

    async def history(
        self,
        agent_id: str,
        limit: int = 50,
        before_id: str | None = None,
    ) -> list[AgentMessage]:
        """
        Storico messaggi per agente.

        Args:
            agent_id: ID agente
            limit: Max messaggi
            before_id: Leggi prima di questo ID

        Returns:
            Lista messaggi (più recenti prima)
        """
        stream_key = self._stream_key(agent_id)

        end = before_id or "+"
        start = "-"

        try:
            results = await self.redis.xrevrange(
                stream_key,
                max=end,
                min=start,
                count=limit,
            )
        except Exception:
            return []

        messages: list[AgentMessage] = []

        for _redis_id, data in results:
            try:
                message = self._parse_message(data)
                messages.append(message)
            except Exception:
                continue

        return messages

    async def ack(self, agent_id: str, redis_id: str) -> None:
        """
        Conferma ricezione messaggio.

        Args:
            agent_id: ID agente
            redis_id: ID messaggio Redis
        """
        stream_key = self._stream_key(agent_id)
        await self.redis.xack(stream_key, self.GROUP_NAME, redis_id)

        logger.debug("message_acked", agent_id=agent_id, redis_id=redis_id)

    async def pending_count(self, agent_id: str) -> int:
        """Conta messaggi pending per agente."""
        stream_key = self._stream_key(agent_id)

        try:
            info = await self.redis.xpending(stream_key, self.GROUP_NAME)
            return info.get("pending", 0) if info else 0
        except Exception:
            return 0

    def _parse_message(self, data: dict) -> AgentMessage:
        """Parsa dati Redis in AgentMessage."""
        flags = []
        if data.get("flags"):
            for f in data["flags"].split(","):
                if f:
                    flags.append(MessageFlag(f))

        return AgentMessage(
            id=data["id"],
            from_agent=data["from_agent"],
            to_agent=data["to_agent"],
            content=data["content"],
            context=json.loads(data.get("context") or "{}"),
            reply_to=data.get("reply_to") or None,
            flags=flags,
            timestamp=datetime.fromisoformat(data["timestamp"]),
        )


# Singleton
_agent_messenger: AgentMessenger | None = None


def get_agent_messenger() -> AgentMessenger | None:
    """Ottiene messenger globale."""
    return _agent_messenger


def set_agent_messenger(messenger: AgentMessenger) -> None:
    """Imposta messenger globale."""
    global _agent_messenger
    _agent_messenger = messenger


async def initialize_agent_messenger(
    redis_url: str = "redis://localhost:6379",
) -> AgentMessenger:
    """Inizializza agent messenger."""
    redis = Redis.from_url(redis_url, decode_responses=True)
    messenger = AgentMessenger(redis)
    set_agent_messenger(messenger)
    logger.info("agent_messenger_initialized", redis_url=redis_url)
    return messenger
