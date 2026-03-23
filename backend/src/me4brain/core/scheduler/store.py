"""Job Store - Storage Redis per job schedulati."""

from __future__ import annotations

from datetime import datetime

import structlog
from redis.asyncio import Redis

from me4brain.core.scheduler.types import ScheduledJob

logger = structlog.get_logger(__name__)


class JobStore:
    """
    Storage persistente per job schedulati in Redis.

    Pattern:
    - Hash per singolo job: me4brain:scheduler:jobs:{id}
    - Set per indice: me4brain:scheduler:jobs:index
    - Sorted set per next_run: me4brain:scheduler:jobs:pending
    """

    PREFIX = "me4brain:scheduler:jobs"

    def __init__(self, redis: Redis):
        """
        Inizializza store.

        Args:
            redis: Client Redis async
        """
        self.redis = redis

    def _job_key(self, job_id: str) -> str:
        """Genera chiave Redis per job."""
        return f"{self.PREFIX}:{job_id}"

    @property
    def _index_key(self) -> str:
        """Chiave per indice job."""
        return f"{self.PREFIX}:index"

    @property
    def _pending_key(self) -> str:
        """Chiave sorted set per job pendenti."""
        return f"{self.PREFIX}:pending"

    async def create(self, job: ScheduledJob) -> ScheduledJob:
        """
        Crea nuovo job.

        Args:
            job: Job da creare

        Returns:
            Job creato
        """
        key = self._job_key(job.id)

        # Serializza job
        job_data = job.model_dump_json()

        # Salva in hash
        await self.redis.set(key, job_data)

        # Aggiungi a indice
        await self.redis.sadd(self._index_key, job.id)

        # Se ha next_run, aggiungi a pending
        if job.next_run:
            score = job.next_run.timestamp()
            await self.redis.zadd(self._pending_key, {job.id: score})

        logger.info(
            "job_created",
            job_id=job.id,
            name=job.name,
            next_run=job.next_run.isoformat() if job.next_run else None,
        )

        return job

    async def get(self, job_id: str) -> ScheduledJob | None:
        """
        Recupera job per ID.

        Args:
            job_id: ID del job

        Returns:
            Job o None se non trovato
        """
        key = self._job_key(job_id)
        data = await self.redis.get(key)

        if data is None:
            return None

        return ScheduledJob.model_validate_json(data)

    async def list(
        self,
        tenant_id: str | None = None,
        enabled_only: bool = False,
    ) -> list[ScheduledJob]:
        """
        Lista tutti i job.

        Args:
            tenant_id: Filtra per tenant
            enabled_only: Solo job abilitati

        Returns:
            Lista job
        """
        job_ids = await self.redis.smembers(self._index_key)
        jobs: list[ScheduledJob] = []

        for job_id in job_ids:
            job = await self.get(job_id)
            if job is None:
                continue

            # Filtri
            if tenant_id and job.tenant_id != tenant_id:
                continue
            if enabled_only and not job.enabled:
                continue

            jobs.append(job)

        return jobs

    async def update(self, job: ScheduledJob) -> None:
        """
        Aggiorna job esistente.

        Args:
            job: Job da aggiornare
        """
        key = self._job_key(job.id)

        # Verifica esistenza
        if not await self.redis.exists(key):
            raise ValueError(f"Job not found: {job.id}")

        # Aggiorna timestamp
        job.updated_at = datetime.now()

        # Salva
        job_data = job.model_dump_json()
        await self.redis.set(key, job_data)

        # Aggiorna sorted set pending
        if job.enabled and job.next_run:
            score = job.next_run.timestamp()
            await self.redis.zadd(self._pending_key, {job.id: score})
        else:
            await self.redis.zrem(self._pending_key, job.id)

        logger.debug("job_updated", job_id=job.id)

    async def delete(self, job_id: str) -> bool:
        """
        Elimina job.

        Args:
            job_id: ID del job

        Returns:
            True se eliminato
        """
        key = self._job_key(job_id)

        # Rimuovi da tutti gli indici
        await self.redis.srem(self._index_key, job_id)
        await self.redis.zrem(self._pending_key, job_id)

        # Elimina job
        count = await self.redis.delete(key)

        if count > 0:
            logger.info("job_deleted", job_id=job_id)
            return True
        return False

    async def get_pending(self, before: datetime) -> list[ScheduledJob]:
        """
        Recupera job pendenti da eseguire.

        Args:
            before: Timestamp limite

        Returns:
            Lista job da eseguire
        """
        score_max = before.timestamp()

        # Recupera job con next_run <= before
        job_ids = await self.redis.zrangebyscore(
            self._pending_key,
            min="-inf",
            max=score_max,
        )

        jobs: list[ScheduledJob] = []
        for job_id in job_ids:
            job = await self.get(job_id)
            if job and job.enabled:
                jobs.append(job)

        logger.debug(
            "pending_jobs_fetched",
            count=len(jobs),
            before=before.isoformat(),
        )

        return jobs

    async def mark_executed(
        self,
        job_id: str,
        success: bool,
        next_run: datetime | None = None,
    ) -> None:
        """
        Registra esecuzione job.

        Args:
            job_id: ID del job
            success: Esito esecuzione
            next_run: Prossimo run time
        """
        job = await self.get(job_id)
        if job is None:
            return

        # Aggiorna statistiche
        job.run_count += 1
        job.last_run = datetime.now()

        if success:
            job.success_count += 1
        else:
            job.failure_count += 1

        # Aggiorna next_run
        job.next_run = next_run

        await self.update(job)

        logger.info(
            "job_executed",
            job_id=job_id,
            success=success,
            run_count=job.run_count,
            next_run=next_run.isoformat() if next_run else None,
        )


# Singleton globale
_job_store: JobStore | None = None


def get_job_store() -> JobStore | None:
    """Ottiene job store globale."""
    return _job_store


def set_job_store(store: JobStore) -> None:
    """Imposta job store globale."""
    global _job_store
    _job_store = store


async def initialize_job_store(redis_url: str = "redis://localhost:6379") -> JobStore:
    """
    Inizializza job store.

    Args:
        redis_url: URL connessione Redis

    Returns:
        JobStore inizializzato
    """
    redis = Redis.from_url(redis_url, decode_responses=True)
    store = JobStore(redis)
    set_job_store(store)
    logger.info("job_store_initialized", redis_url=redis_url)
    return store
