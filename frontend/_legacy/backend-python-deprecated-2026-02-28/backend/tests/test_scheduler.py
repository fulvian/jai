"""Tests for ProactiveScheduler.

Tests cover:
- Monitor creation
- Pause/resume functionality
- Delete monitor
- List monitors
- Stats retrieval
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from backend.proactive.scheduler import ProactiveScheduler
from backend.proactive.monitors import Monitor, MonitorType, MonitorState


@pytest.fixture
def scheduler():
    """Create scheduler with memory job store."""
    sched = ProactiveScheduler(
        redis_url=None,
        on_evaluate=AsyncMock(),
    )
    return sched


@pytest.fixture
def sample_monitor():
    """Create sample monitor for testing."""
    return Monitor(
        user_id="test_user",
        type=MonitorType.PRICE_WATCH,
        name="Test AAPL Monitor",
        description="Test monitor for AAPL price",
        config={
            "ticker": "AAPL",
            "condition": "below",
            "threshold": 180.0,
        },
        interval_minutes=15,
        notify_channels=["web"],
    )


class TestProactiveScheduler:
    """Test suite for ProactiveScheduler."""

    @pytest.mark.asyncio
    async def test_create_monitor(self, scheduler, sample_monitor):
        """Test creating a new monitor."""
        await scheduler.start()

        try:
            await scheduler.create_monitor(sample_monitor)

            monitors = await scheduler.list_monitors()
            assert len(monitors) == 1
            assert monitors[0].id == sample_monitor.id
            assert monitors[0].name == "Test AAPL Monitor"
            assert monitors[0].state == MonitorState.ACTIVE
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_pause_monitor(self, scheduler, sample_monitor):
        """Test pausing a monitor."""
        await scheduler.start()

        try:
            await scheduler.create_monitor(sample_monitor)
            result = await scheduler.pause_monitor(sample_monitor.id)
            assert result is True

            monitors = await scheduler.list_monitors()
            assert monitors[0].state == MonitorState.PAUSED
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_resume_monitor(self, scheduler, sample_monitor):
        """Test resuming a paused monitor."""
        await scheduler.start()

        try:
            await scheduler.create_monitor(sample_monitor)
            await scheduler.pause_monitor(sample_monitor.id)
            result = await scheduler.resume_monitor(sample_monitor.id)
            assert result is True

            monitors = await scheduler.list_monitors()
            assert monitors[0].state == MonitorState.ACTIVE
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_delete_monitor(self, scheduler, sample_monitor):
        """Test deleting a monitor."""
        await scheduler.start()

        try:
            await scheduler.create_monitor(sample_monitor)
            result = await scheduler.delete_monitor(sample_monitor.id)
            assert result is True

            monitors = await scheduler.list_monitors()
            assert len(monitors) == 0
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_delete_nonexistent_monitor(self, scheduler):
        """Test deleting a monitor that doesn't exist."""
        await scheduler.start()

        try:
            result = await scheduler.delete_monitor("nonexistent-id")
            assert result is False
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_list_monitors_by_user(self, scheduler):
        """Test listing monitors filtered by user."""
        await scheduler.start()

        try:
            monitor1 = Monitor(
                user_id="user1",
                type=MonitorType.PRICE_WATCH,
                name="User1 Monitor",
                config={"ticker": "AAPL"},
                interval_minutes=15,
            )
            monitor2 = Monitor(
                user_id="user2",
                type=MonitorType.AUTONOMOUS,
                name="User2 Monitor",
                config={"ticker": "TSLA"},
                interval_minutes=30,
            )

            await scheduler.create_monitor(monitor1)
            await scheduler.create_monitor(monitor2)

            user1_monitors = await scheduler.list_monitors(user_id="user1")
            assert len(user1_monitors) == 1
            assert user1_monitors[0].user_id == "user1"
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_get_stats(self, scheduler, sample_monitor):
        """Test getting monitor statistics."""
        await scheduler.start()

        try:
            await scheduler.create_monitor(sample_monitor)
            stats = await scheduler.get_stats()

            assert stats["total_monitors"] == 1
            assert stats["active_monitors"] == 1
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_get_monitor(self, scheduler, sample_monitor):
        """Test getting a specific monitor by ID."""
        await scheduler.start()

        try:
            await scheduler.create_monitor(sample_monitor)
            monitor = await scheduler.get_monitor(sample_monitor.id)

            assert monitor is not None
            assert monitor.id == sample_monitor.id
        finally:
            await scheduler.stop()

    @pytest.mark.asyncio
    async def test_get_nonexistent_monitor(self, scheduler):
        """Test getting a monitor that doesn't exist."""
        await scheduler.start()

        try:
            monitor = await scheduler.get_monitor("nonexistent-id")
            assert monitor is None
        finally:
            await scheduler.stop()
