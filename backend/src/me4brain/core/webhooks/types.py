"""Webhook Types - Modelli Pydantic per sistema webhooks."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class WebhookEventType(str, Enum):
    """Tipi di eventi webhook supportati."""

    # Scheduler events
    JOB_CREATED = "job.created"
    JOB_COMPLETED = "job.completed"
    JOB_FAILED = "job.failed"

    # Agent events
    AGENT_HANDOFF = "agent.handoff"
    AGENT_MESSAGE = "agent.message"
    AGENT_ERROR = "agent.error"

    # System events
    SYSTEM_HEALTH = "system.health"
    SYSTEM_ALERT = "system.alert"

    # External triggers
    EXTERNAL_TRIGGER = "external.trigger"


class RetryPolicy(BaseModel):
    """Configurazione retry per webhook."""

    max_attempts: int = 3
    backoff_seconds: list[int] = Field(default_factory=lambda: [1, 5, 15])
    timeout_seconds: int = 30


class WebhookConfig(BaseModel):
    """Configurazione webhook registrato."""

    id: str
    name: str
    url: str
    events: list[str]  # Lista di WebhookEventType values
    secret: str  # Per HMAC-SHA256

    # Delivery
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    headers: dict[str, str] = Field(default_factory=dict)

    # State
    enabled: bool = True
    tenant_id: str | None = None

    # Stats
    created_at: datetime = Field(default_factory=datetime.now)
    last_triggered: datetime | None = None
    trigger_count: int = 0
    success_count: int = 0
    failure_count: int = 0


class WebhookEvent(BaseModel):
    """Evento webhook in ingresso o uscita."""

    id: str
    type: str  # WebhookEventType value
    source: str  # "scheduler", "agent", "external"
    payload: dict
    timestamp: datetime = Field(default_factory=datetime.now)

    # Security
    signature: str | None = None  # HMAC-SHA256

    # Metadata
    tenant_id: str | None = None
    correlation_id: str | None = None


class WebhookDelivery(BaseModel):
    """Record di consegna webhook."""

    id: str
    config_id: str
    event_id: str

    # Timing
    attempted_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = None

    # Result
    status: Literal["pending", "success", "failed", "retrying"]
    status_code: int | None = None
    response_body: str | None = None
    error: str | None = None

    # Retry
    attempt: int = 1
    max_attempts: int = 3
    next_retry: datetime | None = None


class CreateWebhookRequest(BaseModel):
    """Request per registrazione webhook."""

    name: str
    url: str
    events: list[str]
    secret: str | None = None  # Auto-generato se non fornito
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    headers: dict[str, str] = Field(default_factory=dict)


class WebhookResponse(BaseModel):
    """Response per webhook via API."""

    id: str
    name: str
    url: str
    events: list[str]
    enabled: bool
    trigger_count: int
    success_rate: float

    @classmethod
    def from_config(cls, config: WebhookConfig) -> WebhookResponse:
        total = config.trigger_count
        success_rate = config.success_count / total if total > 0 else 1.0
        return cls(
            id=config.id,
            name=config.name,
            url=config.url,
            events=config.events,
            enabled=config.enabled,
            trigger_count=config.trigger_count,
            success_rate=success_rate,
        )


class IncomingWebhookPayload(BaseModel):
    """Payload webhook in ingresso da esterni."""

    event_type: str
    data: dict
    timestamp: datetime | None = None
    source: str | None = None
