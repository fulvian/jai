"""Tests for universal guardrails across all domains and routes.

Verifies che guardrails funzionano per:
- Tutti i domini (NBA, finance, weather, travel, tech, etc.)
- Tutte le rotte API (memory, semantic, engine, tools, skills, etc.)
- Tutti i tipi di risposta (JSON, streaming, paginated, compressed)
- Tutti gli edge case e scenari di errore
"""

import pytest

from me4brain.core.interfaces import DomainExecutionResult
from me4brain.domains.adaptive_guardrails import ResponseLimiter
from me4brain.domains.universal_guardrails import (
    configure_guardrails_for_domain,
    create_config_for_domain,
    get_universal_config,
    normalize_domain_key,
    reset_universal_registry,
)


class TestUniversalConfigRegistry:
    """Test universal guardrails configuration registry."""

    def setup_method(self):
        """Reset registry before each test."""
        reset_universal_registry()

    def test_get_universal_config_creates_on_demand(self):
        """Test that configs are created on-demand."""
        config = get_universal_config("sports_nba")
        assert config is not None
        assert config.domain == "sports_nba"
        assert config.max_items_per_page == 5

    def test_get_universal_config_caches(self):
        """Test that configs are cached."""
        config1 = get_universal_config("sports_nba")
        config2 = get_universal_config("sports_nba")
        assert config1 is config2  # Same object

    def test_normalize_domain_key(self):
        """Test domain key normalization."""
        assert normalize_domain_key("sports_nba") == "sports_nba"
        assert normalize_domain_key("/sports_nba/") == "sports_nba"
        assert normalize_domain_key("domains/sports_nba") == "sports_nba"
        assert normalize_domain_key("domains/sports_nba/query") == "sports_nba"

    def test_create_config_for_nba_domain(self):
        """Test NBA domain configuration."""
        config = create_config_for_domain("sports_nba")
        assert config.domain == "sports_nba"
        assert config.max_response_bytes == 150_000
        assert config.max_items_per_page == 5

    def test_create_config_for_finance_crypto(self):
        """Test finance crypto configuration."""
        config = create_config_for_domain("finance_crypto")
        assert config.domain == "finance_crypto"
        assert config.max_response_bytes == 200_000
        assert config.max_items_per_page == 10

    def test_create_config_for_api_route(self):
        """Test API route configuration (e.g., semantic, memory)."""
        semantic_config = create_config_for_domain("semantic")
        assert semantic_config.domain == "semantic"
        assert semantic_config.max_response_bytes == 200_000

        memory_config = create_config_for_domain("memory")
        assert memory_config.domain == "memory"
        assert memory_config.max_response_bytes == 100_000

    def test_create_config_for_unknown_domain(self):
        """Test that unknown domains get default config."""
        config = create_config_for_domain("unknown_domain_xyz")
        assert config.domain == "unknown_domain_xyz"
        assert config.max_response_bytes == 100_000  # Conservative default
        assert config.max_items_per_page == 5

    def test_configure_guardrails_for_domain_runtime(self):
        """Test runtime configuration updates."""
        config = configure_guardrails_for_domain(
            "sports_nba",
            max_response_bytes=50_000,
            max_items_per_page=3,
        )
        assert config.max_response_bytes == 50_000
        assert config.max_items_per_page == 3


