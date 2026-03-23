"""Webhook Store - Storage Redis per configurazioni webhook."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime

import structlog
from redis.asyncio import Redis

from me4brain.core.webhooks.types import (
    CreateWebhookRequest,
    WebhookConfig,
)

logger = structlog.get_logger(__name__)


class WebhookStore:
    """
    Storage per configurazioni webhook.

    Usa Redis hash per configurazioni persistenti.
    """

    PREFIX = "me4brain:webhooks:configs"
    INDEX_KEY = "me4brain:webhooks:index"

    def __init__(self, redis: Redis):
        """
        Inizializza store.

        Args:
            redis: Client Redis async
        """
        self.redis = redis

    def _config_key(self, config_id: str) -> str:
        """Genera chiave Redis per config."""
        return f"{self.PREFIX}:{config_id}"

    async def create(self, request: CreateWebhookRequest) -> WebhookConfig:
        """
        Crea nuova configurazione webhook.

        Args:
            request: Dati configurazione

        Returns:
            Configurazione creata
        """
        config_id = str(uuid.uuid4())[:12]

        # Genera secret se non fornito
        secret = request.secret or secrets.token_urlsafe(32)

        config = WebhookConfig(
            id=config_id,
            name=request.name,
            url=request.url,
            events=request.events,
            secret=secret,
            retry_policy=request.retry_policy,
            headers=request.headers,
        )

        # Salva
        key = self._config_key(config_id)
        await self.redis.set(key, config.model_dump_json())
        await self.redis.sadd(self.INDEX_KEY, config_id)

        logger.info(
            "webhook_config_created",
            config_id=config_id,
            name=config.name,
            events=config.events,
        )

        return config

    async def get(self, config_id: str) -> WebhookConfig | None:
        """
        Recupera configurazione per ID.

        Args:
            config_id: ID configurazione

        Returns:
            Configurazione o None
        """
        key = self._config_key(config_id)
        data = await self.redis.get(key)

        if data is None:
            return None

        return WebhookConfig.model_validate_json(data)

    async def list(
        self,
        tenant_id: str | None = None,
        enabled_only: bool = False,
    ) -> list[WebhookConfig]:
        """
        Lista tutte le configurazioni.

        Args:
            tenant_id: Filtra per tenant
            enabled_only: Solo config abilitate

        Returns:
            Lista configurazioni
        """
        config_ids = await self.redis.smembers(self.INDEX_KEY)
        configs: list[WebhookConfig] = []

        for config_id in config_ids:
            config = await self.get(config_id)
            if config is None:
                continue

            # Filtri
            if tenant_id and config.tenant_id != tenant_id:
                continue
            if enabled_only and not config.enabled:
                continue

            configs.append(config)

        return configs

    async def get_by_event(self, event_type: str) -> list[WebhookConfig]:
        """
        Trova configurazioni che ascoltano un evento.

        Args:
            event_type: Tipo evento

        Returns:
            Lista configurazioni
        """
        all_configs = await self.list(enabled_only=True)
        return [c for c in all_configs if event_type in c.events]

    async def update(self, config: WebhookConfig) -> None:
        """
        Aggiorna configurazione esistente.

        Args:
            config: Configurazione aggiornata
        """
        key = self._config_key(config.id)

        if not await self.redis.exists(key):
            raise ValueError(f"Config not found: {config.id}")

        await self.redis.set(key, config.model_dump_json())
        logger.debug("webhook_config_updated", config_id=config.id)

    async def delete(self, config_id: str) -> bool:
        """
        Elimina configurazione.

        Args:
            config_id: ID configurazione

        Returns:
            True se eliminata
        """
        key = self._config_key(config_id)

        await self.redis.srem(self.INDEX_KEY, config_id)
        count = await self.redis.delete(key)

        if count > 0:
            logger.info("webhook_config_deleted", config_id=config_id)
            return True
        return False

    async def record_trigger(
        self,
        config_id: str,
        success: bool,
    ) -> None:
        """
        Registra trigger webhook.

        Args:
            config_id: ID configurazione
            success: Esito delivery
        """
        config = await self.get(config_id)
        if config is None:
            return

        config.trigger_count += 1
        config.last_triggered = datetime.now()

        if success:
            config.success_count += 1
        else:
            config.failure_count += 1

        await self.update(config)


# Singleton
_webhook_store: WebhookStore | None = None


def get_webhook_store() -> WebhookStore | None:
    """Ottiene store globale."""
    return _webhook_store


def set_webhook_store(store: WebhookStore) -> None:
    """Imposta store globale."""
    global _webhook_store
    _webhook_store = store


async def initialize_webhook_store(
    redis_url: str = "redis://localhost:6379",
) -> WebhookStore:
    """
    Inizializza webhook store.

    Args:
        redis_url: URL connessione Redis

    Returns:
        WebhookStore inizializzato
    """
    redis = Redis.from_url(redis_url, decode_responses=True)
    store = WebhookStore(redis)
    set_webhook_store(store)
    logger.info("webhook_store_initialized", redis_url=redis_url)
    return store
