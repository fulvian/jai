"""Caching layer for UnifiedIntentAnalyzer with TTL support.

This module provides:
- In-memory caching for identical queries
- TTL-based cache expiration
- Cache statistics and monitoring
- Batch processing support
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import structlog

from me4brain.engine.unified_intent_analyzer import IntentAnalysis

logger = structlog.get_logger(__name__)


@dataclass
class CacheEntry:
    """Single cache entry with TTL."""

    analysis: IntentAnalysis
    timestamp: float
    ttl_seconds: float
    access_count: int = 0
    last_accessed: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if entry has expired.

        Returns:
            True if expired, False otherwise
        """
        return time.time() - self.timestamp > self.ttl_seconds

    def touch(self) -> None:
        """Update last access time."""
        self.last_accessed = time.time()
        self.access_count += 1


@dataclass
class CacheStats:
    """Cache statistics."""

    total_queries: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    evictions: int = 0
    avg_entry_size_bytes: int = 0

    @property
    def hit_rate(self) -> float:
        """Get cache hit rate (0.0-1.0)."""
        total = self.cache_hits + self.cache_misses
        return self.cache_hits / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "total_queries": self.total_queries,
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "evictions": self.evictions,
            "hit_rate": self.hit_rate,
            "avg_entry_size_bytes": self.avg_entry_size_bytes,
        }


class IntentCache:
    """In-memory cache for intent analysis results with TTL support."""

    def __init__(self, max_size: int = 10000, default_ttl_seconds: float = 300.0):
        """Initialize cache.

        Args:
            max_size: Maximum number of entries
            default_ttl_seconds: Default TTL for entries
        """
        self._cache: dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl_seconds
        self._stats = CacheStats()

    def _hash_query(self, query: str, context: Optional[str] = None) -> str:
        """Hash query and context to create cache key.

        Args:
            query: User query
            context: Optional context

        Returns:
            Cache key
        """
        key_str = f"{query}:{context or ''}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def get(
        self,
        query: str,
        context: Optional[str] = None,
    ) -> Optional[IntentAnalysis]:
        """Get cached analysis if available.

        Args:
            query: User query
            context: Optional context

        Returns:
            IntentAnalysis if cached and not expired, None otherwise
        """
        key = self._hash_query(query, context)

        if key not in self._cache:
            self._stats.cache_misses += 1
            self._stats.total_queries += 1
            return None

        entry = self._cache[key]

        # Check if expired
        if entry.is_expired():
            del self._cache[key]
            self._stats.evictions += 1
            self._stats.cache_misses += 1
            self._stats.total_queries += 1
            logger.debug(
                "cache_entry_expired",
                query_preview=query[:50],
                age_seconds=time.time() - entry.timestamp,
            )
            return None

        # Cache hit
        entry.touch()
        self._stats.cache_hits += 1
        self._stats.total_queries += 1

        logger.debug(
            "cache_hit",
            query_preview=query[:50],
            access_count=entry.access_count,
        )

        return entry.analysis

    def set(
        self,
        query: str,
        analysis: IntentAnalysis,
        context: Optional[str] = None,
        ttl_seconds: Optional[float] = None,
    ) -> None:
        """Cache analysis result.

        Args:
            query: User query
            analysis: Intent analysis result
            context: Optional context
            ttl_seconds: TTL for this entry (None for default)
        """
        key = self._hash_query(query, context)
        ttl = ttl_seconds or self._default_ttl

        # Evict oldest entry if cache is full
        if len(self._cache) >= self._max_size:
            self._evict_oldest()

        entry = CacheEntry(
            analysis=analysis,
            timestamp=time.time(),
            ttl_seconds=ttl,
        )

        self._cache[key] = entry

        logger.debug(
            "cache_set",
            query_preview=query[:50],
            ttl_seconds=ttl,
            cache_size=len(self._cache),
        )

    def _evict_oldest(self) -> None:
        """Evict oldest entry from cache."""
        if not self._cache:
            return

        # Find entry with oldest last_accessed time
        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].last_accessed,
        )

        del self._cache[oldest_key]
        self._stats.evictions += 1

        logger.debug(
            "cache_eviction",
            reason="max_size_reached",
            cache_size=len(self._cache),
        )

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        logger.info("cache_cleared")

    def get_stats(self) -> CacheStats:
        """Get cache statistics.

        Returns:
            CacheStats object
        """
        # Calculate average entry size
        if self._cache:
            total_size = sum(
                len(entry.analysis.to_dict().__str__().encode())
                for entry in self._cache.values()
            )
            self._stats.avg_entry_size_bytes = total_size // len(self._cache)

        return self._stats

    def cleanup_expired(self) -> int:
        """Remove all expired entries.

        Returns:
            Number of entries removed
        """
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if entry.is_expired()
        ]

        for key in expired_keys:
            del self._cache[key]
            self._stats.evictions += 1

        if expired_keys:
            logger.info(
                "cache_cleanup_completed",
                expired_count=len(expired_keys),
                remaining=len(self._cache),
            )

        return len(expired_keys)

    def get_size(self) -> int:
        """Get current cache size.

        Returns:
            Number of entries in cache
        """
        return len(self._cache)


# Global cache instance
_intent_cache: Optional[IntentCache] = None


def get_intent_cache(
    max_size: int = 10000,
    default_ttl_seconds: float = 300.0,
) -> IntentCache:
    """Get global intent cache instance.

    Args:
        max_size: Maximum cache size (only used on first call)
        default_ttl_seconds: Default TTL (only used on first call)

    Returns:
        IntentCache singleton
    """
    global _intent_cache
    if _intent_cache is None:
        _intent_cache = IntentCache(max_size, default_ttl_seconds)
    return _intent_cache


def reset_intent_cache() -> None:
    """Reset intent cache (for testing)."""
    global _intent_cache
    if _intent_cache:
        _intent_cache.clear()
    _intent_cache = None
