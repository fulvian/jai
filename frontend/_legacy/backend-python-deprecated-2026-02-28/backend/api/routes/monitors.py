"""Monitors API Routes.

Endpoints REST per gestione monitor proattivi.
"""

import os
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Query

from backend.proactive.evaluator import MonitorEvaluator
from backend.proactive.monitors import (
    CreateMonitorRequest,
    EvaluationResult,
    Monitor,
    MonitorListResponse,
    MonitorState,
    MonitorStatsResponse,
)
from backend.proactive.notifications import NotificationDispatcher, format_stock_alert
from backend.proactive.scheduler import ProactiveScheduler

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/monitors", tags=["monitors"])


# =============================================================================
# Singleton Instances
# =============================================================================

_scheduler: ProactiveScheduler | None = None
_evaluator: MonitorEvaluator | None = None
_dispatcher: NotificationDispatcher | None = None


async def get_scheduler() -> ProactiveScheduler:
    """Lazy init scheduler singleton."""
    global _scheduler
    if _scheduler is None:
        # Usa Redis solo se REDIS_URL e REDIS_PASSWORD sono configurati
        redis_url = os.getenv("REDIS_URL")
        redis_password = os.getenv("REDIS_PASSWORD")

        # Se Redis è configurato con password, costruisci URL completo
        if redis_url and redis_password:
            # Inserisci password nell'URL: redis://:password@host:port
            parts = redis_url.replace("redis://", "").split(":")
            if len(parts) >= 1:
                host = parts[0] if "@" not in parts[0] else parts[0].split("@")[1]
                port = parts[1] if len(parts) > 1 else "6379"
                redis_url = f"redis://:{redis_password}@{host}:{port}"
        elif redis_url and not redis_password:
            # Redis configurato ma senza password, usa memory fallback
            logger.warning("proactive_redis_no_password", msg="Using memory fallback")
            redis_url = None

        _scheduler = ProactiveScheduler(
            redis_url=redis_url,
            on_evaluate=_on_monitor_evaluate,
        )
        await _scheduler.start()
        logger.info("proactive_scheduler_initialized", redis=bool(redis_url))
    return _scheduler


async def get_evaluator() -> MonitorEvaluator:
    """Lazy init evaluator singleton."""
    global _evaluator
    if _evaluator is None:
        me4brain_url = os.getenv("ME4BRAIN_URL", "http://localhost:8000")
        nanogpt_key = os.getenv("NANOGPT_API_KEY")
        _evaluator = MonitorEvaluator(
            me4brain_url=me4brain_url,
            nanogpt_api_key=nanogpt_key,
        )
        logger.info("proactive_evaluator_initialized")
    return _evaluator


async def get_dispatcher() -> NotificationDispatcher:
    """Lazy init dispatcher singleton."""
    global _dispatcher
    if _dispatcher is None:
        _dispatcher = NotificationDispatcher(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN"),
            slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
        )
        logger.info("proactive_dispatcher_initialized")
    return _dispatcher


async def _on_monitor_evaluate(monitor: Monitor) -> None:
    """Callback chiamato dallo scheduler per ogni evaluation."""
    evaluator = await get_evaluator()
    dispatcher = await get_dispatcher()

    # Esegui valutazione
    result = await evaluator.evaluate(monitor)

    # Salva risultato nella history del monitor
    monitor.add_evaluation(result)

    # Se trigger, invia notifiche
    if result.trigger and result.decision:
        title, message = format_stock_alert(
            ticker=monitor.config.get("ticker", "N/A"),
            recommendation=result.decision.recommendation,
            confidence=result.decision.confidence,
            reasoning=result.decision.reasoning,
            key_factors=result.decision.key_factors,
            suggested_action=result.decision.suggested_action,
        )

        await dispatcher.dispatch(
            user_id=monitor.user_id,
            channels=monitor.notify_channels,
            title=title,
            message=message,
            data={"monitor_id": monitor.id, "result": result.model_dump()},
        )

        logger.info(
            "monitor_triggered",
            monitor_id=monitor.id,
            recommendation=result.decision.recommendation,
        )


# =============================================================================
# CRUD Endpoints
# =============================================================================


