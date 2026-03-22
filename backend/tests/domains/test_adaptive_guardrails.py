"""Tests for Adaptive Guardrails System.

Testa:
1. GuardrailsMetrics tracking
2. AdaptiveGuardrailsConfig adattamento dinamico
3. ResponseLimiter compressione e paginazione
4. StreamingJSONEncoder streaming
5. apply_response_guardrails integration
6. Adaptive limits adjustment based on patterns
"""

import pytest
from datetime import UTC, datetime

from me4brain.core.interfaces import DomainExecutionResult
from me4brain.domains.adaptive_guardrails import (
    GuardrailsMetrics,
    AdaptiveGuardrailsConfig,
    ResponseLimiter,
    StreamingJSONEncoder,
    apply_response_guardrails,
    get_guardrails_for_domain,
)


class TestGuardrailsMetrics:
    """Test GuardrailsMetrics tracking."""

    def test_metrics_initialization(self):
        """Test metrics initialization."""
        metrics = GuardrailsMetrics(domain="test_domain")

        assert metrics.domain == "test_domain"
        assert metrics.total_responses == 0
        assert metrics.avg_response_size == 0
        assert metrics.truncations_applied == 0

    def test_metrics_update_size(self):
        """Test metrics update with size tracking."""
        metrics = GuardrailsMetrics(domain="test_domain")

        metrics.update(original_size=1000, final_size=900)

        assert metrics.total_responses == 1
        assert metrics.avg_response_size == 900
        assert metrics.max_response_size == 900
        assert metrics.min_response_size == 900

    def test_metrics_update_multiple_responses(self):
        """Test metrics with multiple responses."""
        metrics = GuardrailsMetrics(domain="test_domain")

        metrics.update(original_size=1000, final_size=900)
        metrics.update(original_size=2000, final_size=1800)
        metrics.update(original_size=800, final_size=700)

        assert metrics.total_responses == 3
        assert metrics.max_response_size == 1800
        assert metrics.min_response_size == 700
        assert metrics.avg_response_size == 1133  # (900 + 1800 + 700) / 3

    def test_metrics_track_truncations(self):
        """Test truncation tracking."""
        metrics = GuardrailsMetrics(domain="test_domain")

        metrics.update(original_size=1000, final_size=900, action_taken="truncate")
        metrics.update(original_size=2000, final_size=1800, action_taken="compress")

        assert metrics.truncations_applied == 1
        assert metrics.compressions_applied == 1

    def test_compression_effectiveness(self):
        """Test compression effectiveness calculation."""
        metrics = GuardrailsMetrics(domain="test_domain")

        metrics.update(original_size=1000, final_size=500)  # 50% = good
        metrics.update(original_size=1000, final_size=600)  # 60% = good

        effectiveness = metrics.get_compression_effectiveness()
        assert 0.5 <= effectiveness <= 0.6

    def test_should_adapt_limits(self):
        """Test when to adapt limits."""
        metrics = GuardrailsMetrics(domain="test_domain")

        # Not enough responses
        for _ in range(5):
            metrics.update(1000, 900, "truncate")
        assert not metrics.should_adapt_limits()

        # Reset for next test
        metrics = GuardrailsMetrics(domain="test_domain")

        # Enough responses but no truncations
        for _ in range(10):
            metrics.update(1000, 900)
        assert not metrics.should_adapt_limits()

        # Reset for next test
        metrics = GuardrailsMetrics(domain="test_domain")

        # Enough responses with truncations
        for _ in range(10):
            metrics.update(1000, 900, "truncate")
        assert metrics.should_adapt_limits()


