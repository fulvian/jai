"""Arq Worker - Worker background per esecuzione job schedulati."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from arq import cron
from arq.connections import RedisSettings

from me4brain.core.scheduler.cron import ScheduleParser
from me4brain.core.scheduler.delivery import DeliveryService, get_delivery_service
from me4brain.core.scheduler.store import JobStore, get_job_store
from me4brain.core.scheduler.types import ScheduleType

logger = structlog.get_logger(__name__)


async def execute_scheduled_job(
    ctx: dict[str, Any],
    job_id: str,
) -> dict[str, Any]:
    """
    Esegue un job schedulato.

    Questo è la funzione registrata in Arq che viene
    eseguita quando un job è pronto.

    Args:
        ctx: Contesto Arq (contiene redis, store, ecc.)
        job_id: ID del job da eseguire

    Returns:
        Risultato esecuzione
    """
    store: JobStore = ctx.get("store") or get_job_store()
    delivery: DeliveryService = ctx.get("delivery") or get_delivery_service()
    parser = ScheduleParser()

    if store is None:
        logger.error("job_store_not_initialized")
        return {"error": "Job store not initialized"}

    # Recupera job
    job = await store.get(job_id)
    if job is None:
        logger.warning("job_not_found", job_id=job_id)
        return {"error": f"Job not found: {job_id}"}

    if not job.enabled:
        logger.info("job_disabled", job_id=job_id)
        return {"skipped": True, "reason": "disabled"}

    logger.info(
        "job_execution_started",
        job_id=job_id,
        job_name=job.name,
        action=job.payload.action,
    )

    result: dict[str, Any] = {}
    success = False

    try:
        # Esegui azione
        # Per ora, simuliamo l'esecuzione via cognitive pipeline
        # In produzione, qui chiameremo il CognitivePipeline
        pipeline_executor = ctx.get("pipeline")
        if pipeline_executor:
            result = await pipeline_executor(
                action=job.payload.action,
                params=job.payload.params,
            )
            success = result.get("success", True)
        else:
            # Fallback: log only
            logger.info(
                "job_action_executed",
                action=job.payload.action,
                params=job.payload.params,
            )
            result = {
                "action": job.payload.action,
                "params": job.payload.params,
                "executed_at": datetime.now().isoformat(),
            }
            success = True

    except Exception as e:
        logger.error(
            "job_execution_error",
            job_id=job_id,
            error=str(e),
        )
        result = {"error": str(e)}
        success = False

    # Calcola next_run
    next_run: datetime | None = None
    if job.schedule.type != ScheduleType.AT:
        # Per cron e every, calcola prossimo run
        next_run = parser.next_run(job)

    # Aggiorna job
    await store.mark_executed(job_id, success=success, next_run=next_run)

    # Delivery
    await delivery.deliver(
        config=job.delivery,
        job_name=job.name,
        result=result,
        success=success,
    )

    logger.info(
        "job_execution_completed",
        job_id=job_id,
        success=success,
        next_run=next_run.isoformat() if next_run else None,
    )

    return result


async def check_pending_jobs(ctx: dict[str, Any]) -> int:
    """
    Cron job: controlla job pendenti ed enqueue esecuzione.

    Eseguito ogni 15 minuti da Arq.

    Args:
        ctx: Contesto Arq

    Returns:
        Numero di job enqueued
    """
    store: JobStore = ctx.get("store") or get_job_store()

    if store is None:
        logger.warning("job_store_not_available")
        return 0

    now = datetime.now()
    pending = await store.get_pending(before=now)

    logger.debug(
        "checking_pending_jobs",
        count=len(pending),
        timestamp=now.isoformat(),
    )

    enqueued = 0
    for job in pending:
        try:
            # Enqueue in Arq
            await ctx["redis"].enqueue_job(
                "execute_scheduled_job",
                job.id,
                _job_id=f"job:{job.id}",  # Deduplicazione
            )
            enqueued += 1
            logger.info(
                "job_enqueued",
                job_id=job.id,
                job_name=job.name,
            )
        except Exception as e:
            logger.error(
                "job_enqueue_error",
                job_id=job.id,
                error=str(e),
            )

    if enqueued > 0:
        logger.info("pending_jobs_enqueued", count=enqueued)

    return enqueued


async def startup(ctx: dict[str, Any]) -> None:
    """
    Hook startup Arq.

    Inizializza dipendenze nel contesto.
    """
    from me4brain.core.scheduler.store import initialize_job_store

    # Inizializza store
    store = await initialize_job_store()
    ctx["store"] = store
    ctx["delivery"] = get_delivery_service()

    logger.info("arq_worker_started")


async def shutdown(ctx: dict[str, Any]) -> None:
    """Hook shutdown Arq."""
    logger.info("arq_worker_stopped")


class WorkerSettings:
    """
    Configurazione Arq Worker.

    Uso:
        arq me4brain.core.scheduler.worker.WorkerSettings
    """

    # Funzioni registrate
    functions = [execute_scheduled_job]

    # Cron jobs (check ogni 15 minuti)
    cron_jobs = [
        cron(
            check_pending_jobs,
            minute={0, 15, 30, 45},
            run_at_startup=True,
        ),
    ]

    # Redis settings
    redis_settings = RedisSettings()

    # Concurrency
    max_jobs = 10

    # Retry
    max_tries = 3

    # Timeout
    job_timeout = 300  # 5 minuti

    # Hooks
    on_startup = startup
    on_shutdown = shutdown
