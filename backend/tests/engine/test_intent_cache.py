"""Tests for intent analysis caching."""

import time
import pytest

from me4brain.engine.intent_cache import (
    IntentCache,
    CacheEntry,
    CacheStats,
    get_intent_cache,
    reset_intent_cache,
)
from me4brain.engine.unified_intent_analyzer import (
    IntentAnalysis,
    IntentType,
    QueryComplexity,
)


class TestCacheEntry:
    """Test CacheEntry."""

    def test_cache_entry_creation(self):
        """Test creating cache entry."""
        analysis = IntentAnalysis(
            intent=IntentType.CONVERSATIONAL,
            domains=[],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.95,
            reasoning="greeting",
        )

        entry = CacheEntry(
            analysis=analysis,
            timestamp=time.time(),
            ttl_seconds=300.0,
        )

        assert entry.analysis == analysis
        assert entry.access_count == 0
        assert not entry.is_expired()

    def test_cache_entry_expiration(self):
        """Test cache entry expiration."""
        analysis = IntentAnalysis(
            intent=IntentType.CONVERSATIONAL,
            domains=[],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.95,
            reasoning="greeting",
        )

        # Create entry with very short TTL
        entry = CacheEntry(
            analysis=analysis,
            timestamp=time.time() - 10,  # 10 seconds ago
            ttl_seconds=5.0,  # 5 second TTL
        )

        assert entry.is_expired()

    def test_cache_entry_touch(self):
        """Test touching cache entry."""
        analysis = IntentAnalysis(
            intent=IntentType.CONVERSATIONAL,
            domains=[],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.95,
            reasoning="greeting",
        )

        entry = CacheEntry(
            analysis=analysis,
            timestamp=time.time(),
            ttl_seconds=300.0,
        )

        assert entry.access_count == 0
        entry.touch()
        assert entry.access_count == 1
        entry.touch()
        assert entry.access_count == 2


class TestCacheStats:
    """Test CacheStats."""

    def test_cache_stats_creation(self):
        """Test creating cache stats."""
        stats = CacheStats(
            total_queries=1000,
            cache_hits=400,
            cache_misses=600,
            evictions=10,
            avg_entry_size_bytes=500,
        )

        assert stats.total_queries == 1000
        assert stats.cache_hits == 400
        assert stats.cache_misses == 600

    def test_cache_stats_hit_rate(self):
        """Test cache hit rate calculation."""
        stats = CacheStats(
            total_queries=1000,
            cache_hits=400,
            cache_misses=600,
        )

        assert stats.hit_rate == 0.4

    def test_cache_stats_hit_rate_empty(self):
        """Test cache hit rate with no queries."""
        stats = CacheStats()
        assert stats.hit_rate == 0.0

    def test_cache_stats_to_dict(self):
        """Test converting stats to dict."""
        stats = CacheStats(
            total_queries=1000,
            cache_hits=400,
            cache_misses=600,
        )

        stats_dict = stats.to_dict()
        assert stats_dict["total_queries"] == 1000
        assert stats_dict["cache_hits"] == 400
        assert stats_dict["hit_rate"] == 0.4


