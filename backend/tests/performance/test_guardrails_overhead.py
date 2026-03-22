"""
Performance tests for guardrails middleware overhead.

Measures:
- Middleware overhead per request (<5ms target)
- Domain key extraction performance
- Metrics update overhead
- Config lookup/caching effectiveness
"""

import time
import json
import pytest
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from me4brain.domains.adaptive_guardrails import (
    GuardrailsMetrics,
    AdaptiveGuardrailsConfig,
    ResponseLimiter,
)
from me4brain.domains.universal_guardrails import (
    normalize_domain_key,
    get_universal_config,
)


class TestDomainKeyExtractionPerformance:
    """Measure domain key extraction performance."""

    def test_domain_key_extraction_speed(self):
        """Domain key extraction should be <1ms even with complex paths."""
        test_paths = [
            "v1/domains/sports_nba",
            "v1/domains/finance_crypto",
            "v1/memory",
            "v1/engine",
            "v1/tools",
            "v1/skills",
        ]

        times = []
        for path in test_paths:
            start = time.perf_counter()
            for _ in range(1000):
                normalize_domain_key(path)
            elapsed = (time.perf_counter() - start) / 1000
            times.append(elapsed)

        # Average should be well under 1ms
        avg_time = sum(times) / len(times)
        assert avg_time < 0.001, f"Domain extraction took {avg_time * 1000:.3f}ms (target: <1ms)"

    def test_domain_key_extraction_consistency(self):
        """Domain key extraction should be consistent across calls."""
        path = "v1/domains/sports_nba"
        results = [normalize_domain_key(path) for _ in range(100)]
        assert len(set(results)) == 1, "Domain extraction should be deterministic"

    def test_path_extraction_routing(self):
        """Different path formats should extract correctly and quickly."""
        test_cases = [
            ("v1/domains/sports_nba", "sports_nba"),
            ("v1/memory", "memory"),
            ("v1/engine", "engine"),
            ("v1/tools", "tools"),
            ("v1/skills", "skills"),
        ]

        for path, expected in test_cases:
            start = time.perf_counter()
            test_result = ""
            for _ in range(100):
                test_result = normalize_domain_key(path)
            elapsed = (time.perf_counter() - start) / 100

            assert test_result == expected, f"Expected {expected}, got {test_result}"
            assert elapsed < 0.001, f"Path extraction took {elapsed * 1000:.3f}ms"


class TestConfigLookupCaching:
    """Measure config lookup and caching performance."""

    def test_config_first_lookup_speed(self):
        """First config lookup should be reasonable (<5ms)."""
        start = time.perf_counter()
        config = get_universal_config("sports_nba")
        elapsed = (time.perf_counter() - start) * 1000

        assert config is not None
        assert elapsed < 5, f"First config lookup took {elapsed:.2f}ms (target: <5ms)"

    def test_config_cached_lookup_speed(self):
        """Cached config lookup should be <0.1ms."""
        # First call to populate cache
        get_universal_config("sports_nba")

        # Second call should be cached
        start = time.perf_counter()
        test_config = None
        for _ in range(1000):
            test_config = get_universal_config("sports_nba")
        elapsed = (time.perf_counter() - start) / 1000 * 1000

        assert test_config is not None
        assert elapsed < 0.1, f"Cached config lookup took {elapsed:.3f}ms (target: <0.1ms)"

    def test_config_caching_across_domains(self):
        """Multiple domains should cache independently and quickly."""
        domains = [
            "sports_nba",
            "finance_crypto",
            "geo_weather",
            "tech_coding",
            "memory",
        ]

        times = []
        for domain in domains:
            start = time.perf_counter()
            for _ in range(100):
                config = get_universal_config(domain)
            elapsed = (time.perf_counter() - start) / 100 * 1000
            times.append(elapsed)

        avg_time = sum(times) / len(times)
        assert avg_time < 0.2, f"Average multi-domain lookup took {avg_time:.3f}ms"

    def test_unknown_domain_config_lookup(self):
        """Unknown domain config should fallback quickly."""
        start = time.perf_counter()
        config = get_universal_config("unknown_domain_xyz")
        elapsed = (time.perf_counter() - start) * 1000

        assert config is not None
        assert config.max_response_bytes == 100000  # 100KB default
        assert elapsed < 5, f"Unknown domain lookup took {elapsed:.2f}ms"


