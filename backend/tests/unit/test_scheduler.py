"""Unit tests per Scheduler System (M2)."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from zoneinfo import ZoneInfo

from me4brain.core.scheduler.cron import ScheduleParser
from me4brain.core.scheduler.types import (
    CreateJobRequest,
    DeliveryConfig,
    ExecutionLog,
    JobPayload,
    JobResponse,
    JobStatus,
    ScheduleConfig,
    ScheduledJob,
    ScheduleType,
)


class TestScheduleTypes:
    """Test per modelli Pydantic scheduler."""

    def test_create_scheduled_job(self):
        """Test creazione ScheduledJob."""
        job = ScheduledJob(
            id="test-job-1",
            name="morning_briefing",
            schedule=ScheduleConfig(
                type=ScheduleType.CRON,
                expression="0 7 * * 1-5",
            ),
            payload=JobPayload(
                action="generate_briefing",
                params={"topics": ["weather", "calendar"]},
            ),
        )
        assert job.id == "test-job-1"
        assert job.name == "morning_briefing"
        assert job.schedule.type == ScheduleType.CRON
        assert job.enabled is True
        assert job.run_count == 0

    def test_schedule_types(self):
        """Test enum ScheduleType."""
        assert ScheduleType.CRON == "cron"
        assert ScheduleType.AT == "at"
        assert ScheduleType.EVERY == "every"

    def test_job_success_rate(self):
        """Test calcolo success_rate."""
        job = ScheduledJob(
            id="test",
            name="test",
            schedule=ScheduleConfig(type=ScheduleType.EVERY, expression="1h"),
            payload=JobPayload(action="test"),
            run_count=10,
            success_count=8,
            failure_count=2,
        )
        assert job.success_rate == 0.8

    def test_job_success_rate_no_runs(self):
        """Test success_rate senza esecuzioni."""
        job = ScheduledJob(
            id="test",
            name="test",
            schedule=ScheduleConfig(type=ScheduleType.EVERY, expression="1h"),
            payload=JobPayload(action="test"),
        )
        assert job.success_rate == 1.0  # Default ottimistico

    def test_delivery_config_defaults(self):
        """Test DeliveryConfig defaults."""
        config = DeliveryConfig()
        assert config.channels == ["log"]
        assert config.webhook_url is None

    def test_delivery_config_with_webhook(self):
        """Test DeliveryConfig con webhook."""
        config = DeliveryConfig(
            channels=["log", "webhook"],
            webhook_url="https://example.com/hook",
        )
        assert "webhook" in config.channels
        assert config.webhook_url == "https://example.com/hook"

    def test_execution_log(self):
        """Test ExecutionLog model."""
        log = ExecutionLog(
            id="log-1",
            job_id="job-1",
            job_name="test_job",
            started_at=datetime.now(),
            status=JobStatus.SUCCESS,
            result={"data": "ok"},
        )
        assert log.status == JobStatus.SUCCESS
        assert log.attempt == 1

    def test_create_job_request(self):
        """Test CreateJobRequest."""
        request = CreateJobRequest(
            name="daily_report",
            schedule=ScheduleConfig(
                type=ScheduleType.CRON,
                expression="0 9 * * *",
            ),
            payload=JobPayload(action="generate_report"),
        )
        assert request.name == "daily_report"
        assert request.enabled is True

    def test_job_response_from_job(self):
        """Test JobResponse.from_job."""
        job = ScheduledJob(
            id="job-123",
            name="test_job",
            schedule=ScheduleConfig(type=ScheduleType.EVERY, expression="6h"),
            payload=JobPayload(action="test"),
            run_count=5,
            success_count=4,
        )
        response = JobResponse.from_job(job)
        assert response.id == "job-123"
        assert response.name == "test_job"
        assert response.success_rate == 0.8


class TestScheduleParser:
    """Test per ScheduleParser."""

    def test_parse_every_hours(self):
        """Test parsing 'every 6h'."""
        parser = ScheduleParser()
        job = ScheduledJob(
            id="test",
            name="test",
            schedule=ScheduleConfig(type=ScheduleType.EVERY, expression="6h"),
            payload=JobPayload(action="test"),
        )
        base = datetime.now(ZoneInfo("Europe/Rome"))
        next_run = parser.next_run(job, from_time=base)

        expected = base + timedelta(hours=6)
        assert abs((next_run - expected).total_seconds()) < 1

    def test_parse_every_minutes(self):
        """Test parsing 'every 30m'."""
        parser = ScheduleParser()
        job = ScheduledJob(
            id="test",
            name="test",
            schedule=ScheduleConfig(type=ScheduleType.EVERY, expression="30m"),
            payload=JobPayload(action="test"),
        )
        base = datetime.now(ZoneInfo("Europe/Rome"))
        next_run = parser.next_run(job, from_time=base)

        expected = base + timedelta(minutes=30)
        assert abs((next_run - expected).total_seconds()) < 1

    def test_parse_every_days(self):
        """Test parsing 'every 1d'."""
        parser = ScheduleParser()
        job = ScheduledJob(
            id="test",
            name="test",
            schedule=ScheduleConfig(type=ScheduleType.EVERY, expression="1d"),
            payload=JobPayload(action="test"),
        )
        base = datetime.now(ZoneInfo("Europe/Rome"))
        next_run = parser.next_run(job, from_time=base)

        expected = base + timedelta(days=1)
        assert abs((next_run - expected).total_seconds()) < 1

    def test_parse_at_datetime(self):
        """Test parsing 'at' datetime."""
        parser = ScheduleParser()
        future = datetime.now() + timedelta(days=1)
        job = ScheduledJob(
            id="test",
            name="test",
            schedule=ScheduleConfig(
                type=ScheduleType.AT,
                expression=future.strftime("%Y-%m-%dT%H:%M:%S"),
            ),
            payload=JobPayload(action="test"),
        )
        next_run = parser.next_run(job)
        assert next_run.year == future.year
        assert next_run.month == future.month
        assert next_run.day == future.day

    def test_parse_cron_expression(self):
        """Test parsing cron expression."""
        parser = ScheduleParser()
        job = ScheduledJob(
            id="test",
            name="test",
            schedule=ScheduleConfig(
                type=ScheduleType.CRON,
                expression="0 7 * * *",  # Ogni giorno alle 7
            ),
            payload=JobPayload(action="test"),
        )
        next_run = parser.next_run(job)
        assert next_run.hour == 7
        assert next_run.minute == 0

    def test_invalid_every_expression(self):
        """Test errore per espressione every invalida."""
        parser = ScheduleParser()
        job = ScheduledJob(
            id="test",
            name="test",
            schedule=ScheduleConfig(type=ScheduleType.EVERY, expression="invalid"),
            payload=JobPayload(action="test"),
        )
        with pytest.raises(ValueError, match="Invalid interval"):
            parser.next_run(job)

    def test_validate_expression(self):
        """Test validazione espressioni."""
        parser = ScheduleParser()
        assert parser.validate_expression(ScheduleType.EVERY, "6h") is True
        assert parser.validate_expression(ScheduleType.EVERY, "invalid") is False
        assert parser.validate_expression(ScheduleType.CRON, "0 7 * * *") is True


class TestJobStore:
    """Test per JobStore (con mock Redis)."""

    @pytest.mark.asyncio
    async def test_create_job(self):
        """Test creazione job in store."""
        from me4brain.core.scheduler.store import JobStore

        mock_redis = MagicMock()
        mock_redis.set = AsyncMock()
        mock_redis.sadd = AsyncMock()
        mock_redis.zadd = AsyncMock()

        store = JobStore(mock_redis)

        job = ScheduledJob(
            id="job-123",
            name="test_job",
            schedule=ScheduleConfig(type=ScheduleType.EVERY, expression="1h"),
            payload=JobPayload(action="test"),
            next_run=datetime.now() + timedelta(hours=1),
        )

        result = await store.create(job)

        assert result.id == "job-123"
        mock_redis.set.assert_called_once()
        mock_redis.sadd.assert_called_once()
        mock_redis.zadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_job(self):
        """Test recupero job da store."""
        from me4brain.core.scheduler.store import JobStore

        job = ScheduledJob(
            id="job-456",
            name="test_job",
            schedule=ScheduleConfig(type=ScheduleType.EVERY, expression="1h"),
            payload=JobPayload(action="test"),
        )

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=job.model_dump_json())

        store = JobStore(mock_redis)
        result = await store.get("job-456")

        assert result is not None
        assert result.id == "job-456"
        assert result.name == "test_job"

    @pytest.mark.asyncio
    async def test_get_job_not_found(self):
        """Test job non trovato."""
        from me4brain.core.scheduler.store import JobStore

        mock_redis = MagicMock()
        mock_redis.get = AsyncMock(return_value=None)

        store = JobStore(mock_redis)
        result = await store.get("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_delete_job(self):
        """Test eliminazione job."""
        from me4brain.core.scheduler.store import JobStore

        mock_redis = MagicMock()
        mock_redis.srem = AsyncMock()
        mock_redis.zrem = AsyncMock()
        mock_redis.delete = AsyncMock(return_value=1)

        store = JobStore(mock_redis)
        result = await store.delete("job-123")

        assert result is True
        mock_redis.delete.assert_called_once()
