"""Tenant Store - CRUD tenant in Redis."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import redis.asyncio as redis
import structlog

from me4brain.config import get_settings
from me4brain.core.tenant.types import (
    TenantConfig,
    TenantFeatures,
    TenantLimits,
    TenantStatus,
    TenantTier,
)

logger = structlog.get_logger(__name__)


class TenantStore:
    """
    Store per tenant configurations in Redis.

    Keys:
    - tenant:{id}:config - Configurazione JSON
    - tenant:{id}:metadata - Metadata extra
    - tenants:index - Set di tutti i tenant IDs
    """

    PREFIX = "tenant"
    INDEX_KEY = "tenants:index"
    DEFAULT_TTL = None  # Nessuna scadenza per config

    def __init__(self, redis_client: redis.Redis | None = None):
        """
        Args:
            redis_client: Client Redis (opzionale, lazy init)
        """
        self._redis = redis_client
        self._initialized = False

    async def get_redis(self) -> redis.Redis:
        """Lazy initialization del client Redis."""
        if self._redis is None:
            settings = get_settings()
            self._redis = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
        return self._redis

    def _config_key(self, tenant_id: str) -> str:
        """Genera chiave per config tenant."""
        return f"{self.PREFIX}:{tenant_id}:config"

    async def create(
        self,
        name: str,
        tier: TenantTier = TenantTier.FREE,
        owner_email: str | None = None,
        tenant_id: str | None = None,
    ) -> TenantConfig:
        """
        Crea nuovo tenant.

        Args:
            name: Nome tenant
            tier: Tier (FREE/PRO/ENTERPRISE)
            owner_email: Email owner
            tenant_id: ID custom (opzionale, auto-generato)

        Returns:
            TenantConfig creata
        """
        r = await self.get_redis()

        # Genera ID se non fornito
        if not tenant_id:
            tenant_id = str(uuid.uuid4())[:12]

        # Verifica che non esista
        key = self._config_key(tenant_id)
        if await r.exists(key):
            raise ValueError(f"Tenant {tenant_id} already exists")

        # Crea config con defaults per tier
        config = TenantConfig.create(
            tenant_id=tenant_id,
            name=name,
            tier=tier,
            owner_email=owner_email,
        )

        # Salva in Redis
        await r.set(key, config.model_dump_json())

        # Aggiungi a indice
        await r.sadd(self.INDEX_KEY, tenant_id)

        logger.info(
            "tenant_created",
            tenant_id=tenant_id,
            name=name,
            tier=tier.value,
        )

        return config

    async def get(self, tenant_id: str) -> TenantConfig | None:
        """
        Recupera config tenant.

        Args:
            tenant_id: ID tenant

        Returns:
            TenantConfig o None
        """
        r = await self.get_redis()
        key = self._config_key(tenant_id)

        data = await r.get(key)
        if not data:
            return None

        try:
            return TenantConfig.model_validate_json(data)
        except Exception as e:
            logger.error("tenant_parse_error", tenant_id=tenant_id, error=str(e))
            return None

    async def update(
        self,
        tenant_id: str,
        name: str | None = None,
        tier: TenantTier | None = None,
        status: TenantStatus | None = None,
        limits: TenantLimits | None = None,
        features: TenantFeatures | None = None,
    ) -> TenantConfig | None:
        """
        Aggiorna config tenant.

        Args:
            tenant_id: ID tenant
            **updates: Campi da aggiornare

        Returns:
            Config aggiornata o None se non esiste
        """
        config = await self.get(tenant_id)
        if not config:
            return None

        # Applica updates
        if name is not None:
            config.name = name
        if tier is not None:
            config.tier = tier
            # Aggiorna limiti/features per nuovo tier (opzionale)
        if status is not None:
            config.status = status
        if limits is not None:
            config.limits = limits
        if features is not None:
            config.features = features

        config.updated_at = datetime.now(UTC)

        # Salva
        r = await self.get_redis()
        await r.set(self._config_key(tenant_id), config.model_dump_json())

        logger.info("tenant_updated", tenant_id=tenant_id)

        return config

    async def delete(self, tenant_id: str, soft: bool = True) -> bool:
        """
        Elimina tenant.

        Args:
            tenant_id: ID tenant
            soft: Se True, marca come DELETED invece di eliminare

        Returns:
            True se successo
        """
        if soft:
            config = await self.update(tenant_id, status=TenantStatus.DELETED)
            return config is not None

        # Hard delete
        r = await self.get_redis()
        key = self._config_key(tenant_id)

        deleted = await r.delete(key)
        await r.srem(self.INDEX_KEY, tenant_id)

        if deleted:
            logger.warning("tenant_hard_deleted", tenant_id=tenant_id)

        return deleted > 0

    async def list_all(
        self,
        status: TenantStatus | None = None,
        tier: TenantTier | None = None,
    ) -> list[TenantConfig]:
        """
        Lista tutti i tenant.

        Args:
            status: Filtra per status
            tier: Filtra per tier

        Returns:
            Lista di TenantConfig
        """
        r = await self.get_redis()
        tenant_ids = await r.smembers(self.INDEX_KEY)

        tenants = []
        for tid in tenant_ids:
            config = await self.get(tid)
            if config:
                # Apply filters
                if status and config.status != status:
                    continue
                if tier and config.tier != tier:
                    continue
                tenants.append(config)

        return tenants

    async def exists(self, tenant_id: str) -> bool:
        """Check se tenant esiste."""
        r = await self.get_redis()
        return await r.sismember(self.INDEX_KEY, tenant_id)

    async def count(self) -> int:
        """Conta tenant totali."""
        r = await self.get_redis()
        return await r.scard(self.INDEX_KEY)

    async def ensure_default_tenant(self) -> TenantConfig:
        """
        Crea tenant di default se non esiste.

        Utile per development/testing.

        Returns:
            Config del tenant default
        """
        default_id = "default"

        config = await self.get(default_id)
        if config:
            return config

        return await self.create(
            name="Default Tenant",
            tier=TenantTier.PRO,  # Pro per avere tutte le features
            tenant_id=default_id,
        )


# Singleton
_tenant_store: TenantStore | None = None


def get_tenant_store() -> TenantStore:
    """Ottiene store globale."""
    global _tenant_store
    if _tenant_store is None:
        _tenant_store = TenantStore()
    return _tenant_store