class TestMetricsUpdateOverhead:
    """Measure metrics tracking overhead."""

    def test_metrics_update_speed(self):
        """Metrics update should be <0.5ms."""
        metrics = GuardrailsMetrics(domain="sports_nba")

        start = time.perf_counter()
        for _ in range(1000):
            metrics.update(10000, 5000, "none")
        elapsed = (time.perf_counter() - start) / 1000 * 1000

        assert elapsed < 0.5, f"Metrics update took {elapsed:.3f}ms (target: <0.5ms)"

    def test_metrics_calculation_speed(self):
        """Metrics calculation should be <1ms even with large datasets."""
        metrics = GuardrailsMetrics(domain="sports_nba")

        # Simulate heavy usage
        for _ in range(100):
            metrics.update(10000, 5000, "none")
            metrics.update(10000, 5000, "compress")

        start = time.perf_counter()
        for _ in range(100):
            comp = metrics.get_compression_effectiveness()
            should_adapt = metrics.should_adapt_limits()
        elapsed = (time.perf_counter() - start) / 100 * 1000

        assert elapsed < 1, f"Metrics calculation took {elapsed:.3f}ms (target: <1ms)"

    def test_adaptive_limit_update_speed(self):
        """Adaptive limit update should be <2ms."""
        config = AdaptiveGuardrailsConfig(domain="sports_nba", max_response_bytes=150 * 1024)

        start = time.perf_counter()
        for _ in range(1000):
            config.adapt_to_metrics()
        elapsed = (time.perf_counter() - start) / 1000 * 1000

        assert elapsed < 2, f"Adaptive limit update took {elapsed:.3f}ms (target: <2ms)"


class TestResponseLimiterPerformance:
    """Measure response limiter performance."""

    def test_size_calculation_speed(self):
        """Size calculation should be <1ms."""
        large_response = {
            "data": [{"id": i, "text": "x" * 100} for i in range(100)],
            "metadata": {"total": 100, "page": 1},
        }

        start = time.perf_counter()
        for _ in range(1000):
            size = ResponseLimiter.calculate_size(large_response)
        elapsed = (time.perf_counter() - start) / 1000 * 1000

        assert elapsed < 1, f"Size calculation took {elapsed:.3f}ms (target: <1ms)"

    def test_pagination_speed(self):
        """Pagination should be <5ms for typical responses."""
        results = [{"id": i, "text": "x" * 100} for i in range(100)]

        start = time.perf_counter()
        for _ in range(10):
            paginated, meta = ResponseLimiter.paginate_results(results, page=1, page_size=10)
        elapsed = (time.perf_counter() - start) / 10 * 1000

        assert elapsed < 5, f"Pagination took {elapsed:.2f}ms (target: <5ms)"

    def test_compression_speed(self):
        """Compression should be <10ms for typical responses."""
        large_response = {
            "data": [{"id": i, "text": "x" * 100} for i in range(100)],
            "metadata": {"total": 100, "page": 1},
        }

        start = time.perf_counter()
        for _ in range(10):
            result = ResponseLimiter.compress_nested_object(large_response, depth=0, max_depth=3)
        elapsed = (time.perf_counter() - start) / 10 * 1000

        assert elapsed < 10, f"Compression took {elapsed:.2f}ms (target: <10ms)"


