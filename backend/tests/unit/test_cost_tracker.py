"""Unit tests for CostTracker module."""

import pytest

from me4brain.utils.cost_tracker import (
    MODEL_PRICING,
    CostRecord,
    CostTracker,
    TokenUsage,
    cost_tracker,
    track_llm_cost,
)


class TestTokenUsage:
    """Test TokenUsage dataclass."""

    def test_token_usage_creation(self):
        """Test TokenUsage creation with defaults."""
        usage = TokenUsage()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0
        assert usage.total_tokens == 0
        assert usage.model == "unknown"
        assert usage.timestamp is not None

    def test_token_usage_with_values(self):
        """Test TokenUsage with specific values."""
        usage = TokenUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            model="gpt-4o",
        )
        assert usage.prompt_tokens == 100
        assert usage.completion_tokens == 50
        assert usage.total_tokens == 150
        assert usage.model == "gpt-4o"


class TestCostRecord:
    """Test CostRecord dataclass."""

    def test_cost_record_creation(self):
        """Test CostRecord creation."""
        record = CostRecord(
            operation="query",
            tenant_id="tenant_1",
            user_id="user_1",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            total_tokens=1500,
            cost_usd=0.0075,
            latency_ms=250.0,
        )
        assert record.operation == "query"
        assert record.tenant_id == "tenant_1"
        assert record.total_tokens == 1500
        assert record.cost_usd == 0.0075


class TestModelPricing:
    """Test MODEL_PRICING configuration."""

    def test_gpt4o_pricing(self):
        """Test GPT-4o pricing."""
        assert "gpt-4o" in MODEL_PRICING
        assert MODEL_PRICING["gpt-4o"]["input"] == 0.0025
        assert MODEL_PRICING["gpt-4o"]["output"] == 0.01

    def test_claude_pricing(self):
        """Test Claude pricing."""
        assert "claude-3-5-sonnet" in MODEL_PRICING
        assert MODEL_PRICING["claude-3-5-sonnet"]["input"] == 0.003

    def test_default_pricing(self):
        """Test default pricing fallback."""
        assert "default" in MODEL_PRICING
        assert MODEL_PRICING["default"]["input"] == 0.001


class TestCostTracker:
    """Test CostTracker class."""

    @pytest.fixture
    def tracker(self):
        """Fresh tracker instance."""
        # Reset singleton for testing
        tracker = CostTracker()
        tracker._records = []
        tracker._aggregates = {}
        return tracker

    def test_singleton_pattern(self):
        """Test CostTracker is singleton."""
        t1 = CostTracker()
        t2 = CostTracker()
        assert t1 is t2

    def test_record_llm_usage(self, tracker):
        """Test recording LLM usage."""
        record = tracker.record_llm_usage(
            tenant_id="t1",
            user_id="u1",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            latency_ms=200.0,
            operation="query",
        )

        assert record.tenant_id == "t1"
        assert record.total_tokens == 1500
        assert record.cost_usd > 0
        assert len(tracker._records) == 1

    def test_calculate_cost_known_model(self, tracker):
        """Test cost calculation for known model."""
        cost = tracker._calculate_cost("gpt-4o", 1000, 500)
        # 1000 * 0.0025 / 1000 + 500 * 0.01 / 1000 = 0.0025 + 0.005 = 0.0075
        assert cost == 0.0075

    def test_calculate_cost_unknown_model(self, tracker):
        """Test cost calculation for unknown model uses default."""
        cost = tracker._calculate_cost("unknown-model", 1000, 1000)
        # Uses default pricing
        expected = (1000 / 1000 * 0.001) + (1000 / 1000 * 0.002)
        assert cost == round(expected, 6)

    def test_get_tenant_usage_empty(self, tracker):
        """Test tenant usage when no records."""
        usage = tracker.get_tenant_usage("t1")
        assert usage["tenant_id"] == "t1"
        assert usage["total_tokens"] == 0
        assert usage["call_count"] == 0

    def test_get_tenant_usage_with_records(self, tracker):
        """Test tenant usage with records."""
        tracker.record_llm_usage(
            tenant_id="t1",
            user_id="u1",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            latency_ms=100.0,
        )
        tracker.record_llm_usage(
            tenant_id="t1",
            user_id="u1",
            model="gpt-4o",
            prompt_tokens=500,
            completion_tokens=200,
            latency_ms=50.0,
        )

        usage = tracker.get_tenant_usage("t1")
        assert usage["total_tokens"] == 2200
        assert usage["call_count"] == 2
        assert "gpt-4o" in usage["by_model"]

    def test_get_daily_summary(self, tracker):
        """Test daily summary."""
        tracker.record_llm_usage(
            tenant_id="t1",
            user_id="u1",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            latency_ms=100.0,
        )

        summary = tracker.get_daily_summary()
        assert "date" in summary
        assert summary["total_calls"] == 1
        assert "t1" in summary["by_tenant"]

    def test_export_records(self, tracker):
        """Test export records."""
        tracker.record_llm_usage(
            tenant_id="t1",
            user_id="u1",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            latency_ms=100.0,
        )

        records = tracker.export_records()
        assert len(records) == 1
        assert records[0]["tenant_id"] == "t1"
        assert records[0]["model"] == "gpt-4o"

    def test_export_records_filtered(self, tracker):
        """Test export records filtered by tenant."""
        tracker.record_llm_usage(
            tenant_id="t1",
            user_id="u1",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            latency_ms=100.0,
        )
        tracker.record_llm_usage(
            tenant_id="t2",
            user_id="u2",
            model="gpt-4o",
            prompt_tokens=500,
            completion_tokens=200,
            latency_ms=50.0,
        )

        records = tracker.export_records(tenant_id="t1")
        assert len(records) == 1
        assert records[0]["tenant_id"] == "t1"


class TestTrackLlmCostHelper:
    """Test track_llm_cost helper function."""

    def test_track_llm_cost(self):
        """Test the helper function."""
        # Clear existing records
        cost_tracker._records = []

        record = track_llm_cost(
            tenant_id="t1",
            user_id="u1",
            model="gpt-4o",
            prompt_tokens=1000,
            completion_tokens=500,
            latency_ms=100.0,
        )

        assert isinstance(record, CostRecord)
        assert record.tenant_id == "t1"