class TestUniversalGuardrailsAcrossAllDomains:
    """Test guardrails work consistently across all domains."""

    def setup_method(self):
        reset_universal_registry()

    def test_guardrails_for_all_sports_domains(self):
        """Test guardrails configuration for all sports domains."""
        sports = ["sports_nba", "sports_football", "sports_soccer"]
        for domain in sports:
            config = get_universal_config(domain)
            assert config.domain == domain
            assert config.max_response_bytes > 0
            assert config.max_items_per_page > 0
            assert config.enable_adaptive_limits

    def test_guardrails_for_all_finance_domains(self):
        """Test guardrails configuration for all finance domains."""
        finance = ["finance_crypto", "finance_stocks", "finance_forex"]
        for domain in finance:
            config = get_universal_config(domain)
            assert config.domain == domain
            assert config.max_response_bytes >= 150_000
            assert config.enable_adaptive_limits

    def test_guardrails_for_all_api_routes(self):
        """Test guardrails configuration for all API routes."""
        routes = [
            "memory",
            "semantic",
            "engine",
            "tools",
            "skills",
            "working",
            "procedural",
            "monitoring",
        ]
        for route in routes:
            config = get_universal_config(route)
            assert config.domain == route
            assert config.enable_adaptive_limits

    def test_apply_guardrails_to_nba_response(self):
        """Test guardrails applied to NBA response."""
        result = DomainExecutionResult(
            success=True,
            domain="sports_nba",
            tool_name="betting_analyzer",
            data={
                "daily_predictions": [
                    {
                        "game_id": f"game_{i}",
                        "team_a": f"Team {i}",
                        "team_b": f"Team {i + 1}",
                        "analysis": "x" * 1000,
                    }
                    for i in range(50)
                ]
            },
            error=None,
            latency_ms=100.0,
            cached=False,
        )

        config = get_universal_config("sports_nba")
        guarded_data, metadata = ResponseLimiter.apply_guardrails(result.data, config)

        # Should paginate large response
        assert "pagination" in guarded_data
        assert len(guarded_data["daily_predictions"]) <= 5

    def test_apply_guardrails_to_finance_response(self):
        """Test guardrails applied to finance response."""
        result = DomainExecutionResult(
            success=True,
            domain="finance_crypto",
            tool_name="market_analyzer",
            data={
                "cryptocurrencies": [
                    {
                        "symbol": f"ASSET_{i}",
                        "price": 1000 + i * 10,
                        "detailed_analysis": "x" * 5000,  # Much larger per item
                    }
                    for i in range(100)
                ]
            },
            error=None,
            latency_ms=150.0,
            cached=False,
        )

        config = get_universal_config("finance_crypto")
        guarded_data, metadata = ResponseLimiter.apply_guardrails(result.data, config)

        # Should paginate if large enough
        assert "cryptocurrencies" in guarded_data
        assert len(guarded_data["cryptocurrencies"]) > 0

    def test_apply_guardrails_to_semantic_route_response(self):
        """Test guardrails applied to semantic route response."""
        data = {
            "entities": [
                {
                    "id": f"entity_{i}",
                    "name": f"Entity {i}",
                    "description": "x" * 2000,  # Larger descriptions
                }
                for i in range(100)
            ]
        }

        config = get_universal_config("semantic")
        guarded_data, metadata = ResponseLimiter.apply_guardrails(data, config)

        # Semantic allows many items, but data should be preserved
        assert "entities" in guarded_data
        assert len(guarded_data["entities"]) > 0

    def test_guardrails_preserve_data_integrity(self):
        """Test that guardrails preserve data integrity across all domains."""
        domains = ["sports_nba", "finance_crypto", "geo_weather", "semantic", "memory"]

        for domain in domains:
            config = get_universal_config(domain)

            # Create test data
            data = {
                "items": [
                    {
                        "id": f"item_{i}",
                        "value": f"value_{i}",
                        "nested": {"deep": f"data_{i}"},
                    }
                    for i in range(50)
                ]
            }

            guarded_data, metadata = ResponseLimiter.apply_guardrails(data, config)

            # Verify structure preserved
            assert "items" in guarded_data
            assert len(guarded_data["items"]) > 0

            # Verify fields preserved (no truncation)
            first_item = guarded_data["items"][0]
            assert "id" in first_item
            assert "value" in first_item


