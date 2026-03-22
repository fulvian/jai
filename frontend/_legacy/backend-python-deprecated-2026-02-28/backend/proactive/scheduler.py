"""Proactive Scheduler.

Gestisce scheduling e persistenza dei monitor jobs usando APScheduler.
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Callable

import structlog
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.proactive.monitors import Monitor, MonitorState

logger = structlog.get_logger(__name__)


class ProactiveScheduler:
    """Scheduler per monitor proattivi.

    Gestisce la creazione, pausa, resume e cancellazione di job schedulati.
    Integra con Redis per persistenza (quando disponibile).
    """

    def __init__(
        self,
        redis_url: str | None = None,
        on_evaluate: Callable[[Monitor], Any] | None = None,
    ):
        """Inizializza scheduler.

        Args:
            redis_url: URL Redis per persistenza jobs (opzionale)
            on_evaluate: Callback chiamato per ogni evaluation
        """
        self.redis_url = redis_url
        self.on_evaluate = on_evaluate

        # Configura jobstores
        jobstores: dict[str, Any] = {}

        # Prova Redis JobStore se configurato
        if redis_url:
            try:
                from apscheduler.jobstores.redis import RedisJobStore

                jobstores["default"] = RedisJobStore(
                    jobs_key="persan:proactive:jobs",
                    run_times_key="persan:proactive:run_times",
                    host=self._parse_redis_host(redis_url),
                    port=self._parse_redis_port(redis_url),
                    password=self._parse_redis_password(redis_url),
                )
                logger.info("proactive_scheduler_redis_init", url=redis_url)
            except Exception as e:
                logger.warning("proactive_scheduler_redis_fallback", error=str(e))
                jobstores["default"] = MemoryJobStore()
        else:
            jobstores["default"] = MemoryJobStore()
            logger.info("proactive_scheduler_memory_init")

        # Crea scheduler
        self.scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            job_defaults={
                "coalesce": True,  # Combina run mancati
                "max_instances": 1,  # Max 1 istanza per job
                "misfire_grace_time": 60,  # Tolleranza 60s per run mancati
            },
        )

        # Monitor registry (in-memory, backup Redis)
        self._monitors: dict[str, Monitor] = {}

    def _parse_redis_host(self, url: str) -> str:
        """Estrae host da redis URL."""
        # redis://[:password@]host[:port][/db]
        url = url.replace("redis://", "")
        if "@" in url:
            url = url.split("@")[1]
        return url.split(":")[0].split("/")[0]

    def _parse_redis_port(self, url: str) -> int:
        """Estrae port da redis URL."""
        url = url.replace("redis://", "")
        if "@" in url:
            url = url.split("@")[1]
        if ":" in url:
            port_str = url.split(":")[1].split("/")[0]
            return int(port_str)
        return 6379

    def _parse_redis_password(self, url: str) -> str | None:
        """Estrae password da redis URL."""
        url = url.replace("redis://", "")
        if "@" in url:
            auth = url.split("@")[0]
            if ":" in auth:
                return auth.split(":")[1]
            return auth
        return None

    async def start(self) -> None:
        """Avvia lo scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("proactive_scheduler_started")

    async def stop(self, wait: bool = True) -> None:
        """Ferma lo scheduler gracefully."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)
            logger.info("proactive_scheduler_stopped", wait=wait)

    # =========================================================================
    # Monitor Management
    # =========================================================================

    async def create_monitor(self, monitor: Monitor) -> str:
        """Crea e schedula un nuovo monitor.

        Returns:
            ID del monitor creato
        """
        # Store monitor
        self._monitors[monitor.id] = monitor

        # Crea job in base al tipo
        if monitor.type.value == "scheduled":
            # Usa cron expression dalla config
            cron_expr = monitor.config.get("cron_expression", "0 * * * *")
            trigger = CronTrigger.from_crontab(cron_expr)
        else:
            # Usa interval per tutti gli altri tipi
            trigger = IntervalTrigger(minutes=monitor.interval_minutes)

        # Schedula job
        self.scheduler.add_job(
            self._evaluate_job,
            trigger=trigger,
            id=monitor.id,
            name=f"monitor:{monitor.name}",
            args=[monitor.id],
            replace_existing=True,
        )

        # Aggiorna stato
        monitor.state = MonitorState.ACTIVE
        monitor.next_check = datetime.utcnow() + timedelta(minutes=monitor.interval_minutes)

        logger.info(
            "monitor_created",
            monitor_id=monitor.id,
            type=monitor.type.value,
            interval=monitor.interval_minutes,
        )

        return monitor.id

    async def pause_monitor(self, monitor_id: str) -> bool:
        """Pausa un monitor."""
        if monitor_id not in self._monitors:
            return False

        self.scheduler.pause_job(monitor_id)
        self._monitors[monitor_id].state = MonitorState.PAUSED

        logger.info("monitor_paused", monitor_id=monitor_id)
        return True

    async def resume_monitor(self, monitor_id: str) -> bool:
        """Riprende un monitor pausato."""
        if monitor_id not in self._monitors:
            return False

        self.scheduler.resume_job(monitor_id)
        self._monitors[monitor_id].state = MonitorState.ACTIVE

        logger.info("monitor_resumed", monitor_id=monitor_id)
        return True

    async def delete_monitor(self, monitor_id: str) -> bool:
        """Elimina un monitor."""
        if monitor_id not in self._monitors:
            return False

        try:
            self.scheduler.remove_job(monitor_id)
        except Exception:
            pass  # Job potrebbe non esistere

        del self._monitors[monitor_id]

        logger.info("monitor_deleted", monitor_id=monitor_id)
        return True

    async def get_monitor(self, monitor_id: str) -> Monitor | None:
        """Ottiene un monitor per ID."""
        return self._monitors.get(monitor_id)

    async def list_monitors(self, user_id: str | None = None) -> list[Monitor]:
        """Lista monitor, opzionalmente filtrati per user."""
        monitors = list(self._monitors.values())
        if user_id:
            monitors = [m for m in monitors if m.user_id == user_id]
        return monitors

    async def get_stats(self) -> dict[str, Any]:
        """Statistiche scheduler."""
        monitors = list(self._monitors.values())
        return {
            "total_monitors": len(monitors),
            "active_monitors": sum(1 for m in monitors if m.state == MonitorState.ACTIVE),
            "paused_monitors": sum(1 for m in monitors if m.state == MonitorState.PAUSED),
            "total_checks": sum(m.checks_count for m in monitors),
            "total_triggers": sum(m.triggers_count for m in monitors),
            "by_type": self._count_by_type(monitors),
            "scheduler_running": self.scheduler.running,
            "pending_jobs": len(self.scheduler.get_jobs()),
        }

    def _count_by_type(self, monitors: list[Monitor]) -> dict[str, int]:
        """Conta monitor per tipo."""
        counts: dict[str, int] = {}
        for m in monitors:
            t = m.type.value
            counts[t] = counts.get(t, 0) + 1
        return counts

    # =========================================================================
    # Job Execution
    # =========================================================================

    async def _evaluate_job(self, monitor_id: str) -> None:
        """Job eseguito dallo scheduler per ogni check."""
        monitor = self._monitors.get(monitor_id)
        if not monitor:
            logger.warning("evaluate_job_monitor_not_found", monitor_id=monitor_id)
            return

        logger.info(
            "evaluate_job_start",
            monitor_id=monitor_id,
            type=monitor.type.value,
            check_number=monitor.checks_count + 1,
        )

        try:
            # Chiama callback evaluate se configurato
            if self.on_evaluate:
                await self.on_evaluate(monitor)

            # Aggiorna next_check
            monitor.next_check = datetime.utcnow() + timedelta(minutes=monitor.interval_minutes)

            # Check max_checks
            if monitor.max_checks and monitor.checks_count >= monitor.max_checks:
                monitor.state = MonitorState.COMPLETED
                await self.delete_monitor(monitor_id)
                logger.info(
                    "monitor_completed_max_checks",
                    monitor_id=monitor_id,
                    total_checks=monitor.checks_count,
                )

        except Exception as e:
            logger.error(
                "evaluate_job_error",
                monitor_id=monitor_id,
                error=str(e),
            )
            monitor.state = MonitorState.ERROR

    async def trigger_immediate(self, monitor_id: str) -> bool:
        """Forza valutazione immediata di un monitor."""
        monitor = self._monitors.get(monitor_id)
        if not monitor:
            return False

        # Esegui job immediatamente
        asyncio.create_task(self._evaluate_job(monitor_id))

        logger.info("monitor_triggered_immediate", monitor_id=monitor_id)
        return True