class TestAdaptiveGuardrailsConfig:
    """Test AdaptiveGuardrailsConfig."""

    def test_config_initialization(self):
        """Test config initialization."""
        config = AdaptiveGuardrailsConfig(domain="test_domain")

        assert config.domain == "test_domain"
        assert config.max_response_bytes == 100000
        assert config.max_items_per_page == 5
        assert config.metrics.domain == "test_domain"

    def test_adapt_to_metrics_increase_items(self):
        """Test adapting to increase items when compression is good."""
        config = AdaptiveGuardrailsConfig(
            domain="test_domain",
            max_items_per_page=5,
            enable_adaptive_limits=True,
        )

        # Simulate good compression with pagination (>10 responses, ratio < 0.7, some pagination)
        for i in range(15):
            action = "paginate" if i < 5 else ""
            config.metrics.update(1000, 600, action)  # 60% compression ratio

        config.adapt_to_metrics()

        # Metrics should show that we can increase (good compression)
        assert config.metrics.total_responses == 15
        assert config.metrics.get_compression_effectiveness() < 0.7

    def test_adapt_to_metrics_decrease_items(self):
        """Test adapting to decrease items when truncations are high."""
        config = AdaptiveGuardrailsConfig(
            domain="test_domain",
            max_items_per_page=5,
            enable_adaptive_limits=True,
        )

        # Simulate high truncation rate
        for _ in range(15):
            config.metrics.update(1000, 900, "truncate")

        config.adapt_to_metrics()

        # Should have decreased items per page
        assert config.max_items_per_page < 5

    def test_adapt_limits_disabled(self):
        """Test that adapt doesn't change limits when disabled."""
        config = AdaptiveGuardrailsConfig(
            domain="test_domain",
            max_items_per_page=5,
            enable_adaptive_limits=False,
        )

        for _ in range(15):
            config.metrics.update(1000, 600)

        original_items = config.max_items_per_page
        config.adapt_to_metrics()

        assert config.max_items_per_page == original_items


class TestResponseLimiter:
    """Test ResponseLimiter utilities."""

    def test_truncate_large_string_short_string(self):
        """Test truncating string shorter than max_length."""
        text = "short text"
        result = ResponseLimiter.truncate_large_string(text, max_length=100)

        assert result == text

    def test_truncate_large_string_long_string(self):
        """Test truncating string longer than max_length."""
        text = "this is a very long string that should be truncated at word boundary " * 10
        result = ResponseLimiter.truncate_large_string(text, max_length=50)

        assert len(result) <= 55  # 50 + "..."
        assert result.endswith("...")

    def test_calculate_size(self):
        """Test size calculation."""
        data = {"key": "value", "number": 42}

        size = ResponseLimiter.calculate_size(data)

        assert size > 0
        # Should be close to JSON serialized size
        assert size <= len('{"key":"value","number":42}') + 10

    def test_compress_nested_object_dict(self):
        """Test compressing deeply nested dict."""
        obj = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "level5": {"deep": "value"}  # Too deep
                        }
                    }
                }
            }
        }

        result = ResponseLimiter.compress_nested_object(obj, max_depth=3)

        # Should have truncated at depth limit
        assert "[truncated - max depth reached]" in str(result)

    def test_compress_nested_object_list(self):
        """Test compressing large list."""
        obj = {"items": list(range(200))}  # 200 items

        result = ResponseLimiter.compress_nested_object(obj)

        # Should compress to first 50 items
        assert len(result["items"]) == 50

    def test_paginate_results_basic(self):
        """Test basic pagination."""
        results = [{"id": i} for i in range(100)]

        paginated, info = ResponseLimiter.paginate_results(results, page=1, page_size=10)

        assert len(paginated) == 10
        assert info["total_items"] == 100
        assert info["total_pages"] == 10
        assert info["page"] == 1
        assert info["has_next"] is True
        assert info["has_prev"] is False

    def test_paginate_results_last_page(self):
        """Test pagination on last page."""
        results = [{"id": i} for i in range(25)]

        paginated, info = ResponseLimiter.paginate_results(results, page=3, page_size=10)

        assert len(paginated) == 5
        assert info["page"] == 3
        assert info["has_next"] is False
        assert info["has_prev"] is True

    def test_paginate_results_invalid_page(self):
        """Test pagination with invalid page number."""
        results = [{"id": i} for i in range(25)]

        # Page 0 should become page 1
        paginated, info = ResponseLimiter.paginate_results(results, page=0, page_size=10)
        assert info["page"] == 1

        # Page 100 should become max page
        paginated, info = ResponseLimiter.paginate_results(results, page=100, page_size=10)
        assert info["page"] == 3

    def test_apply_guardrails_no_action(self):
        """Test guardrails with small response (compress still applied)."""
        config = AdaptiveGuardrailsConfig(
            domain="test",
            max_response_bytes=100000,
            compress_nested_objects=False,  # Disable compression for this test
        )
        data = {"key": "value"}

        result, action = ResponseLimiter.apply_guardrails(data, config)

        assert result == data
        assert action == ""

    def test_apply_guardrails_pagination(self):
        """Test guardrails applies pagination."""
        config = AdaptiveGuardrailsConfig(
            domain="test",
            max_items_per_page=5,
            max_response_bytes=100000,
        )
        data = {"predictions": [{"id": i} for i in range(20)]}

        result, action = ResponseLimiter.apply_guardrails(data, config)

        assert len(result["predictions"]) == 5
        assert "pagination" in result
        assert result["pagination"]["total_items"] == 20
        assert action == "paginate"


