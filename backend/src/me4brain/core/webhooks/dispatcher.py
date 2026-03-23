"""Webhook Dispatcher - Invio webhook in uscita con retry."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta

import aiohttp
import structlog
from redis.asyncio import Redis

from me4brain.core.webhooks.types import (
    WebhookConfig,
    WebhookDelivery,
    WebhookEvent,
)

logger = structlog.get_logger(__name__)


class WebhookDispatcher:
    """
    Dispatcher per invio webhook in uscita.

    Responsabilità:
    - Firma HMAC-SHA256
    - Invio HTTP con timeout
    - Retry con backoff esponenziale
    - Queue per delivery fallite
    """

    FAILED_QUEUE_KEY = "me4brain:webhooks:failed"
    CONFIG_PREFIX = "me4brain:webhooks:configs"

    def __init__(
        self,
        redis: Redis | None = None,
        timeout: int = 30,
    ):
        """
        Inizializza dispatcher.

        Args:
            redis: Client Redis per queue
            timeout: Timeout HTTP in secondi
        """
        self.redis = redis
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    def sign_payload(self, payload: bytes, secret: str) -> str:
        """
        Genera HMAC-SHA256 signature.

        Args:
            payload: Payload da firmare
            secret: Secret webhook

        Returns:
            Signature in formato "sha256=xxx"
        """
        sig = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return f"sha256={sig}"

    async def dispatch(
        self,
        config: WebhookConfig,
        event: WebhookEvent,
    ) -> WebhookDelivery:
        """
        Invia webhook con retry.

        Args:
            config: Configurazione webhook
            event: Evento da inviare

        Returns:
            Record di delivery
        """
        delivery = WebhookDelivery(
            id=str(uuid.uuid4()),
            config_id=config.id,
            event_id=event.id,
            attempted_at=datetime.now(),
            status="pending",
            max_attempts=config.retry_policy.max_attempts,
        )

        # Prepara payload
        payload_dict = {
            "event_id": event.id,
            "event_type": event.type,
            "source": event.source,
            "timestamp": event.timestamp.isoformat(),
            "payload": event.payload,
        }
        payload_bytes = json.dumps(payload_dict).encode()

        # Firma
        signature = self.sign_payload(payload_bytes, config.secret)

        # Headers
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Me4BrAIn-Webhook/1.0",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": event.type,
            "X-Webhook-Delivery": delivery.id,
            **config.headers,
        }

        # Retry loop
        backoff = config.retry_policy.backoff_seconds
        max_attempts = config.retry_policy.max_attempts

        for attempt in range(1, max_attempts + 1):
            delivery.attempt = attempt

            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    async with session.post(
                        config.url,
                        data=payload_bytes,
                        headers=headers,
                    ) as response:
                        delivery.status_code = response.status

                        if response.status < 400:
                            # Success
                            delivery.status = "success"
                            delivery.completed_at = datetime.now()
                            delivery.duration_ms = (
                                delivery.completed_at - delivery.attempted_at
                            ).total_seconds() * 1000

                            logger.info(
                                "webhook_delivered",
                                config_id=config.id,
                                event_type=event.type,
                                status_code=response.status,
                                attempt=attempt,
                            )

                            return delivery

                        else:
                            # HTTP error
                            body = await response.text()
                            delivery.response_body = body[:500]
                            delivery.error = f"HTTP {response.status}"

                            logger.warning(
                                "webhook_http_error",
                                config_id=config.id,
                                status_code=response.status,
                                attempt=attempt,
                            )

            except TimeoutError:
                delivery.error = "Timeout"
                logger.warning(
                    "webhook_timeout",
                    config_id=config.id,
                    attempt=attempt,
                )

            except aiohttp.ClientError as e:
                delivery.error = str(e)
                logger.warning(
                    "webhook_client_error",
                    config_id=config.id,
                    error=str(e),
                    attempt=attempt,
                )

            except Exception as e:
                delivery.error = str(e)
                logger.error(
                    "webhook_unexpected_error",
                    config_id=config.id,
                    error=str(e),
                    attempt=attempt,
                )

            # Retry?
            if attempt < max_attempts:
                delay = backoff[min(attempt - 1, len(backoff) - 1)]
                delivery.status = "retrying"
                delivery.next_retry = datetime.now() + timedelta(seconds=delay)

                logger.debug(
                    "webhook_retry_scheduled",
                    config_id=config.id,
                    delay=delay,
                    next_attempt=attempt + 1,
                )

                await asyncio.sleep(delay)

        # Max attempts reached
        delivery.status = "failed"
        delivery.completed_at = datetime.now()

        # Queue for later retry
        await self._queue_failed(config, event, delivery)

        logger.error(
            "webhook_delivery_failed",
            config_id=config.id,
            event_type=event.type,
            attempts=max_attempts,
        )

        return delivery

    async def _queue_failed(
        self,
        config: WebhookConfig,
        event: WebhookEvent,
        delivery: WebhookDelivery,
    ) -> None:
        """Salva delivery fallita per retry manuale."""
        if not self.redis:
            return

        failed_data = {
            "config_id": config.id,
            "event": event.model_dump_json(),
            "delivery": delivery.model_dump_json(),
            "queued_at": datetime.now().isoformat(),
        }

        await self.redis.lpush(
            self.FAILED_QUEUE_KEY,
            json.dumps(failed_data),
        )

        logger.debug(
            "webhook_queued_for_retry",
            config_id=config.id,
            event_id=event.id,
        )

    async def retry_failed(self, limit: int = 10) -> int:
        """
        Riprova webhook falliti dalla queue.

        Args:
            limit: Max webhook da riprovare

        Returns:
            Numero di webhook riprovati
        """
        if not self.redis:
            return 0

        retried = 0

        for _ in range(limit):
            data = await self.redis.rpop(self.FAILED_QUEUE_KEY)
            if not data:
                break

            try:
                failed = json.loads(data)
                config_data = await self.redis.get(f"{self.CONFIG_PREFIX}:{failed['config_id']}")

                if not config_data:
                    continue

                config = WebhookConfig.model_validate_json(config_data)
                event = WebhookEvent.model_validate_json(failed["event"])

                await self.dispatch(config, event)
                retried += 1

            except Exception as e:
                logger.error("webhook_retry_error", error=str(e))

        if retried > 0:
            logger.info("webhooks_retried", count=retried)

        return retried

    async def get_failed_count(self) -> int:
        """Conta webhook falliti in queue."""
        if not self.redis:
            return 0
        return await self.redis.llen(self.FAILED_QUEUE_KEY)


# Singleton
_webhook_dispatcher: WebhookDispatcher | None = None


def get_webhook_dispatcher() -> WebhookDispatcher:
    """Ottiene o crea dispatcher globale."""
    global _webhook_dispatcher
    if _webhook_dispatcher is None:
        _webhook_dispatcher = WebhookDispatcher()
    return _webhook_dispatcher


def set_webhook_dispatcher(dispatcher: WebhookDispatcher) -> None:
    """Imposta dispatcher globale."""
    global _webhook_dispatcher
    _webhook_dispatcher = dispatcher
