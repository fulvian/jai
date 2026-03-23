"""Schedule Task Tool - Tool per l'agente per schedulare task."""

import hashlib
from datetime import datetime

import structlog

from me4brain.core.scheduler.cron import ScheduleParser
from me4brain.core.scheduler.store import get_job_store
from me4brain.core.scheduler.types import (
    DeliveryConfig,
    JobPayload,
    ScheduleConfig,
    ScheduledJob,
    ScheduleType,
)

logger = structlog.get_logger(__name__)


async def schedule_task(
    name: str,
    schedule: str,
    action: str,
    params: dict | None = None,
    webhook_url: str | None = None,
    description: str | None = None,
) -> dict:
    """
    Schedula un task per esecuzione futura.

    L'agente può usare questo tool durante conversazioni
    per creare reminder, briefing periodici, ecc.

    Args:
        name: Nome del job (es. "morning_briefing")
        schedule: Espressione schedule:
            - "every 6h" - ogni 6 ore
            - "every 30m" - ogni 30 minuti
            - "at 2024-02-03T10:00" - one-shot
            - "cron 0 7 * * 1-5" - lun-ven ore 7
        action: Azione da eseguire (es. "generate_briefing")
        params: Parametri per l'azione
        webhook_url: URL per notifica webhook (opzionale)
        description: Descrizione del task

    Returns:
        Dettagli del job creato
    """
    store = get_job_store()
    if store is None:
        return {
            "success": False,
            "error": "Scheduler not initialized",
        }

    parser = ScheduleParser()

    # Parse schedule expression
    schedule_type, expression = _parse_schedule_expression(schedule)

    # Genera ID
    job_id = hashlib.sha256(f"{name}:{datetime.now().isoformat()}".encode()).hexdigest()[:12]

    # Configura delivery
    channels = ["log"]
    if webhook_url:
        channels.append("webhook")

    delivery = DeliveryConfig(
        channels=channels,
        webhook_url=webhook_url,
    )

    # Crea job
    job = ScheduledJob(
        id=job_id,
        name=name,
        description=description,
        schedule=ScheduleConfig(
            type=schedule_type,
            expression=expression,
        ),
        payload=JobPayload(
            action=action,
            params=params or {},
        ),
        delivery=delivery,
    )

    # Calcola next_run
    try:
        job.next_run = parser.next_run(job)
    except ValueError as e:
        return {
            "success": False,
            "error": f"Invalid schedule: {e}",
        }

    # Salva
    await store.create(job)

    logger.info(
        "task_scheduled_by_agent",
        job_id=job.id,
        name=name,
        schedule=schedule,
        next_run=job.next_run.isoformat() if job.next_run else None,
    )

    return {
        "success": True,
        "job_id": job.id,
        "name": name,
        "schedule": schedule,
        "next_run": job.next_run.isoformat() if job.next_run else None,
        "message": f"Task '{name}' scheduled successfully",
    }


def _parse_schedule_expression(schedule: str) -> tuple[ScheduleType, str]:
    """
    Parse espressione schedule in tipo + expression.

    Args:
        schedule: "every 6h", "at 2024-...", "cron 0 7 * * *"

    Returns:
        (ScheduleType, expression)
    """
    schedule = schedule.strip()

    if schedule.startswith("every "):
        return ScheduleType.EVERY, schedule[6:].strip()

    elif schedule.startswith("at "):
        return ScheduleType.AT, schedule[3:].strip()

    elif schedule.startswith("cron "):
        return ScheduleType.CRON, schedule[5:].strip()

    else:
        # Assume cron se contiene spazi numerici
        if any(c.isdigit() for c in schedule) and " " in schedule:
            return ScheduleType.CRON, schedule
        # Assume every se contiene unità tempo
        if any(u in schedule.lower() for u in ["s", "m", "h", "d", "w"]):
            return ScheduleType.EVERY, schedule
        # Default: cron
        return ScheduleType.CRON, schedule


# Tool definition per il catalogo
SCHEDULE_TASK_TOOL = {
    "name": "schedule_task",
    "description": "Schedule a task for future execution. Supports: 'every 6h' (interval), 'at 2024-02-03T10:00' (one-shot), 'cron 0 7 * * 1-5' (cron expression).",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Name of the scheduled task",
            },
            "schedule": {
                "type": "string",
                "description": "Schedule expression: 'every 6h', 'at 2024-02-03T10:00', 'cron 0 7 * * 1-5'",
            },
            "action": {
                "type": "string",
                "description": "Action to execute (e.g., 'generate_briefing', 'send_reminder')",
            },
            "params": {
                "type": "object",
                "description": "Parameters for the action",
            },
            "webhook_url": {
                "type": "string",
                "description": "Optional webhook URL for notification",
            },
            "description": {
                "type": "string",
                "description": "Optional description of the task",
            },
        },
        "required": ["name", "schedule", "action"],
    },
}
