"""Webhook Receiver - Ricezione e validazione webhook in ingresso."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import datetime
from typing import Callable, Optional

import structlog

from me4brain.core.webhooks.types import (
    IncomingWebhookPayload,
    WebhookEvent,
    WebhookEventType,
)

logger = structlog.get_logger(__name__)


class WebhookReceiver:
    """
    Receiver per webhook in ingresso.

    Responsabilità:
    - Validazione HMAC-SHA256
    - Parsing payload
    - Dispatch a handler appropriato
    """

    def __init__(
        self,
        secret: Optional[str] = None,
        handler: Optional[Callable[[WebhookEvent], None]] = None,
    ):
        """
        Inizializza receiver.

        Args:
            secret: Secret per validazione HMAC (opzionale per dev)
            handler: Callback per processare eventi
        """
        self.secret = secret
        self.handler = handler
        self._event_handlers: dict[str, list[Callable]] = {}

    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        secret: Optional[str] = None,
    ) -> bool:
        """
        Verifica HMAC-SHA256 signature.

        Args:
            payload: Body della request in bytes
            signature: Signature header (es. "sha256=abc123...")
            secret: Secret per HMAC (default: self.secret)

        Returns:
            True se signature valida
        """
        secret_key = secret or self.secret
        if not secret_key:
            logger.warning("webhook_no_secret_configured")
            return True  # Dev mode: skip validation

        # Supporta formato "sha256=xxx" o solo "xxx"
        if signature.startswith("sha256="):
            signature = signature[7:]

        expected = hmac.new(
            secret_key.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        is_valid = hmac.compare_digest(expected, signature)

        if not is_valid:
            logger.warning(
                "webhook_signature_invalid",
                expected_prefix=expected[:8],
                received_prefix=signature[:8] if signature else "none",
            )

        return is_valid

    async def receive(
        self,
        payload: IncomingWebhookPayload,
        raw_body: Optional[bytes] = None,
        signature: Optional[str] = None,
    ) -> WebhookEvent:
        """
        Riceve e processa webhook in ingresso.

        Args:
            payload: Payload parsato
            raw_body: Body originale per verifica signature
            signature: Signature header

        Returns:
            WebhookEvent creato

        Raises:
            ValueError: Se signature invalida
        """
        # Verifica signature se presente
        if signature and raw_body:
            if not self.verify_signature(raw_body, signature):
                raise ValueError("Invalid webhook signature")

        # Crea evento
        event = WebhookEvent(
            id=str(uuid.uuid4()),
            type=payload.event_type,
            source=payload.source or "external",
            payload=payload.data,
            timestamp=payload.timestamp or datetime.now(),
        )

        logger.info(
            "webhook_received",
            event_id=event.id,
            event_type=event.type,
            source=event.source,
        )

        # Dispatch a handler
        await self.process_event(event)

        return event

    async def process_event(self, event: WebhookEvent) -> None:
        """
        Processa evento con handler registrati.

        Args:
            event: Evento da processare
        """
        # Handler globale
        if self.handler:
            try:
                result = self.handler(event)
                # Support async handlers
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.error(
                    "webhook_handler_error",
                    event_id=event.id,
                    error=str(e),
                )

        # Handler specifici per tipo
        handlers = self._event_handlers.get(event.type, [])
        for handler in handlers:
            try:
                result = handler(event)
                if hasattr(result, "__await__"):
                    await result
            except Exception as e:
                logger.error(
                    "webhook_type_handler_error",
                    event_id=event.id,
                    event_type=event.type,
                    error=str(e),
                )

    def on_event(self, event_type: str) -> Callable:
        """
        Decorator per registrare handler per tipo evento.

        Usage:
            @receiver.on_event("job.completed")
            async def handle_job_completed(event):
                ...
        """

        def decorator(func: Callable) -> Callable:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = []
            self._event_handlers[event_type].append(func)
            return func

        return decorator

    def generate_signature(self, payload: bytes, secret: Optional[str] = None) -> str:
        """
        Genera HMAC-SHA256 signature per payload.

        Args:
            payload: Payload da firmare
            secret: Secret per HMAC

        Returns:
            Signature in formato "sha256=xxx"
        """
        secret_key = secret or self.secret
        if not secret_key:
            raise ValueError("No secret configured")

        sig = hmac.new(
            secret_key.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return f"sha256={sig}"


# Singleton
_webhook_receiver: Optional[WebhookReceiver] = None


def get_webhook_receiver() -> WebhookReceiver:
    """Ottiene o crea receiver globale."""
    global _webhook_receiver
    if _webhook_receiver is None:
        _webhook_receiver = WebhookReceiver()
    return _webhook_receiver


def set_webhook_receiver(receiver: WebhookReceiver) -> None:
    """Imposta receiver globale."""
    global _webhook_receiver
    _webhook_receiver = receiver