class TestMiddlewareOverheadEstimate:
    """Estimate total middleware overhead."""

    def test_combined_overhead_per_request(self):
        """
        Estimate total overhead per request:
        - Domain extraction: <1ms
        - Config lookup (cached): <0.1ms
        - Response size calculation: <1ms
        - Metrics update: <0.5ms
        - Total target: <5ms
        """
        config = get_universal_config("sports_nba")

        # Simulate a complete middleware cycle
        response = {
            "data": [{"id": i, "value": i * 2} for i in range(50)],
            "metadata": {"total": 50},
        }

        start = time.perf_counter()
        for _ in range(100):
            # Step 1: Domain extraction
            domain = normalize_domain_key("v1/domains/sports_nba")

            # Step 2: Config lookup (cached)
            config = get_universal_config(domain)

            # Step 3: Size calculation
            size = ResponseLimiter.calculate_size(response)

            # Step 4: Check if limiting needed
            if size > config.max_response_bytes:
                pass

            # Step 5: Metrics update
            config.metrics.update(size, size, "none")

        elapsed = (time.perf_counter() - start) / 100 * 1000

        assert elapsed < 5, f"Total middleware overhead {elapsed:.2f}ms (target: <5ms)"

    def test_worst_case_overhead(self):
        """Worst case with compression and pagination."""
        config = get_universal_config("sports_nba")

        # Large response requiring work
        response = {
            "data": [{"id": i, "text": "x" * 200} for i in range(200)],
            "metadata": {"total": 200},
        }

        start = time.perf_counter()
        for _ in range(10):
            # Domain extraction
            domain = normalize_domain_key("v1/domains/sports_nba")

            # Config lookup
            config = get_universal_config(domain)

            # Size check
            size = ResponseLimiter.calculate_size(response)

            # Compress if needed
            if size > config.max_response_bytes * 0.8:
                compressed = ResponseLimiter.compress_nested_object(response, depth=0, max_depth=3)
                compressed_size = ResponseLimiter.calculate_size(compressed)
                config.metrics.update(size, compressed_size, "compress")

            config.metrics.update(size, size, "compression")

        elapsed = (time.perf_counter() - start) / 10 * 1000

        assert elapsed < 20, f"Worst case overhead {elapsed:.2f}ms (target: <20ms)"

    def test_throughput_capacity(self):
        """Estimate requests/second capacity at <5ms per request."""
        config = get_universal_config("sports_nba")

        response = {
            "data": [{"id": i, "value": i} for i in range(50)],
        }

        start = time.perf_counter()
        request_count = 0

        while (time.perf_counter() - start) < 1.0:  # 1 second
            # Middleware cycle
            domain = normalize_domain_key("v1/domains/sports_nba")
            config = get_universal_config(domain)
            size = ResponseLimiter.calculate_size(response)
            config.metrics.update(size, size, "none")
            request_count += 1

        # At <5ms per request, should handle at least 200 req/sec
        assert request_count >= 200, f"Only {request_count} req/sec (target: >=200)"


class TestMemoryOverhead:
    """Measure memory usage of guardrails system."""

    def test_config_cache_memory(self):
        """Config cache should use minimal memory."""
        import sys

        # Load configs for multiple domains
        domains = [
            "sports_nba",
            "finance_crypto",
            "geo_weather",
            "tech_coding",
            "memory",
            "engine",
            "tools",
        ]

        for domain in domains:
            get_universal_config(domain)

        # Each config should be reasonable size
        config = get_universal_config("sports_nba")
        config_size = sys.getsizeof(config)

        # Metrics should be minimal
        metrics = config.metrics
        metrics_size = sys.getsizeof(metrics)

        # Total per domain should be <10KB
        total_size = config_size + metrics_size
        assert total_size < 10 * 1024, f"Config+metrics {total_size} bytes (target: <10KB)"

    def test_metrics_memory_growth(self):
        """Metrics tracking should not cause unbounded memory growth."""
        import sys

        metrics = GuardrailsMetrics(domain="sports_nba")
        initial_size = sys.getsizeof(metrics)

        # Record lots of data
        for _ in range(10000):
            metrics.update(5000, 5000, "none")
            metrics.update(10000, 5000, "compress")

        final_size = sys.getsizeof(metrics)
        growth = final_size - initial_size

        # Growth should be reasonable (lists can grow)
        assert growth < 100 * 1024, f"Metrics grew {growth} bytes (target: <100KB for 10k records)"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