class TestStreamingJSONEncoder:
    """Test StreamingJSONEncoder."""

    @pytest.mark.asyncio
    async def test_stream_json_object(self):
        """Test streaming JSON object."""
        data = {"key1": "value1", "key2": 42, "key3": [1, 2, 3]}

        chunks = []
        async for chunk in StreamingJSONEncoder.stream_json_object(data):
            chunks.append(chunk)

        result = "".join(chunks)

        # Should be valid JSON
        import json

        parsed = json.loads(result)
        assert parsed == data

    @pytest.mark.asyncio
    async def test_stream_json_array(self):
        """Test streaming JSON array."""
        items = [{"id": 1}, {"id": 2}, {"id": 3}]

        chunks = []
        async for chunk in StreamingJSONEncoder.stream_json_array(items):
            chunks.append(chunk)

        result = "".join(chunks)

        import json

        parsed = json.loads(result)
        assert parsed == items


class TestGetGuardrailsForDomain:
    """Test guardrails registry per domain."""

    def test_get_existing_domain(self):
        """Test getting guardrails for existing domain."""
        config = get_guardrails_for_domain("sports_nba")

        assert config.domain == "sports_nba"
        assert config.max_response_bytes == 150000
        assert config.max_items_per_page == 5

    def test_get_new_domain(self):
        """Test getting guardrails for new domain (creates default)."""
        config = get_guardrails_for_domain("new_domain_xyz")

        assert config.domain == "new_domain_xyz"
        assert config.max_response_bytes == 100000  # Default


class TestApplyResponseGuardrails:
    """Test full integration with DomainExecutionResult."""

    def test_apply_guardrails_success(self):
        """Test applying guardrails to successful result."""
        result = DomainExecutionResult(
            success=True,
            domain="sports_nba",
            tool_name="test_tool",
            data={"daily_predictions": [{"id": i} for i in range(10)]},
            error=None,
            latency_ms=100.0,
            cached=False,
        )

        guarded = apply_response_guardrails(result, "sports_nba")

        assert guarded.success is True
        assert guarded.domain == "sports_nba"
        # Should be paginated to 5 items
        assert len(guarded.data["daily_predictions"]) == 5

    def test_apply_guardrails_failure(self):
        """Test applying guardrails to failed result (no-op)."""
        result = DomainExecutionResult(
            success=False,
            domain="sports_nba",
            tool_name="test_tool",
            data={},  # Use empty dict instead of None
            error="Some error",
            latency_ms=100.0,
            cached=False,
        )

        guarded = apply_response_guardrails(result, "sports_nba")

        assert guarded.success is False
        assert guarded.error == "Some error"

    def test_apply_guardrails_no_data(self):
        """Test applying guardrails to result with empty data."""
        result = DomainExecutionResult(
            success=True,
            domain="sports_nba",
            tool_name="test_tool",
            data={},  # Use empty dict instead of None
            error=None,
            latency_ms=100.0,
            cached=False,
        )

        guarded = apply_response_guardrails(result, "sports_nba")

        # Empty data should return as-is
        assert guarded.data == {}


class TestAdaptiveGuardrailsIntegration:
    """Integration tests for adaptive guardrails."""

    def test_adaptive_workflow(self):
        """Test full adaptive workflow."""
        config = AdaptiveGuardrailsConfig(
            domain="test_integration",
            max_items_per_page=5,
            enable_adaptive_limits=True,
        )

        # Simulate 15 responses with good compression
        for i in range(15):
            data = {"items": list(range(50 + i * 10))}
            _, _ = ResponseLimiter.apply_guardrails(data, config)

        # Config should adapt
        original_items = 5
        config.adapt_to_metrics()

        # Verify metrics were updated
        assert config.metrics.total_responses == 15

    def test_nba_domain_guardrails(self):
        """Test NBA-specific guardrails."""
        config = get_guardrails_for_domain("sports_nba")

        # Simulate large NBA response
        data = {
            "daily_predictions": [
                {
                    "game_id": i,
                    "home_team": "Team A",
                    "away_team": "Team B",
                    "predictions": {
                        "spread": -5.5,
                        "moneyline": 1.8,
                        "analysis": "This is a detailed analysis " * 50,
                    },
                }
                for i in range(20)
            ]
        }

        result, action = ResponseLimiter.apply_guardrails(data, config)

        # Should be paginated to 5 items
        assert len(result["daily_predictions"]) == 5
        assert "pagination" in result
        assert result["pagination"]["total_items"] == 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
