"""Proactive API Routes.

Endpoint per parsing NL e gestione monitor proattivi.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.proactive.monitors import Monitor, MonitorType
from backend.proactive.nl_parser import NLMonitorParser, ParsedMonitor, is_proactive_query
from backend.proactive.scheduler import ProactiveScheduler

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/proactive", tags=["Proactive"])

# Singleton instances
_parser: NLMonitorParser | None = None
_scheduler: ProactiveScheduler | None = None


def get_parser() -> NLMonitorParser:
    """Get parser singleton."""
    global _parser
    if _parser is None:
        _parser = NLMonitorParser()
    return _parser


def get_scheduler() -> ProactiveScheduler:
    """Get scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = ProactiveScheduler()
        _scheduler.start()
    return _scheduler


# =============================================================================
# Request/Response Models
# =============================================================================


class ParseRequest(BaseModel):
    """Request per parsing NL."""

    query: str = Field(..., min_length=5, max_length=1000)


class ParseResponse(BaseModel):
    """Response parsing NL."""

    type: str
    name: str
    description: str
    schedule: str | None
    interval_seconds: int | None
    config: dict[str, Any]
    notify_channels: list[str]
    confidence: float
    raw_query: str


class CreateMonitorRequest(BaseModel):
    """Request per creazione monitor."""

    user_id: str = "default"
    type: str
    name: str
    description: str
    schedule: str | None = "*/5 * * * *"
    config: dict[str, Any] = Field(default_factory=dict)
    notify_channels: list[str] = Field(default_factory=lambda: ["web"])


class MonitorResponse(BaseModel):
    """Response con dati monitor."""

    id: str
    user_id: str
    type: str
    name: str
    description: str
    state: str
    schedule: str | None
    config: dict[str, Any]
    notify_channels: list[str]
    created_at: str


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/parse", response_model=ParseResponse)
async def parse_nl_query(request: ParseRequest) -> ParseResponse:
    """Parse query NL → Monitor config.

    Esempi:
    - "avvisami quando BTC scende sotto 70k"
    - "ogni mattina alle 9 verifica il calendario"
    """
    parser = get_parser()

    parsed = parser.parse(request.query)
    if not parsed:
        raise HTTPException(
            status_code=400,
            detail="Unable to parse query as proactive intent",
        )

    return ParseResponse(
        type=parsed.type.value,
        name=parsed.name,
        description=parsed.description,
        schedule=parsed.schedule,
        interval_seconds=parsed.interval_seconds,
        config=parsed.config,
        notify_channels=parsed.notify_channels,
        confidence=parsed.confidence,
        raw_query=parsed.raw_query,
    )


@router.post("/monitors", response_model=MonitorResponse)
async def create_monitor(request: CreateMonitorRequest) -> MonitorResponse:
    """Crea un nuovo monitor."""
    scheduler = get_scheduler()

    # Map string type to enum
    try:
        monitor_type = MonitorType(request.type)
    except ValueError:
        monitor_type = MonitorType.SCHEDULED

    # Crea Monitor object
    monitor = Monitor(
        user_id=request.user_id,
        type=monitor_type,
        name=request.name,
        description=request.description,
        schedule=request.schedule,
        config=request.config,
        notify_channels=request.notify_channels,
    )

    # Registra nello scheduler
    monitor_id = scheduler.create_monitor(monitor)
    monitor.id = monitor_id

    logger.info(
        "monitor_created",
        monitor_id=monitor_id,
        type=request.type,
        name=request.name,
    )

    return MonitorResponse(
        id=monitor.id,
        user_id=monitor.user_id,
        type=monitor.type.value,
        name=monitor.name,
        description=monitor.description,
        state=monitor.state.value,
        schedule=monitor.schedule,
        config=monitor.config,
        notify_channels=monitor.notify_channels,
        created_at=monitor.created_at.isoformat(),
    )


@router.get("/monitors")
async def list_monitors(user_id: str | None = None) -> dict[str, Any]:
    """Lista monitor, opzionalmente filtrati per user."""
    scheduler = get_scheduler()
    monitors = scheduler.list_monitors(user_id)

    return {
        "monitors": [
            MonitorResponse(
                id=m.id,
                user_id=m.user_id,
                type=m.type.value,
                name=m.name,
                description=m.description,
                state=m.state.value,
                schedule=m.schedule,
                config=m.config,
                notify_channels=m.notify_channels,
                created_at=m.created_at.isoformat(),
            ).model_dump()
            for m in monitors
        ],
        "total": len(monitors),
    }


@router.get("/monitors/{monitor_id}", response_model=MonitorResponse)
async def get_monitor(monitor_id: str) -> MonitorResponse:
    """Ottiene dettagli monitor."""
    scheduler = get_scheduler()
    monitor = scheduler.get_monitor(monitor_id)

    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    return MonitorResponse(
        id=monitor.id,
        user_id=monitor.user_id,
        type=monitor.type.value,
        name=monitor.name,
        description=monitor.description,
        state=monitor.state.value,
        schedule=monitor.schedule,
        config=monitor.config,
        notify_channels=monitor.notify_channels,
        created_at=monitor.created_at.isoformat(),
    )


@router.delete("/monitors/{monitor_id}")
async def delete_monitor(monitor_id: str) -> dict[str, str]:
    """Elimina monitor."""
    scheduler = get_scheduler()

    if not scheduler.get_monitor(monitor_id):
        raise HTTPException(status_code=404, detail="Monitor not found")

    scheduler.delete_monitor(monitor_id)
    return {"message": "Monitor deleted"}


@router.post("/monitors/{monitor_id}/pause", response_model=MonitorResponse)
async def pause_monitor(monitor_id: str) -> MonitorResponse:
    """Pausa monitor."""
    scheduler = get_scheduler()
    scheduler.pause_monitor(monitor_id)

    monitor = scheduler.get_monitor(monitor_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    return MonitorResponse(
        id=monitor.id,
        user_id=monitor.user_id,
        type=monitor.type.value,
        name=monitor.name,
        description=monitor.description,
        state=monitor.state.value,
        schedule=monitor.schedule,
        config=monitor.config,
        notify_channels=monitor.notify_channels,
        created_at=monitor.created_at.isoformat(),
    )


@router.post("/monitors/{monitor_id}/resume", response_model=MonitorResponse)
async def resume_monitor(monitor_id: str) -> MonitorResponse:
    """Riprende monitor pausato."""
    scheduler = get_scheduler()
    scheduler.resume_monitor(monitor_id)

    monitor = scheduler.get_monitor(monitor_id)
    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    return MonitorResponse(
        id=monitor.id,
        user_id=monitor.user_id,
        type=monitor.type.value,
        name=monitor.name,
        description=monitor.description,
        state=monitor.state.value,
        schedule=monitor.schedule,
        config=monitor.config,
        notify_channels=monitor.notify_channels,
        created_at=monitor.created_at.isoformat(),
    )


@router.get("/stats")
async def get_stats() -> dict[str, Any]:
    """Statistiche proactive system."""
    scheduler = get_scheduler()
    return scheduler.get_stats()


@router.post("/check-intent")
async def check_proactive_intent(request: ParseRequest) -> dict[str, Any]:
    """Quick check se query ha intent proattivo (senza parsing completo)."""
    parser = get_parser()
    result = parser.detect_proactive_intent(request.query)

    return {
        "is_proactive": result.is_proactive,
        "confidence": result.confidence,
        "trigger_phrase": result.trigger_phrase,
    }