class TestUniversalGuardrailsEdgeCases:
    """Test edge cases for universal guardrails."""

    def setup_method(self):
        reset_universal_registry()

    def test_empty_response_all_domains(self):
        """Test empty responses are handled for all domains."""
        domains = ["sports_nba", "finance_crypto", "semantic", "memory"]

        for domain in domains:
            config = get_universal_config(domain)
            data = {"items": []}

            guarded_data, metadata = ResponseLimiter.apply_guardrails(data, config)

            assert "items" in guarded_data
            assert len(guarded_data["items"]) == 0

    def test_very_large_single_item(self):
        """Test very large single item is handled."""
        config = get_universal_config("sports_nba")

        data = {
            "items": [
                {
                    "id": "huge_item",
                    "data": "x" * 500_000,  # 500KB single item
                }
            ]
        }

        guarded_data, metadata = ResponseLimiter.apply_guardrails(data, config)

        # Should handle gracefully
        assert "items" in guarded_data
        assert len(guarded_data["items"]) >= 1

    def test_deeply_nested_structure(self):
        """Test deeply nested structures are handled."""
        config = get_universal_config("tech_coding")

        # Create deeply nested structure
        data = {
            "root": {"level1": {"level2": {"level3": {"level4": {"level5": {"data": "x" * 1000}}}}}}
        }

        guarded_data, metadata = ResponseLimiter.apply_guardrails(data, config)

        # Should compress deep nesting
        assert guarded_data is not None

    def test_mixed_data_types(self):
        """Test mixed data types are preserved."""
        config = get_universal_config("semantic")

        data = {
            "items": [
                {
                    "id": 1,
                    "name": "string",
                    "value": 42.5,
                    "active": True,
                    "tags": ["tag1", "tag2"],
                    "metadata": {"key": "value"},
                }
                for i in range(10)
            ]
        }

        guarded_data, metadata = ResponseLimiter.apply_guardrails(data, config)

        # Data types preserved
        first = guarded_data["items"][0]
        assert isinstance(first["id"], int)
        assert isinstance(first["name"], str)
        assert isinstance(first["value"], float)
        assert isinstance(first["active"], bool)
        assert isinstance(first["tags"], list)
        assert isinstance(first["metadata"], dict)


class TestUniversalGuardrailsPerformance:
    """Test performance characteristics of universal guardrails."""

    def setup_method(self):
        reset_universal_registry()

    def test_guardrails_doesnt_add_excessive_overhead(self):
        """Test that guardrails application is performant."""
        import time

        config = get_universal_config("sports_nba")

        # Create moderate-sized data
        data = {
            "items": [
                {
                    "id": f"item_{i}",
                    "data": f"value_{i}" * 10,
                }
                for i in range(100)
            ]
        }

        start = time.time()
        for _ in range(10):
            ResponseLimiter.apply_guardrails(data, config)
        elapsed = time.time() - start

        # Should be fast (< 1 second for 10 iterations)
        assert elapsed < 1.0

    def test_config_lookup_is_cached(self):
        """Test that config lookups are cached efficiently."""
        import time

        # First lookup
        start = time.time()
        config1 = get_universal_config("sports_nba")
        first_lookup = time.time() - start

        # Second lookup (cached)
        start = time.time()
        config2 = get_universal_config("sports_nba")
        second_lookup = time.time() - start

        # Cached lookup should be much faster
        assert config1 is config2
        assert second_lookup < first_lookup  # Cached is faster


class TestUniversalGuardrailsMetrics:
    """Test metrics tracking across all domains."""

    def setup_method(self):
        reset_universal_registry()

    def test_metrics_tracked_per_domain(self):
        """Test that metrics are tracked independently per domain."""
        nba_config = get_universal_config("sports_nba")
        finance_config = get_universal_config("finance_crypto")

        # Apply guardrails to different domains
        nba_data = {"items": [{"id": f"nba_{i}"} for i in range(50)]}
        finance_data = {"items": [{"id": f"fin_{i}"} for i in range(100)]}

        ResponseLimiter.apply_guardrails(nba_data, nba_config)
        ResponseLimiter.apply_guardrails(finance_data, finance_config)

        # Metrics should be independent
        assert nba_config.metrics.total_responses > 0
        assert finance_config.metrics.total_responses > 0
        assert nba_config.metrics is not finance_config.metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
