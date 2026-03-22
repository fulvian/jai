"""Tests for MonitorEvaluator.

Tests cover:
- Evaluator initialization
- Close method
- Error handling basics
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from backend.proactive.evaluator import MonitorEvaluator
from backend.proactive.monitors import Monitor, MonitorType


@pytest.fixture
def evaluator():
    """Create evaluator with mocked dependencies."""
    return MonitorEvaluator(
        me4brain_url="http://localhost:8000",
        nanogpt_api_key="test-key",
    )


@pytest.fixture
def price_watch_monitor():
    """Price watch monitor fixture."""
    return Monitor(
        user_id="test_user",
        type=MonitorType.PRICE_WATCH,
        name="AAPL Price Alert",
        config={
            "ticker": "AAPL",
            "condition": "above",  # Use above so fallback price=0 doesn't trigger
            "threshold": 180.0,
        },
        interval_minutes=15,
    )


class TestMonitorEvaluator:
    """Test suite for MonitorEvaluator."""

    def test_evaluator_init(self, evaluator):
        """Test evaluator initialization."""
        assert evaluator.me4brain_url == "http://localhost:8000"
        assert evaluator.nanogpt_api_key == "test-key"
        assert evaluator._http_client is None

    @pytest.mark.asyncio
    async def test_get_client_creates_client(self, evaluator):
        """Test lazy client initialization."""
        client = await evaluator._get_client()
        assert client is not None
        assert evaluator._http_client is not None
        await evaluator.close()

    @pytest.mark.asyncio
    async def test_close_releases_resources(self, evaluator):
        """Test that close() releases HTTP client."""
        await evaluator._get_client()
        await evaluator.close()
        assert evaluator._http_client is None

    @pytest.mark.asyncio
    async def test_evaluate_returns_result(self, evaluator, price_watch_monitor):
        """Test evaluate returns an EvaluationResult."""
        result = await evaluator.evaluate(price_watch_monitor)

        assert result is not None
        assert result.monitor_id == price_watch_monitor.id
        assert result.evaluated_at is not None

        await evaluator.close()

    @pytest.mark.asyncio
    async def test_evaluate_price_watch_fallback(self, evaluator, price_watch_monitor):
        """Test price watch with API failure uses fallback."""
        # When API fails, evaluator should still return a result
        result = await evaluator.evaluate(price_watch_monitor)

        # Should have data_snapshot even with fallback
        assert result.data_snapshot is not None

        await evaluator.close()


class TestEvaluatorWithMockedAPI:
    """Test evaluator with mocked API responses."""

    @pytest.mark.asyncio
    async def test_price_watch_trigger_above(self):
        """Test price watch triggers when price is above threshold."""
        evaluator = MonitorEvaluator(
            me4brain_url="http://test:8000",
            nanogpt_api_key="test",
        )

        monitor = Monitor(
            user_id="test",
            type=MonitorType.PRICE_WATCH,
            name="Test",
            config={
                "ticker": "TEST",
                "condition": "above",
                "threshold": 100.0,
            },
            interval_minutes=15,
        )

        # Mock the fetch method to return a price above threshold
        async def mock_fetch_stock(ticker):
            return {"price": 120.0, "ticker": ticker}

        with patch.object(evaluator, "_fetch_stock_data", mock_fetch_stock):
            result = await evaluator.evaluate(monitor)
            assert result.trigger is True

        await evaluator.close()

    @pytest.mark.asyncio
    async def test_price_watch_no_trigger_above(self):
        """Test price watch doesn't trigger when price is below threshold."""
        evaluator = MonitorEvaluator(
            me4brain_url="http://test:8000",
            nanogpt_api_key="test",
        )

        monitor = Monitor(
            user_id="test",
            type=MonitorType.PRICE_WATCH,
            name="Test",
            config={
                "ticker": "TEST",
                "condition": "above",
                "threshold": 100.0,
            },
            interval_minutes=15,
        )

        async def mock_fetch_stock(ticker):
            return {"price": 80.0, "ticker": ticker}

        with patch.object(evaluator, "_fetch_stock_data", mock_fetch_stock):
            result = await evaluator.evaluate(monitor)
            assert result.trigger is False

        await evaluator.close()

    @pytest.mark.asyncio
    async def test_price_watch_trigger_below(self):
        """Test price watch triggers when price is below threshold."""
        evaluator = MonitorEvaluator(
            me4brain_url="http://test:8000",
            nanogpt_api_key="test",
        )

        monitor = Monitor(
            user_id="test",
            type=MonitorType.PRICE_WATCH,
            name="Test",
            config={
                "ticker": "TEST",
                "condition": "below",
                "threshold": 100.0,
            },
            interval_minutes=15,
        )

        async def mock_fetch_stock(ticker):
            return {"price": 80.0, "ticker": ticker}

        with patch.object(evaluator, "_fetch_stock_data", mock_fetch_stock):
            result = await evaluator.evaluate(monitor)
            assert result.trigger is True

        await evaluator.close()
