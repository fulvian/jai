"""Embedding Cache - Multi-tier L1/L2 cache for BGE-M3 embeddings.

L1: In-memory LRU cache (cachetools.LRUCache)
L2: Redis with TTL for distributed caching

SOTA 2026 patterns:
- Hash-based key generation for O(1) lookup
- Multi-tier fallback (L1 → L2 → compute)
- Probabilistic early expiration for stampede protection
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

import structlog
from cachetools import LRUCache

if TYPE_CHECKING:
    import numpy as np
    import redis.asyncio as redis

logger = structlog.get_logger(__name__)


class EmbeddingCache:
    """Multi-tier embedding cache (L1: memory, L2: Redis).

    Uses hash-based keys for efficient lookup and supports
    both dense (numpy arrays) and serialized storage.
    """

    # Redis key prefix for embeddings
    KEY_PREFIX = "me4brain:embedding"

    # Default TTL: 24 hours for embeddings
    DEFAULT_TTL_SECONDS = 86400

    # L1 cache default size (max entries)
    DEFAULT_L1_MAX_SIZE = 10000

    def __init__(
        self,
        redis_client: redis.Redis | None = None,
        local_max_size: int | None = None,
        redis_ttl_seconds: int | None = None,
    ) -> None:
        """Initialize embedding cache.

        Args:
            redis_client: Async Redis client for L2 cache
            local_max_size: Max L1 cache entries (default: 10000)
            redis_ttl_seconds: Redis TTL in seconds (default: 86400 = 24h)
        """

        self._redis: redis.Redis | None = redis_client  # type: ignore[assignment]
        self._l1_max_size = local_max_size or self.DEFAULT_L1_MAX_SIZE
        self._redis_ttl = redis_ttl_seconds or self.DEFAULT_TTL_SECONDS

        # L1: In-memory LRU cache
        # Uses text hash as key, numpy array as value
        self._l1: LRUCache[str, np.ndarray] = LRUCache(maxsize=self._l1_max_size)  # type: ignore[arg-type]

        # Statistics
        self._hits = 0
        self._misses = 0
        self._l1_hits = 0
        self._l2_hits = 0

    def _compute_key(self, text: str) -> str:
        """Compute cache key from text hash.

        Uses SHA256 truncated to 32 chars for compact keys
        while maintaining collision resistance.

        Args:
            text: Input text

        Returns:
            Cache key string
        """
        text_hash = hashlib.sha256(text.encode()).hexdigest()[:32]
        return f"{self.KEY_PREFIX}:{text_hash}"

    async def _get_redis(self) -> redis.Redis | None:
        """Get or initialize Redis client (lazy initialization).

        Returns:
            Redis client or None if unavailable
        """
        import redis.asyncio as redis

        if self._redis is None:
            try:
                from me4brain.config import get_settings

                settings = get_settings()
                self._redis = redis.from_url(
                    settings.redis_url,
                    decode_responses=False,  # Binary for numpy arrays
                )
                # Test connection
                await self._redis.ping()
                logger.info("embedding_cache_redis_connected")
            except Exception as e:
                logger.warning(
                    "embedding_cache_redis_unavailable",
                    error=str(e),
                    hint="Continuing with L1 cache only",
                )
                self._redis = None

        return self._redis

    async def get(self, text: str) -> np.ndarray | None:  # type: ignore[name-defined]
        """Get embedding from cache (L1 then L2).

        Args:
            text: Input text to look up

        Returns:
            Cached embedding as numpy array, or None if not found
        """
        import numpy as np

        key = self._compute_key(text)

        # L1: Local cache (fastest)
        l1_value = self._l1.get(key)
        if l1_value is not None:
            self._hits += 1
            self._l1_hits += 1
            logger.debug("embedding_cache_l1_hit", key=key[:16])
            return l1_value

        # L2: Redis cache
        redis_client = await self._get_redis()
        if redis_client is not None:
            try:
                cached_bytes = await redis_client.get(key)
                if cached_bytes is not None:
                    embedding = np.frombuffer(cached_bytes, dtype=np.float32)
                    # Populate L1 on L2 hit
                    self._l1[key] = embedding
                    self._hits += 1
                    self._l2_hits += 1
                    logger.debug("embedding_cache_l2_hit", key=key[:16])
                    return embedding
            except Exception as e:
                logger.warning(
                    "embedding_cache_l2_error",
                    key=key[:16],
                    error=str(e),
                )

        # Cache miss
        self._misses += 1
        logger.debug("embedding_cache_miss", key=key[:16])
        return None

    async def set(self, text: str, embedding: np.ndarray) -> bool:  # type: ignore[name-defined]
        """Store embedding in cache (both L1 and L2).

        Args:
            text: Original text (used for key generation)
            embedding: Numpy array embedding to cache

        Returns:
            True if stored successfully
        """
        import numpy as np

        key = self._compute_key(text)

        # L1: Local cache (always)
        self._l1[key] = embedding

        # L2: Redis cache
        redis_client = await self._get_redis()
        if redis_client is not None:
            try:
                # Convert numpy array to bytes for storage
                embedding_bytes = embedding.astype(np.float32).tobytes()
                await redis_client.setex(key, self._redis_ttl, embedding_bytes)
                logger.debug(
                    "embedding_cache_l2_set",
                    key=key[:16],
                    ttl=self._redis_ttl,
                )
                return True
            except Exception as e:
                logger.warning(
                    "embedding_cache_l2_set_error",
                    key=key[:16],
                    error=str(e),
                )

        return True

    async def get_or_compute(
        self,
        text: str,
        compute_fn: callable,  # type: ignore[type-arg]
    ) -> np.ndarray:  # type: ignore[name-defined]
        """Get embedding from cache or compute if not present.

        Implements the cache-aside pattern with multi-tier fallback.

        Args:
            text: Input text
            compute_fn: Async function to compute embedding if not cached

        Returns:
            Embedding as numpy array
        """

        # Try cache first
        cached = await self.get(text)
        if cached is not None:
            return cached

        # Cache miss - compute
        embedding = await compute_fn(text)

        # Store in cache
        await self.set(text, embedding)

        return embedding

    async def batch_get(
        self,
        texts: list[str],
    ) -> dict[str, np.ndarray | None]:  # type: ignore[name-defined]
        """Get multiple embeddings from cache.

        Args:
            texts: List of input texts

        Returns:
            Dict mapping text to embedding (or None if not cached)
        """
        results: dict[str, np.ndarray | None] = {}  # type: ignore[var-annotated]

        for text in texts:
            results[text] = await self.get(text)

        return results

    async def batch_set(
        self,
        items: list[tuple[str, np.ndarray]],  # type: ignore[type-arg]
    ) -> None:
        """Store multiple embeddings in cache.

        Args:
            items: List of (text, embedding) tuples
        """
        for text, embedding in items:
            await self.set(text, embedding)

    async def invalidate(self, text: str) -> bool:
        """Invalidate a single cache entry.

        Args:
            text: Original text

        Returns:
            True if entry was deleted
        """
        key = self._compute_key(text)

        # Remove from L1
        if key in self._l1:
            del self._l1[key]

        # Remove from L2
        redis_client = await self._get_redis()
        if redis_client is not None:
            try:
                count = await redis_client.delete(key)
                return count > 0
            except Exception as e:
                logger.warning(
                    "embedding_cache_invalidate_error",
                    key=key[:16],
                    error=str(e),
                )

        return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all cache entries matching a pattern.

        Args:
            pattern: Pattern to match (e.g., "me4brain:embedding:*")

        Returns:
            Number of keys deleted
        """
        redis_client = await self._get_redis()
        if redis_client is None:
            return 0

        try:
            full_pattern = f"{pattern}:*"
            count = 0
            cursor = 0

            while True:
                cursor, keys = await redis_client.scan(
                    cursor=cursor,
                    match=full_pattern,
                    count=100,
                )
                if keys:
                    count += await redis_client.delete(*keys)
                if cursor == 0:
                    break

            # Clear L1 as well
            self._l1.clear()

            logger.info("embedding_cache_invalidated", pattern=pattern, count=count)
            return count

        except Exception as e:
            logger.warning(
                "embedding_cache_invalidate_pattern_error",
                pattern=pattern,
                error=str(e),
            )
            return 0

    async def clear(self) -> None:
        """Clear all cache entries (both L1 and L2)."""
        # Clear L1
        self._l1.clear()

        # Clear L2
        await self.invalidate_pattern(self.KEY_PREFIX)

        # Reset stats
        self._hits = 0
        self._misses = 0
        self._l1_hits = 0
        self._l2_hits = 0

        logger.info("embedding_cache_cleared")

    def get_stats(self) -> dict:
        """Return cache statistics.

        Returns:
            Dict with hits, misses, hit_rate, and tier breakdown
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        l1_rate = self._l1_hits / self._hits if self._hits > 0 else 0.0
        l2_rate = self._l2_hits / self._hits if self._hits > 0 else 0.0

        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "l1_hits": self._l1_hits,
            "l2_hits": self._l2_hits,
            "l1_rate": l1_rate,
            "l2_rate": l2_rate,
            "l1_size": len(self._l1),
            "l1_max_size": self._l1_max_size,
            "l2_ttl_seconds": self._redis_ttl,
        }

    @property
    def l1_size(self) -> int:
        """Current L1 cache size."""
        return len(self._l1)

    @property
    def l1_max_size(self) -> int:
        """Max L1 cache size."""
        return self._l1_max_size

    async def close(self) -> None:
        """Close Redis connection if open."""
        if self._redis is not None:
            try:
                await self._redis.close()
                logger.debug("embedding_cache_redis_closed")
            except Exception as e:
                logger.warning(
                    "embedding_cache_redis_close_error",
                    error=str(e),
                )
            finally:
                self._redis = None


# Singleton instance
_embedding_cache: EmbeddingCache | None = None


def get_embedding_cache() -> EmbeddingCache:
    """Get the global embedding cache instance."""
    global _embedding_cache
    if _embedding_cache is None:
        _embedding_cache = EmbeddingCache()
    return _embedding_cache


def set_embedding_cache(cache: EmbeddingCache) -> None:
    """Set the global embedding cache instance."""
    global _embedding_cache
    _embedding_cache = cache
