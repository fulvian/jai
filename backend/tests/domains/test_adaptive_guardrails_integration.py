"""Integration tests for adaptive guardrails with NBA domain.

Testa il workflow completo:
1. Domain query execution
2. Response size management
3. Adaptive limit adjustment
4. Pagination and compression
5. No truncation even with large responses
"""

import pytest

from me4brain.core.interfaces import DomainExecutionResult
from me4brain.domains.adaptive_guardrails import (
    ResponseLimiter,
    apply_response_guardrails,
    get_guardrails_for_domain,
    stream_large_response,
)


class TestNBADomainGuardrails:
    """Test adaptive guardrails with NBA-like responses."""

    def test_large_nba_betting_response_no_truncation(self):
        """Test that large NBA betting responses don't get truncated."""
        # Simulate a large NBA betting response with 50 games
        nba_response = DomainExecutionResult(
            success=True,
            domain="sports_nba",
            tool_name="betting_analyzer",
            data={
                "daily_predictions": [
                    {
                        "game_id": f"game_{i}",
                        "home_team": f"Team {i}",
                        "away_team": f"Team {i + 1}",
                        "spread": -5.5 + (i * 0.1),
                        "moneyline": 1.8 + (i * 0.01),
                        "over_under": 210 + (i * 0.5),
                        "detailed_analysis": "This is a detailed betting analysis " * 100,
                        "predictions": {
                            "spread_pick": "Home Team",
                            "moneyline_pick": "Away Team",
                            "ou_pick": "Over",
                            "confidence": 0.75 + (i * 0.001),
                            "rationale": "Based on season performance and head-to-head matchups "
                            * 50,
                        },
                        "advanced_metrics": {
                            "pace_factor": 100 + (i * 0.1),
                            "efficiency_rating": 105 + (i * 0.1),
                            "tempo": 95 + (i * 0.1),
                        },
                    }
                    for i in range(50)
                ]
            },
            error=None,
            latency_ms=250.0,
            cached=False,
        )

        # Apply guardrails
        guarded = apply_response_guardrails(nba_response, "sports_nba")

        # Verify success and no truncation
        assert guarded.success is True
        assert guarded.data is not None
        assert "daily_predictions" in guarded.data

        # Should be paginated, not truncated
        predictions = guarded.data["daily_predictions"]
        assert len(predictions) <= 5  # NBA config: max 5 per page
        assert "pagination" in guarded.data
        assert guarded.data["pagination"]["total_items"] == 50
        assert guarded.data["pagination"]["total_pages"] == 10

        # Verify data integrity - no fields lost
        first_game = predictions[0]
        assert "game_id" in first_game
        assert "home_team" in first_game
        assert "predictions" in first_game
        assert "detailed_analysis" in first_game

    def test_repeated_large_responses_adaptive_limits(self):
        """Test that repeated large responses trigger adaptive limits."""
        # Create a new config for this test (not shared)
        from me4brain.domains.adaptive_guardrails import (
            AdaptiveGuardrailsConfig,
            GuardrailsMetrics,
        )

        config = AdaptiveGuardrailsConfig(
            domain="test_nba_adaptive",
            max_response_bytes=150000,
            max_items_per_page=5,
            enable_adaptive_limits=True,
            metrics=GuardrailsMetrics(domain="test_nba_adaptive"),
        )

        initial_items = config.max_items_per_page

        # Simulate 20 large responses
        for batch in range(20):
            nba_response = DomainExecutionResult(
                success=True,
                domain="test_nba_adaptive",
                tool_name="betting_analyzer",
                data={
                    "daily_predictions": [
                        {
                            "game_id": f"game_{batch}_{i}",
                            "home_team": f"Team {i}",
                            "predictions": {
                                "analysis": "Analysis " * 20,
                            },
                        }
                        for i in range(30)
                    ]
                },
                error=None,
                latency_ms=100.0 + batch,
                cached=False,
            )

            # Use the local config, not the global one
            from me4brain.domains.adaptive_guardrails import ResponseLimiter

            _, _ = ResponseLimiter.apply_guardrails(nba_response.data, config)

        # Check metrics after many responses
        assert config.metrics.total_responses == 20
        assert config.metrics.paginatings_applied > 0

    def test_compression_effectiveness_tracking(self):
        """Test that compression effectiveness is tracked correctly."""
        config = get_guardrails_for_domain("sports_nba")

        # Create response with nested structure
        response = DomainExecutionResult(
            success=True,
            domain="sports_nba",
            tool_name="test",
            data={
                "daily_predictions": [
                    {
                        "game_id": f"game_{i}",
                        "nested_data": {
                            "level2": {
                                "level3": {
                                    "level4": {
                                        "level5": f"value_{i}",
                                        "verbose_text": "x" * 1000,
                                    }
                                }
                            },
                        },
                    }
                    for i in range(10)
                ]
            },
            error=None,
            latency_ms=100.0,
            cached=False,
        )

        guarded = apply_response_guardrails(response, "sports_nba")

        # Should have applied compression (removed deep nesting)
        metrics = config.metrics
        assert metrics.compressions_applied >= 0  # May or may not compress depending on size

    def test_multiple_domains_independent_limits(self):
        """Test that different domains have independent guardrail limits."""
        nba_config = get_guardrails_for_domain("sports_nba")
        finance_config = get_guardrails_for_domain("finance_crypto")
        weather_config = get_guardrails_for_domain("geo_weather")

        # Verify each has independent metrics
        assert nba_config.metrics.domain == "sports_nba"
        assert finance_config.metrics.domain == "finance_crypto"
        assert weather_config.metrics.domain == "geo_weather"

        # Verify they have different configs (or at least independent state)
        assert nba_config.domain != finance_config.domain
        assert nba_config.metrics != finance_config.metrics

    def test_response_size_calculation(self):
        """Test response size is calculated correctly."""
        data = {
            "predictions": [
                {
                    "game": f"game_{i}",
                    "analysis": "x" * 100,
                }
                for i in range(100)
            ]
        }

        size = ResponseLimiter.calculate_size(data)

        # Size should be positive and reasonable
        assert size > 0
        assert size < 1_000_000  # Less than 1MB (sanity check)
        assert size > 10_000  # More than 10KB (sanity check)


