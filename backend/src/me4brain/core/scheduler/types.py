"""Scheduler Types - Modelli Pydantic per job scheduling."""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ScheduleType(str, Enum):
    """Tipi di schedule supportati."""

    CRON = "cron"  # Espressione cron: "0 7 * * 1-5"
    AT = "at"  # One-shot datetime ISO: "2024-02-03T10:00:00"
    EVERY = "every"  # Intervallo: "6h", "30m", "1d"


class JobPayload(BaseModel):
    """Payload dell'azione da eseguire."""

    action: str
    params: dict = Field(default_factory=dict)


class DeliveryConfig(BaseModel):
    """Configurazione delivery channels."""

    channels: list[Literal["log", "webhook"]] = Field(default_factory=lambda: ["log"])
    webhook_url: Optional[str] = None
    webhook_headers: dict[str, str] = Field(default_factory=dict)


class ScheduleConfig(BaseModel):
    """Configurazione schedule."""

    type: ScheduleType
    expression: str  # "0 7 * * 1-5" | "2024-02-03T10:00" | "6h"
    timezone: str = "Europe/Rome"


class ScheduledJob(BaseModel):
    """Modello principale per job schedulati."""

    id: str
    name: str
    description: Optional[str] = None
    schedule: ScheduleConfig
    payload: JobPayload
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)

    # Multi-tenancy
    tenant_id: Optional[str] = None

    # Stato
    enabled: bool = True
    next_run: Optional[datetime] = None
    last_run: Optional[datetime] = None

    # Statistiche
    run_count: int = 0
    success_count: int = 0
    failure_count: int = 0

    # Retry
    max_retries: int = 3

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None

    @property
    def success_rate(self) -> float:
        """Calcola success rate."""
        if self.run_count == 0:
            return 1.0
        return self.success_count / self.run_count


class JobStatus(str, Enum):
    """Stato esecuzione job."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRYING = "retrying"


class ExecutionLog(BaseModel):
    """Log esecuzione per auditing (PostgreSQL)."""

    id: str
    job_id: str
    job_name: str

    # Timing
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None

    # Risultato
    status: JobStatus
    result: Optional[dict] = None
    error: Optional[str] = None

    # Retry info
    attempt: int = 1
    max_attempts: int = 3

    # Context
    tenant_id: Optional[str] = None


class CreateJobRequest(BaseModel):
    """Request per creazione job via API."""

    name: str
    description: Optional[str] = None
    schedule: ScheduleConfig
    payload: JobPayload
    delivery: DeliveryConfig = Field(default_factory=DeliveryConfig)
    enabled: bool = True


class JobResponse(BaseModel):
    """Response per job via API."""

    id: str
    name: str
    description: Optional[str]
    schedule: ScheduleConfig
    enabled: bool
    next_run: Optional[datetime]
    last_run: Optional[datetime]
    run_count: int
    success_rate: float

    @classmethod
    def from_job(cls, job: ScheduledJob) -> "JobResponse":
        return cls(
            id=job.id,
            name=job.name,
            description=job.description,
            schedule=job.schedule,
            enabled=job.enabled,
            next_run=job.next_run,
            last_run=job.last_run,
            run_count=job.run_count,
            success_rate=job.success_rate,
        )
