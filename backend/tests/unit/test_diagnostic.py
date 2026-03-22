"""Tests for diagnostic module."""

import asyncio

import pytest

from me4brain.utils.diagnostic import (
    LatencyTracker,
    QueryTrace,
    track_latency,
    with_timing,
)


class TestLatencyTracker:
    """Tests for LatencyTracker."""

    def test_start_and_stop(self):
        tracker = LatencyTracker("test_op")
        tracker.start(key="value")
        metrics = tracker.stop()

        assert metrics.operation == "test_op"
        assert metrics.success
        assert metrics.duration_ms >= 0
        assert metrics.metadata == {"key": "value"}

    def test_stop_with_error(self):
        tracker = LatencyTracker("test_op")
        tracker.start()
        metrics = tracker.stop(success=False, error="Something failed")

        assert not metrics.success
        assert metrics.error == "Something failed"


class TestTrackLatency:
    """Tests for track_latency context manager."""

    @pytest.mark.asyncio
    async def test_successful_operation(self):
        async with track_latency("test_op") as tracker:
            await asyncio.sleep(0.01)

        assert tracker.start_time is not None
        assert tracker.end_time is not None

    @pytest.mark.asyncio
    async def test_failed_operation(self):
        with pytest.raises(ValueError):
            async with track_latency("test_op") as tracker:
                raise ValueError("test error")


class TestQueryTrace:
    """Tests for QueryTrace."""

    def test_init(self):
        trace = QueryTrace("test query", session_id="sess123")

        assert trace.query == "test query"
        assert trace.session_id == "sess123"
        assert trace.phases == []
        assert trace.decisions == []

    def test_record_phase(self):
        trace = QueryTrace("test query")
        trace.record_phase("intent_analysis", 50.0, success=True)

        assert len(trace.phases) == 1
        assert trace.phases[0]["phase"] == "intent_analysis"
        assert trace.phases[0]["duration_ms"] == 50.0

    def test_record_decision(self):
        trace = QueryTrace("test query")
        trace.record_decision("domain_selection", "finance", reasoning="Keywords detected")

        assert len(trace.decisions) == 1
        assert trace.decisions[0]["decision_point"] == "domain_selection"
        assert trace.decisions[0]["decision"] == "finance"

    def test_record_tool_call(self):
        trace = QueryTrace("test query")
        trace.record_tool_call("search_api")
        trace.record_tool_call("finance_api")

        assert len(trace.tools_called) == 2
        assert "search_api" in trace.tools_called

    def test_record_error(self):
        trace = QueryTrace("test query")
        trace.record_error(ValueError("test error"), phase="tool_execution")

        assert len(trace.errors) == 1
        assert trace.errors[0]["error_type"] == "ValueError"
        assert trace.errors[0]["phase"] == "tool_execution"

    def test_finalize(self):
        trace = QueryTrace("test query")
        trace.record_phase("phase1", 10.0)
        trace.record_decision("decision1", "choice1")
        trace.record_tool_call("tool1")

        summary = trace.finalize()

        assert summary["phases_count"] == 1
        assert summary["decisions_count"] == 1
        assert summary["tools_count"] == 1
        assert summary["success"]


class TestWithTiming:
    """Tests for with_timing decorator."""

    @pytest.mark.asyncio
    async def test_async_timing(self):
        @with_timing("test_async_op")
        async def async_func():
            await asyncio.sleep(0.01)
            return "result"

        result = await async_func()
        assert result == "result"

    def test_sync_timing(self):
        @with_timing("test_sync_op")
        def sync_func():
            return "result"

        result = sync_func()
        assert result == "result"
