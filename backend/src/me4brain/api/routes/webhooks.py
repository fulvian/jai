"""Webhooks API Routes - Endpoint REST per gestione webhooks."""

from __future__ import annotations

from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException, Request

from me4brain.core.webhooks.dispatcher import get_webhook_dispatcher
from me4brain.core.webhooks.receiver import get_webhook_receiver
from me4brain.core.webhooks.store import get_webhook_store
from me4brain.core.webhooks.types import (
    CreateWebhookRequest,
    IncomingWebhookPayload,
    WebhookResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])


def _get_store():
    """Dependency injection per store."""
    store = get_webhook_store()
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="Webhook store not initialized",
        )
    return store


# --- Webhook Configs ---


@router.post("/configs", response_model=WebhookResponse)
async def create_webhook_config(request: CreateWebhookRequest) -> WebhookResponse:
    """
    Registra nuova configurazione webhook.

    Args:
        request: Dati configurazione

    Returns:
        Configurazione creata
    """
    store = _get_store()
    config = await store.create(request)

    logger.info(
        "webhook_config_created_via_api",
        config_id=config.id,
        name=config.name,
    )

    return WebhookResponse.from_config(config)


@router.get("/configs", response_model=list[WebhookResponse])
async def list_webhook_configs(
    tenant_id: Optional[str] = None,
    enabled_only: bool = False,
) -> list[WebhookResponse]:
    """
    Lista configurazioni webhook.

    Args:
        tenant_id: Filtra per tenant
        enabled_only: Solo config abilitate

    Returns:
        Lista configurazioni
    """
    store = _get_store()
    configs = await store.list(tenant_id=tenant_id, enabled_only=enabled_only)
    return [WebhookResponse.from_config(c) for c in configs]


@router.get("/configs/{config_id}", response_model=WebhookResponse)
async def get_webhook_config(config_id: str) -> WebhookResponse:
    """
    Dettaglio singola configurazione.

    Args:
        config_id: ID configurazione

    Returns:
        Dettaglio configurazione
    """
    store = _get_store()
    config = await store.get(config_id)

    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")

    return WebhookResponse.from_config(config)


@router.patch("/configs/{config_id}", response_model=WebhookResponse)
async def toggle_webhook_config(config_id: str, enabled: bool) -> WebhookResponse:
    """
    Abilita/disabilita configurazione.

    Args:
        config_id: ID configurazione
        enabled: Nuovo stato

    Returns:
        Configurazione aggiornata
    """
    store = _get_store()
    config = await store.get(config_id)

    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")

    config.enabled = enabled
    await store.update(config)

    logger.info("webhook_config_toggled", config_id=config_id, enabled=enabled)
    return WebhookResponse.from_config(config)


@router.delete("/configs/{config_id}")
async def delete_webhook_config(config_id: str) -> dict[str, str]:
    """
    Elimina configurazione.

    Args:
        config_id: ID configurazione

    Returns:
        Messaggio conferma
    """
    store = _get_store()
    success = await store.delete(config_id)

    if not success:
        raise HTTPException(status_code=404, detail="Config not found")

    logger.info("webhook_config_deleted_via_api", config_id=config_id)
    return {"message": f"Config {config_id} deleted"}


# --- Incoming Webhooks ---


@router.post("/receive")
async def receive_webhook(
    payload: IncomingWebhookPayload,
    request: Request,
) -> dict[str, str]:
    """
    Riceve webhook esterni.

    Headers supportati:
    - X-Webhook-Signature: HMAC-SHA256 signature
    - X-Webhook-Secret: Secret per verifica (alternativa)

    Args:
        payload: Payload webhook
        request: FastAPI request

    Returns:
        Conferma ricezione
    """
    receiver = get_webhook_receiver()

    # Leggi signature da header
    signature = request.headers.get("X-Webhook-Signature")

    # Leggi raw body per verifica firma
    raw_body = await request.body()

    try:
        event = await receiver.receive(
            payload=payload,
            raw_body=raw_body,
            signature=signature,
        )

        return {
            "status": "received",
            "event_id": event.id,
        }

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


# --- Stats & Debug ---


@router.get("/stats")
async def get_webhook_stats() -> dict:
    """
    Statistiche webhooks.

    Returns:
        Stats globali
    """
    store = _get_store()
    dispatcher = get_webhook_dispatcher()

    configs = await store.list()
    failed_count = await dispatcher.get_failed_count()

    total_triggers = sum(c.trigger_count for c in configs)
    total_success = sum(c.success_count for c in configs)
    total_failures = sum(c.failure_count for c in configs)

    return {
        "total_configs": len(configs),
        "enabled_configs": len([c for c in configs if c.enabled]),
        "total_triggers": total_triggers,
        "total_success": total_success,
        "total_failures": total_failures,
        "success_rate": total_success / total_triggers if total_triggers > 0 else 1.0,
        "pending_retries": failed_count,
    }


@router.post("/retry-failed")
async def retry_failed_webhooks(limit: int = 10) -> dict[str, int]:
    """
    Riprova webhook falliti.

    Args:
        limit: Max webhook da riprovare

    Returns:
        Numero riprovati
    """
    dispatcher = get_webhook_dispatcher()
    retried = await dispatcher.retry_failed(limit=limit)

    return {"retried": retried}