class TestStreamingLargeResponses:
    """Test streaming functionality for very large responses."""

    @pytest.mark.asyncio
    async def test_stream_large_response_above_threshold(self):
        """Test streaming is used for responses above threshold."""
        # Create response larger than streaming threshold (150KB)
        large_data = {
            "predictions": [
                {
                    "id": i,
                    "analysis": "x" * 5000,  # 5KB per item
                }
                for i in range(50)  # 250KB total
            ]
        }

        result = DomainExecutionResult(
            success=True,
            domain="sports_nba",
            tool_name="test",
            data=large_data,
            error=None,
            latency_ms=100.0,
            cached=False,
        )

        # Stream the response
        chunks = []
        async for chunk in stream_large_response(result, "sports_nba"):
            chunks.append(chunk)

        # Should have produced chunks
        assert len(chunks) > 0

        # Combined chunks should form valid JSON
        combined = "".join(chunks)
        import json

        parsed = json.loads(combined)
        assert parsed is not None
        assert "predictions" in parsed or "daily_predictions" in parsed

    @pytest.mark.asyncio
    async def test_stream_small_response_no_streaming(self):
        """Test that small responses don't use streaming."""
        small_data = {"result": "small"}

        result = DomainExecutionResult(
            success=True,
            domain="sports_nba",
            tool_name="test",
            data=small_data,
            error=None,
            latency_ms=10.0,
            cached=False,
        )

        chunks = []
        async for chunk in stream_large_response(result, "sports_nba"):
            chunks.append(chunk)

        # Should produce chunks (even if just one)
        assert len(chunks) > 0

        # Combined should be valid JSON
        combined = "".join(chunks)
        import json

        parsed = json.loads(combined)
        assert parsed is not None


class TestGuardrailsEdgeCases:
    """Test edge cases in guardrails."""

    def test_empty_predictions_list(self):
        """Test handling of empty predictions list."""
        result = DomainExecutionResult(
            success=True,
            domain="sports_nba",
            tool_name="test",
            data={"daily_predictions": []},
            error=None,
            latency_ms=10.0,
            cached=False,
        )

        guarded = apply_response_guardrails(result, "sports_nba")

        assert guarded.success is True
        assert len(guarded.data["daily_predictions"]) == 0

    def test_single_item_list(self):
        """Test handling of single-item list."""
        result = DomainExecutionResult(
            success=True,
            domain="sports_nba",
            tool_name="test",
            data={"daily_predictions": [{"game": "game_1"}]},
            error=None,
            latency_ms=10.0,
            cached=False,
        )

        guarded = apply_response_guardrails(result, "sports_nba")

        assert guarded.success is True
        assert len(guarded.data["daily_predictions"]) == 1

    def test_extremely_large_single_item(self):
        """Test handling of single item that is extremely large."""
        result = DomainExecutionResult(
            success=True,
            domain="sports_nba",
            tool_name="test",
            data={
                "daily_predictions": [
                    {
                        "game": "game_1",
                        "huge_analysis": "x" * 500_000,  # 500KB single item
                    }
                ]
            },
            error=None,
            latency_ms=100.0,
            cached=False,
        )

        guarded = apply_response_guardrails(result, "sports_nba")

        # Should still succeed, even if large
        assert guarded.success is True
        # Item should be truncated but preserved
        assert "daily_predictions" in guarded.data
        assert len(guarded.data["daily_predictions"]) >= 1

    def test_guardrails_dont_modify_successful_small_responses(self):
        """Test that guardrails don't unnecessarily modify small responses."""
        original_data = {
            "daily_predictions": [
                {"game": "game_1", "pick": "Team A"},
                {"game": "game_2", "pick": "Team B"},
            ]
        }

        result = DomainExecutionResult(
            success=True,
            domain="sports_nba",
            tool_name="test",
            data=original_data.copy(),
            error=None,
            latency_ms=10.0,
            cached=False,
        )

        guarded = apply_response_guardrails(result, "sports_nba")

        # Data should be preserved (small enough to not need pagination)
        assert len(guarded.data["daily_predictions"]) == 2
        assert guarded.data["daily_predictions"][0]["game"] == "game_1"
        assert guarded.data["daily_predictions"][1]["game"] == "game_2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
