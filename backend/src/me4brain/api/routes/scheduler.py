"""Scheduler API Routes - Endpoint REST per gestione job schedulati."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

import structlog
from fastapi import APIRouter, HTTPException

from me4brain.core.scheduler.cron import ScheduleParser
from me4brain.core.scheduler.store import JobStore, get_job_store
from me4brain.core.scheduler.types import (
    CreateJobRequest,
    JobResponse,
    ScheduledJob,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/v1/scheduler", tags=["scheduler"])


def _get_store() -> JobStore:
    """Dependency injection per store."""
    store = get_job_store()
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="Scheduler not initialized",
        )
    return store


@router.post("/jobs", response_model=JobResponse)
async def create_job(request: CreateJobRequest) -> JobResponse:
    """
    Crea un nuovo job schedulato.

    Args:
        request: Dati del job

    Returns:
        Job creato
    """
    store = _get_store()
    parser = ScheduleParser()

    # Genera ID
    job_id = hashlib.sha256(
        f"{request.name}:{datetime.now().isoformat()}".encode()
    ).hexdigest()[:12]

    # Crea job
    job = ScheduledJob(
        id=job_id,
        name=request.name,
        description=request.description,
        schedule=request.schedule,
        payload=request.payload,
        delivery=request.delivery,
        enabled=request.enabled,
    )

    # Calcola next_run
    try:
        job.next_run = parser.next_run(job)
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid schedule: {e}",
        )

    # Salva
    await store.create(job)

    logger.info(
        "job_created_via_api",
        job_id=job.id,
        name=job.name,
        next_run=job.next_run.isoformat() if job.next_run else None,
    )

    return JobResponse.from_job(job)


@router.get("/jobs", response_model=list[JobResponse])
async def list_jobs(
    tenant_id: Optional[str] = None,
    enabled_only: bool = False,
) -> list[JobResponse]:
    """
    Lista tutti i job.

    Args:
        tenant_id: Filtra per tenant
        enabled_only: Solo job abilitati

    Returns:
        Lista job
    """
    store = _get_store()

    jobs = await store.list(tenant_id=tenant_id, enabled_only=enabled_only)
    return [JobResponse.from_job(j) for j in jobs]


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str) -> JobResponse:
    """
    Dettaglio singolo job.

    Args:
        job_id: ID del job

    Returns:
        Dettaglio job
    """
    store = _get_store()

    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobResponse.from_job(job)


@router.post("/jobs/{job_id}/run")
async def run_job_now(job_id: str) -> dict[str, str]:
    """
    Esegue un job immediatamente.

    Args:
        job_id: ID del job

    Returns:
        Messaggio conferma
    """
    store = _get_store()

    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Enqueue diretto in Arq
    # In produzione, useremo il pool Arq
    # Per ora, eseguiamo inline
    from me4brain.core.scheduler.worker import execute_scheduled_job

    try:
        result = await execute_scheduled_job(
            ctx={"store": store},
            job_id=job_id,
        )
        logger.info("job_run_manually", job_id=job_id)
        return {"message": f"Job {job_id} executed", "result": str(result)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/jobs/{job_id}", response_model=JobResponse)
async def toggle_job(job_id: str, enabled: bool) -> JobResponse:
    """
    Abilita/disabilita un job.

    Args:
        job_id: ID del job
        enabled: Nuovo stato

    Returns:
        Job aggiornato
    """
    store = _get_store()
    parser = ScheduleParser()

    job = await store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    job.enabled = enabled

    # Ricalcola next_run se abilitato
    if enabled:
        job.next_run = parser.next_run(job)
    else:
        job.next_run = None

    await store.update(job)

    logger.info("job_toggled", job_id=job_id, enabled=enabled)
    return JobResponse.from_job(job)


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str) -> dict[str, str]:
    """
    Elimina un job.

    Args:
        job_id: ID del job

    Returns:
        Messaggio conferma
    """
    store = _get_store()

    success = await store.delete(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")

    logger.info("job_deleted_via_api", job_id=job_id)
    return {"message": f"Job {job_id} deleted"}
