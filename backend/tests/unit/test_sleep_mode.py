import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, UTC
from me4brain.core.sleep_mode import SleepMode, ConsolidationConfig


@pytest.fixture
def sleep_mode():
    return SleepMode()


@pytest.mark.asyncio
async def test_run_consolidation_basic(sleep_mode):
    # Mock dependencies with proper async returns
    mock_semantic = MagicMock()
    mock_semantic.get_driver = AsyncMock(return_value=None)  # Skip Neo4j ops

    mock_episodic = MagicMock()
    mock_episodic.get_qdrant = AsyncMock(return_value=None)  # Skip Qdrant ops

    with (
        patch("me4brain.core.sleep_mode.get_episodic_memory", return_value=mock_episodic),
        patch("me4brain.core.sleep_mode.get_semantic_memory", return_value=mock_semantic),
        patch("me4brain.core.sleep_mode.get_embedding_service") as mock_emb,
    ):
        result = await sleep_mode.run_consolidation(tenant_id="t1", dry_run=True)

        assert result.episodes_processed == 0
        assert len(result.errors) == 0
        assert isinstance(result.started_at, datetime)


@pytest.mark.asyncio
async def test_scheduler_lifecycle(sleep_mode):
    # Test starting and stopping the scheduler
    with patch("me4brain.core.sleep_mode.asyncio.sleep", AsyncMock()):
        await sleep_mode.start_background_scheduler(interval_hours=1, tenant_ids=["t1"])
        assert sleep_mode._running is True
        assert sleep_mode._task is not None

        await sleep_mode.stop_background_scheduler()
        assert sleep_mode._running is False
        assert sleep_mode._task is None


@pytest.mark.asyncio
async def test_consolidation_error_handling(sleep_mode):
    # Simulate an error in one of the steps
    with patch.object(
        sleep_mode, "_consolidate_episodic_to_semantic", side_effect=ValueError("Test Error")
    ):
        result = await sleep_mode.run_consolidation(tenant_id="t1")
        assert len(result.errors) > 0
        assert "Pattern extraction failed" in result.errors[0]