@router.post("/", response_model=Monitor)
async def create_monitor(request: CreateMonitorRequest) -> Monitor:
    """Crea un nuovo monitor proattivo.

    Esempi:
    - PRICE_WATCH: {"ticker": "AAPL", "condition": "below", "threshold": 180}
    - AUTONOMOUS: {"ticker": "AAPL", "goal": "buy", "min_confidence": 70}
    - SCHEDULED: {"cron_expression": "0 9 * * MON", "task": "Analizza portafoglio"}
    """
    scheduler = await get_scheduler()

    # Crea monitor
    monitor = Monitor(
        user_id="default",  # TODO: Get from auth
        type=request.type,
        name=request.name,
        description=request.description,
        config=request.config,
        interval_minutes=request.interval_minutes,
        notify_channels=request.notify_channels,
    )

    # Schedula
    await scheduler.create_monitor(monitor)

    logger.info(
        "monitor_created_api",
        monitor_id=monitor.id,
        type=request.type.value,
    )

    return monitor


@router.get("/", response_model=MonitorListResponse)
async def list_monitors(
    user_id: str | None = Query(None, description="Filter by user"),
    state: MonitorState | None = Query(None, description="Filter by state"),
) -> MonitorListResponse:
    """Lista tutti i monitor."""
    scheduler = await get_scheduler()

    monitors = await scheduler.list_monitors(user_id=user_id)

    # Filter by state if specified
    if state:
        monitors = [m for m in monitors if m.state == state]

    active_count = sum(1 for m in monitors if m.state == MonitorState.ACTIVE)
    paused_count = sum(1 for m in monitors if m.state == MonitorState.PAUSED)

    return MonitorListResponse(
        monitors=monitors,
        total=len(monitors),
        active_count=active_count,
        paused_count=paused_count,
    )


@router.get("/stats", response_model=MonitorStatsResponse)
async def get_monitor_stats() -> MonitorStatsResponse:
    """Statistiche aggregate dei monitor."""
    scheduler = await get_scheduler()
    stats = await scheduler.get_stats()

    return MonitorStatsResponse(
        total_monitors=stats["total_monitors"],
        active_monitors=stats["active_monitors"],
        total_checks=stats["total_checks"],
        total_triggers=stats["total_triggers"],
        by_type=stats["by_type"],
    )


@router.get("/{monitor_id}", response_model=Monitor)
async def get_monitor(monitor_id: str) -> Monitor:
    """Ottiene dettagli di un monitor specifico."""
    scheduler = await get_scheduler()
    monitor = await scheduler.get_monitor(monitor_id)

    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    return monitor


@router.patch("/{monitor_id}/pause")
async def pause_monitor(monitor_id: str) -> dict[str, Any]:
    """Pausa un monitor attivo."""
    scheduler = await get_scheduler()
    success = await scheduler.pause_monitor(monitor_id)

    if not success:
        raise HTTPException(status_code=404, detail="Monitor not found")

    return {"success": True, "monitor_id": monitor_id, "state": "paused"}


@router.patch("/{monitor_id}/resume")
async def resume_monitor(monitor_id: str) -> dict[str, Any]:
    """Riprende un monitor pausato."""
    scheduler = await get_scheduler()
    success = await scheduler.resume_monitor(monitor_id)

    if not success:
        raise HTTPException(status_code=404, detail="Monitor not found")

    return {"success": True, "monitor_id": monitor_id, "state": "active"}


@router.post("/{monitor_id}/trigger")
async def trigger_immediate(monitor_id: str) -> dict[str, Any]:
    """Forza valutazione immediata di un monitor."""
    scheduler = await get_scheduler()
    success = await scheduler.trigger_immediate(monitor_id)

    if not success:
        raise HTTPException(status_code=404, detail="Monitor not found")

    return {"success": True, "monitor_id": monitor_id, "message": "Evaluation triggered"}


@router.delete("/{monitor_id}")
async def delete_monitor(monitor_id: str) -> dict[str, Any]:
    """Elimina un monitor."""
    scheduler = await get_scheduler()
    success = await scheduler.delete_monitor(monitor_id)

    if not success:
        raise HTTPException(status_code=404, detail="Monitor not found")

    return {"success": True, "monitor_id": monitor_id, "deleted": True}


@router.get("/{monitor_id}/history", response_model=list[EvaluationResult])
async def get_monitor_history(
    monitor_id: str,
    limit: int = Query(10, ge=1, le=100),
) -> list[EvaluationResult]:
    """Ottiene storico valutazioni di un monitor."""
    scheduler = await get_scheduler()
    monitor = await scheduler.get_monitor(monitor_id)

    if not monitor:
        raise HTTPException(status_code=404, detail="Monitor not found")

    return monitor.history[:limit]
