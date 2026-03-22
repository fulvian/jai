"""Quota Manager - Enforcement limiti risorse per tenant."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Optional, Tuple

import structlog
import redis.asyncio as redis

from me4brain.config import get_settings
from me4brain.core.tenant.context import get_tenant_id
from me4brain.core.tenant.store import TenantStore
from me4brain.core.tenant.types import TenantQuota, TenantUsage

logger = structlog.get_logger(__name__)


class QuotaExceededError(Exception):
    """Raised quando quota superata."""

    def __init__(self, resource: str, current: int, limit: int):
        super().__init__(f"Quota exceeded for {resource}: {current}/{limit}")
        self.resource = resource
        self.current = current
        self.limit = limit


class QuotaManager:
    """
    Manager per quota enforcement.

    Usa Redis per tracking atomico delle risorse:
    - quota:{tenant_id}:{resource}:current - Valore corrente
    - quota:{tenant_id}:{resource}:reset - Timestamp reset

    Risorse tracciate:
    - api_calls_day: Reset giornaliero
    - api_calls_minute: Reset ogni minuto
    - llm_tokens_month: Reset mensile
    - storage_mb: Nessun reset (cumulativo)
    """

    PREFIX = "quota"

    # TTL per counter (auto-cleanup)
    TTL_MINUTE = 60
    TTL_DAY = 86400  # 24h
    TTL_MONTH = 2678400  # 31 giorni

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """
        Args:
            redis_client: Client Redis (opzionale)
        """
        self._redis = redis_client

    async def get_redis(self) -> redis.Redis:
        """Lazy initialization del client Redis."""
        if self._redis is None:
            settings = get_settings()
            self._redis = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
        return self._redis

    def _key(self, tenant_id: str, resource: str) -> str:
        """Genera chiave per counter."""
        return f"{self.PREFIX}:{tenant_id}:{resource}"

    async def check(
        self,
        tenant_id: str,
        resource: str,
    ) -> TenantQuota:
        """
        Controlla stato quota senza incrementare.

        Args:
            tenant_id: ID tenant
            resource: Nome risorsa

        Returns:
            TenantQuota con stato corrente
        """
        r = await self.get_redis()
        key = self._key(tenant_id, resource)

        # Ottieni valore corrente
        current = await r.get(key)
        current = int(current) if current else 0

        # Ottieni limite da config
        limit = await self._get_limit(tenant_id, resource)

        return TenantQuota(
            tenant_id=tenant_id,
            resource=resource,
            current=current,
            limit=limit,
            remaining=max(0, limit - current),
        )

    async def check_and_increment(
        self,
        tenant_id: str,
        resource: str,
        amount: int = 1,
    ) -> Tuple[bool, int, int]:
        """
        Verifica quota e incrementa se permesso.

        Usa operazione atomica INCR + confronto.

        Args:
            tenant_id: ID tenant
            resource: Nome risorsa
            amount: Quantità da incrementare

        Returns:
            Tuple (allowed, current, limit)
        """
        r = await self.get_redis()
        key = self._key(tenant_id, resource)

        # Ottieni limite
        limit = await self._get_limit(tenant_id, resource)

        # Incrementa atomicamente
        current = await r.incrby(key, amount)

        # Imposta TTL se primo uso
        ttl = await r.ttl(key)
        if ttl == -1:  # No TTL set
            ttl_seconds = self._get_ttl(resource)
            if ttl_seconds:
                await r.expire(key, ttl_seconds)

        allowed = current <= limit

        if not allowed:
            # Rollback se non permesso
            await r.decrby(key, amount)
            current -= amount

            logger.warning(
                "quota_exceeded",
                tenant_id=tenant_id,
                resource=resource,
                current=current,
                limit=limit,
            )

        return (allowed, current, limit)

    async def increment(
        self,
        tenant_id: str,
        resource: str,
        amount: int = 1,
    ) -> int:
        """
        Incrementa quota senza verificare limite.

        Utile per tracking (es. storage) dove il controllo
        è fatto separatamente.

        Args:
            tenant_id: ID tenant
            resource: Nome risorsa
            amount: Quantità

        Returns:
            Nuovo valore
        """
        r = await self.get_redis()
        key = self._key(tenant_id, resource)

        current = await r.incrby(key, amount)

        # Set TTL se primo uso
        ttl = await r.ttl(key)
        if ttl == -1:
            ttl_seconds = self._get_ttl(resource)
            if ttl_seconds:
                await r.expire(key, ttl_seconds)

        return current

    async def decrement(
        self,
        tenant_id: str,
        resource: str,
        amount: int = 1,
    ) -> int:
        """Decrementa quota (es. rilascio storage)."""
        r = await self.get_redis()
        key = self._key(tenant_id, resource)

        current = await r.decrby(key, amount)
        return max(0, current)

    async def reset(self, tenant_id: str, resource: str) -> None:
        """Reset manuale quota a zero."""
        r = await self.get_redis()
        key = self._key(tenant_id, resource)
        await r.delete(key)

        logger.info("quota_reset", tenant_id=tenant_id, resource=resource)

    async def reset_all(self, tenant_id: str) -> None:
        """Reset tutte le quote di un tenant."""
        r = await self.get_redis()
        pattern = f"{self.PREFIX}:{tenant_id}:*"

        keys = []
        async for key in r.scan_iter(match=pattern):
            keys.append(key)

        if keys:
            await r.delete(*keys)

        logger.info("all_quotas_reset", tenant_id=tenant_id, count=len(keys))

    async def get_usage(self, tenant_id: str) -> TenantUsage:
        """
        Ottieni usage completo per tenant.

        Returns:
            TenantUsage con tutti i contatori
        """
        r = await self.get_redis()

        # Leggi tutti i contatori
        keys = {
            "api_calls_day": f"{self.PREFIX}:{tenant_id}:api_calls_day",
            "api_calls_minute": f"{self.PREFIX}:{tenant_id}:api_calls_minute",
            "llm_tokens_month": f"{self.PREFIX}:{tenant_id}:llm_tokens_month",
            "storage_mb": f"{self.PREFIX}:{tenant_id}:storage_mb",
            "episodes": f"{self.PREFIX}:{tenant_id}:episodes",
            "entities": f"{self.PREFIX}:{tenant_id}:entities",
            "sessions": f"{self.PREFIX}:{tenant_id}:sessions",
            "browser_sessions": f"{self.PREFIX}:{tenant_id}:browser_sessions",
        }

        values = await r.mget(list(keys.values()))

        def safe_int(v):
            return int(v) if v else 0

        def safe_float(v):
            return float(v) if v else 0.0

        return TenantUsage(
            tenant_id=tenant_id,
            api_calls_today=safe_int(values[0]),
            api_calls_this_minute=safe_int(values[1]),
            llm_tokens_this_month=safe_int(values[2]),
            storage_used_mb=safe_float(values[3]),
            episodes_count=safe_int(values[4]),
            entities_count=safe_int(values[5]),
            active_sessions=safe_int(values[6]),
            active_browser_sessions=safe_int(values[7]),
        )

    async def get_all_quotas(self, tenant_id: str) -> list[TenantQuota]:
        """Ottieni tutte le quote con limiti."""
        resources = [
            "api_calls_day",
            "api_calls_minute",
            "llm_tokens_month",
            "storage_mb",
            "episodes",
            "entities",
        ]

        return [await self.check(tenant_id, r) for r in resources]

    async def _get_limit(self, tenant_id: str, resource: str) -> int:
        """Ottieni limite per risorsa da config tenant."""
        store = TenantStore()
        config = await store.get(tenant_id)

        if not config:
            # Default limits se tenant non trovato
            return 1000

        limits = config.limits

        # Mapping resource -> limit field
        mapping = {
            "api_calls_day": limits.api_calls_per_day,
            "api_calls_minute": limits.api_calls_per_minute,
            "llm_tokens_month": limits.llm_tokens_per_month,
            "storage_mb": limits.storage_mb,
            "episodes": limits.max_episodes,
            "entities": limits.max_entities,
            "sessions": limits.max_concurrent_sessions,
            "browser_sessions": limits.max_browser_sessions,
        }

        return mapping.get(resource, 1000)

    def _get_ttl(self, resource: str) -> Optional[int]:
        """Ottieni TTL per risorsa."""
        ttls = {
            "api_calls_day": self.TTL_DAY,
            "api_calls_minute": self.TTL_MINUTE,
            "llm_tokens_month": self.TTL_MONTH,
            # Nessun TTL per storage (cumulativo)
        }
        return ttls.get(resource)


# --- Decorators ---


def check_quota(resource: str, amount: int = 1):
    """
    Decorator per verificare quota prima di eseguire.

    Uso:
        @check_quota("api_calls_day")
        async def process_request(...):
            ...
    """
    from functools import wraps

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            tenant_id = get_tenant_id()
            manager = QuotaManager()

            allowed, current, limit = await manager.check_and_increment(
                tenant_id, resource, amount
            )

            if not allowed:
                raise QuotaExceededError(resource, current, limit)

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# Singleton
_quota_manager: Optional[QuotaManager] = None


def get_quota_manager() -> QuotaManager:
    """Ottiene manager globale."""
    global _quota_manager
    if _quota_manager is None:
        _quota_manager = QuotaManager()
    return _quota_manager