class TestIntentCache:
    """Test IntentCache."""

    def test_cache_creation(self):
        """Test creating cache."""
        cache = IntentCache(max_size=1000, default_ttl_seconds=300.0)
        assert cache.get_size() == 0

    def test_cache_set_and_get(self):
        """Test setting and getting cache entry."""
        cache = IntentCache()

        analysis = IntentAnalysis(
            intent=IntentType.CONVERSATIONAL,
            domains=[],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.95,
            reasoning="greeting",
        )

        query = "Ciao"
        cache.set(query, analysis)

        retrieved = cache.get(query)
        assert retrieved is not None
        assert retrieved.intent == IntentType.CONVERSATIONAL

    def test_cache_miss(self):
        """Test cache miss."""
        cache = IntentCache()

        retrieved = cache.get("non-existent-query")
        assert retrieved is None

    def test_cache_with_context(self):
        """Test cache with context."""
        cache = IntentCache()

        analysis = IntentAnalysis(
            intent=IntentType.TOOL_REQUIRED,
            domains=["geo_weather"],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.95,
            reasoning="weather query",
        )

        query = "Che tempo fa?"
        context = "Roma"

        cache.set(query, analysis, context=context)

        # Should find with same context
        retrieved = cache.get(query, context=context)
        assert retrieved is not None

        # Should not find with different context
        retrieved = cache.get(query, context="Milano")
        assert retrieved is None

    def test_cache_expiration(self):
        """Test cache entry expiration."""
        cache = IntentCache(default_ttl_seconds=0.1)  # 100ms TTL

        analysis = IntentAnalysis(
            intent=IntentType.CONVERSATIONAL,
            domains=[],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.95,
            reasoning="greeting",
        )

        query = "Ciao"
        cache.set(query, analysis)

        # Should be in cache immediately
        assert cache.get(query) is not None

        # Wait for expiration
        time.sleep(0.2)

        # Should be expired
        assert cache.get(query) is None

    def test_cache_max_size(self):
        """Test cache max size enforcement."""
        cache = IntentCache(max_size=5)

        # Add 5 entries
        for i in range(5):
            analysis = IntentAnalysis(
                intent=IntentType.CONVERSATIONAL,
                domains=[],
                complexity=QueryComplexity.SIMPLE,
                confidence=0.95,
                reasoning=f"query{i}",
            )
            cache.set(f"query{i}", analysis)

        assert cache.get_size() == 5

        # Add 6th entry - should evict oldest
        analysis = IntentAnalysis(
            intent=IntentType.CONVERSATIONAL,
            domains=[],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.95,
            reasoning="query5",
        )
        cache.set("query5", analysis)

        assert cache.get_size() == 5

    def test_cache_clear(self):
        """Test clearing cache."""
        cache = IntentCache()

        analysis = IntentAnalysis(
            intent=IntentType.CONVERSATIONAL,
            domains=[],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.95,
            reasoning="greeting",
        )

        cache.set("query1", analysis)
        cache.set("query2", analysis)

        assert cache.get_size() == 2

        cache.clear()
        assert cache.get_size() == 0

    def test_cache_stats(self):
        """Test cache statistics."""
        cache = IntentCache()

        analysis = IntentAnalysis(
            intent=IntentType.CONVERSATIONAL,
            domains=[],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.95,
            reasoning="greeting",
        )

        # Add entry
        cache.set("query1", analysis)

        # Hit
        cache.get("query1")

        # Miss
        cache.get("query2")

        stats = cache.get_stats()
        assert stats.cache_hits == 1
        assert stats.cache_misses == 1
        assert stats.hit_rate == 0.5

    def test_cache_cleanup_expired(self):
        """Test cleaning up expired entries."""
        cache = IntentCache(default_ttl_seconds=0.1)

        analysis = IntentAnalysis(
            intent=IntentType.CONVERSATIONAL,
            domains=[],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.95,
            reasoning="greeting",
        )

        # Add entries
        cache.set("query1", analysis)
        cache.set("query2", analysis)

        assert cache.get_size() == 2

        # Wait for expiration
        time.sleep(0.2)

        # Cleanup
        removed = cache.cleanup_expired()
        assert removed == 2
        assert cache.get_size() == 0

    def test_cache_custom_ttl(self):
        """Test custom TTL per entry."""
        cache = IntentCache(default_ttl_seconds=10.0)

        analysis = IntentAnalysis(
            intent=IntentType.CONVERSATIONAL,
            domains=[],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.95,
            reasoning="greeting",
        )

        # Set with custom TTL
        cache.set("query1", analysis, ttl_seconds=0.1)

        # Should be in cache immediately
        assert cache.get("query1") is not None

        # Wait for expiration
        time.sleep(0.2)

        # Should be expired
        assert cache.get("query1") is None


class TestGlobalIntentCache:
    """Test global intent cache singleton."""

    def setup_method(self):
        """Reset cache before each test."""
        reset_intent_cache()

    def test_get_intent_cache_singleton(self):
        """Test that get_intent_cache returns singleton."""
        cache1 = get_intent_cache()
        cache2 = get_intent_cache()
        assert cache1 is cache2

    def test_reset_intent_cache(self):
        """Test resetting intent cache."""
        cache1 = get_intent_cache()

        analysis = IntentAnalysis(
            intent=IntentType.CONVERSATIONAL,
            domains=[],
            complexity=QueryComplexity.SIMPLE,
            confidence=0.95,
            reasoning="greeting",
        )

        cache1.set("query1", analysis)
        assert cache1.get_size() == 1

        reset_intent_cache()

        cache2 = get_intent_cache()
        assert cache2 is not cache1
        assert cache2.get_size() == 0
