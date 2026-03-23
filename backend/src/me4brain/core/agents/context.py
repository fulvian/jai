"""Shared Context - Propagazione contesto tra agenti."""

from __future__ import annotations

import json
from typing import Any

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


class SharedContext:
    """
    Shared context per task multi-agente.

    Permette propagazione stato tra agenti che collaborano
    sullo stesso task.
    """

    PREFIX = "me4brain:context"
    DEFAULT_TTL = 3600  # 1 ora

    def __init__(self, redis: Redis, ttl_seconds: int = DEFAULT_TTL):
        """
        Inizializza shared context.

        Args:
            redis: Client Redis async
            ttl_seconds: TTL default per context
        """
        self.redis = redis
        self.ttl_seconds = ttl_seconds

    def _context_key(self, task_id: str) -> str:
        """Genera chiave Redis per context."""
        return f"{self.PREFIX}:{task_id}"

    async def set(
        self,
        task_id: str,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> None:
        """
        Imposta valore nel context.

        Args:
            task_id: ID task
            key: Chiave
            value: Valore (serializzato in JSON)
            ttl: TTL in secondi (opzionale)
        """
        context_key = self._context_key(task_id)

        # Serializza valore
        if isinstance(value, (dict, list)):
            serialized = json.dumps(value)
        else:
            serialized = str(value)

        await self.redis.hset(context_key, key, serialized)

        # Imposta TTL
        await self.redis.expire(context_key, ttl or self.ttl_seconds)

        logger.debug(
            "context_set",
            task_id=task_id,
            key=key,
        )

    async def get(self, task_id: str, key: str) -> Any | None:
        """
        Legge valore dal context.

        Args:
            task_id: ID task
            key: Chiave

        Returns:
            Valore o None
        """
        context_key = self._context_key(task_id)
        value = await self.redis.hget(context_key, key)

        if value is None:
            return None

        # Prova deserializzazione JSON
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    async def get_all(self, task_id: str) -> dict[str, Any]:
        """
        Legge tutto il context.

        Args:
            task_id: ID task

        Returns:
            Dict con tutti i valori
        """
        context_key = self._context_key(task_id)
        raw = await self.redis.hgetall(context_key)

        result = {}
        for key, value in raw.items():
            try:
                result[key] = json.loads(value)
            except json.JSONDecodeError:
                result[key] = value

        return result

    async def propagate(
        self,
        from_task: str,
        to_task: str,
        keys: list[str] | None = None,
    ) -> int:
        """
        Copia context da un task a un altro.

        Args:
            from_task: Task sorgente
            to_task: Task destinazione
            keys: Chiavi specifiche (tutte se None)

        Returns:
            Numero di chiavi copiate
        """
        source_key = self._context_key(from_task)
        dest_key = self._context_key(to_task)

        if keys:
            # Copia chiavi specifiche
            for key in keys:
                value = await self.redis.hget(source_key, key)
                if value:
                    await self.redis.hset(dest_key, key, value)

            await self.redis.expire(dest_key, self.ttl_seconds)
            return len(keys)

        else:
            # Copia tutto
            all_data = await self.redis.hgetall(source_key)
            if all_data:
                await self.redis.hset(dest_key, mapping=all_data)
                await self.redis.expire(dest_key, self.ttl_seconds)

            logger.debug(
                "context_propagated",
                from_task=from_task,
                to_task=to_task,
                keys_count=len(all_data),
            )

            return len(all_data)

    async def merge(
        self,
        task_id: str,
        data: dict[str, Any],
    ) -> None:
        """
        Merge dati nel context esistente.

        Args:
            task_id: ID task
            data: Dati da mergiare
        """
        context_key = self._context_key(task_id)

        for key, value in data.items():
            if isinstance(value, (dict, list)):
                serialized = json.dumps(value)
            else:
                serialized = str(value)
            await self.redis.hset(context_key, key, serialized)

        await self.redis.expire(context_key, self.ttl_seconds)

    async def delete(self, task_id: str, key: str | None = None) -> None:
        """
        Elimina context o singola chiave.

        Args:
            task_id: ID task
            key: Chiave specifica (tutto context se None)
        """
        context_key = self._context_key(task_id)

        if key:
            await self.redis.hdel(context_key, key)
        else:
            await self.redis.delete(context_key)

    async def cleanup_expired(self) -> int:
        """
        Pulisce context scaduti.

        Returns:
            Numero di context eliminati
        """
        # Redis gestisce TTL automaticamente
        # Questo metodo esiste per coerenza API
        return 0

    async def extend_ttl(
        self,
        task_id: str,
        seconds: int | None = None,
    ) -> None:
        """
        Estende TTL di un context.

        Args:
            task_id: ID task
            seconds: Nuova durata (default: TTL originale)
        """
        context_key = self._context_key(task_id)
        await self.redis.expire(context_key, seconds or self.ttl_seconds)


# Singleton
_shared_context: SharedContext | None = None


def get_shared_context() -> SharedContext | None:
    """Ottiene shared context globale."""
    return _shared_context


def set_shared_context(ctx: SharedContext) -> None:
    """Imposta shared context globale."""
    global _shared_context
    _shared_context = ctx


async def initialize_shared_context(
    redis_url: str = "redis://localhost:6379",
    ttl_seconds: int = 3600,
) -> SharedContext:
    """Inizializza shared context."""
    redis = Redis.from_url(redis_url, decode_responses=True)
    ctx = SharedContext(redis, ttl_seconds)
    set_shared_context(ctx)
    logger.info("shared_context_initialized", redis_url=redis_url, ttl=ttl_seconds)
    return ctx
