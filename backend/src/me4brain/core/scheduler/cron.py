"""Cron Parser - Parsing espressioni schedule."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from croniter import croniter

from me4brain.core.scheduler.types import ScheduledJob, ScheduleType

logger = structlog.get_logger(__name__)


class ScheduleParser:
    """
    Parser per espressioni schedule.

    Supporta:
    - cron: "0 7 * * 1-5" (lun-ven ore 7)
    - at: "2024-02-03T10:00:00" (one-shot)
    - every: "6h", "30m", "1d" (intervallo)
    """

    # Regex per intervalli (every)
    EVERY_PATTERN = re.compile(r"^(\d+)\s*(s|m|h|d|w)$", re.IGNORECASE)

    # Mapping unità a secondi
    UNIT_SECONDS = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400,
        "w": 604800,
    }

    def next_run(self, job: ScheduledJob, from_time: datetime | None = None) -> datetime:
        """
        Calcola prossimo run time per un job.

        Args:
            job: Job schedulato
            from_time: Tempo di riferimento (default: now)

        Returns:
            Datetime del prossimo run
        """
        base_time = from_time or datetime.now(ZoneInfo(job.schedule.timezone))
        schedule_type = job.schedule.type
        expression = job.schedule.expression

        if schedule_type == ScheduleType.CRON:
            return self._parse_cron(expression, job.schedule.timezone, base_time)
        elif schedule_type == ScheduleType.AT:
            return self._parse_at(expression, job.schedule.timezone)
        elif schedule_type == ScheduleType.EVERY:
            return self._parse_every(expression, base_time)
        else:
            raise ValueError(f"Unknown schedule type: {schedule_type}")

    def _parse_cron(self, expression: str, timezone: str, base_time: datetime) -> datetime:
        """
        Parse espressione cron.

        Args:
            expression: Cron expression (es. "0 7 * * 1-5")
            timezone: Timezone string (es. "Europe/Rome")
            base_time: Tempo di riferimento

        Returns:
            Prossimo run time
        """
        try:
            tz = ZoneInfo(timezone)
            # Assicura che base_time sia timezone-aware
            if base_time.tzinfo is None:
                base_time = base_time.replace(tzinfo=tz)

            cron = croniter(expression, base_time)
            next_time = cron.get_next(datetime)

            logger.debug(
                "cron_parsed",
                expression=expression,
                next_run=next_time.isoformat(),
            )

            return next_time

        except Exception as e:
            logger.error("cron_parse_error", expression=expression, error=str(e))
            raise ValueError(f"Invalid cron expression: {expression}") from e

    def _parse_at(self, expression: str, timezone: str) -> datetime:
        """
        Parse datetime ISO per one-shot.

        Args:
            expression: ISO datetime (es. "2024-02-03T10:00:00")
            timezone: Timezone string

        Returns:
            Datetime specificato
        """
        try:
            tz = ZoneInfo(timezone)

            # Prova parsing ISO
            if "T" in expression:
                dt = datetime.fromisoformat(expression)
            else:
                # Solo data: assume mezzanotte
                dt = datetime.fromisoformat(f"{expression}T00:00:00")

            # Aggiungi timezone se manca
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz)

            logger.debug(
                "at_parsed",
                expression=expression,
                result=dt.isoformat(),
            )

            return dt

        except Exception as e:
            logger.error("at_parse_error", expression=expression, error=str(e))
            raise ValueError(f"Invalid datetime: {expression}") from e

    def _parse_every(self, expression: str, base_time: datetime) -> datetime:
        """
        Parse intervallo.

        Args:
            expression: Intervallo (es. "6h", "30m", "1d")
            base_time: Tempo di riferimento

        Returns:
            Next run time
        """
        match = self.EVERY_PATTERN.match(expression.strip())
        if not match:
            raise ValueError(f"Invalid interval expression: {expression}")

        value = int(match.group(1))
        unit = match.group(2).lower()

        if unit not in self.UNIT_SECONDS:
            raise ValueError(f"Unknown time unit: {unit}")

        seconds = value * self.UNIT_SECONDS[unit]
        next_time = base_time + timedelta(seconds=seconds)

        logger.debug(
            "every_parsed",
            expression=expression,
            seconds=seconds,
            next_run=next_time.isoformat(),
        )

        return next_time

    def validate_expression(self, schedule_type: ScheduleType, expression: str) -> bool:
        """
        Valida espressione schedule.

        Args:
            schedule_type: Tipo schedule
            expression: Espressione da validare

        Returns:
            True se valida
        """
        try:
            dummy_job = ScheduledJob(
                id="validation",
                name="validation",
                schedule={"type": schedule_type, "expression": expression},
                payload={"action": "test"},
            )
            self.next_run(dummy_job)
            return True
        except Exception:
            return False
