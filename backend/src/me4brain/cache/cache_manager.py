"""
Cache Manager - Redis-backed caching for domain classification.

Provides async Redis caching with TTL support, connection pooling,
and graceful fallback when Redis is unavailable.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import redis.asyncio as redis
import structlog
from pydantic import BaseModel

if TYPE_CHECKING:
    from redis.asyncio import ConnectionPool

    from me4brain.engine.hybrid_router.types import DomainClassification

logger = structlog.get_logger(__name__)

# Default Redis URL if not configured
DEFAULT_REDIS_URL = "redis://localhost:6379/0"

# Cache key prefix for domain classifications
CACHE_KEY_PREFIX = "me4brain:domain:"


class CachedResponse(BaseModel):
    """Cached domain classification response.

    Stores the serialized form of a DomainClassification result
    along with metadata for cache management.

    Note: The simplified form uses just 'domain' (singular) for backwards
    compatibility. For full multi-domain support, use 'domains' list.
    """

    # Primary domain (for backwards compatibility with single-domain tests)
    domain: str  # Primary domain name (e.g., 'sports_nba')

    # Classification metadata
    confidence: float
    method: str  # 'llm', 'fallback_keyword', etc.

    # Cache metadata
    cached_at: float  # Unix timestamp

    # Optional full domain list (for complete reconstruction)
    domains: list[dict[str, str]] | None = None

    # Optional query summary
    query_summary: str | None = None

    def to_domain_classification(self) -> DomainClassification:
        """Convert cached response back to DomainClassification.

        Returns:
            DomainClassification instance
        """
        # Lazy import to avoid circular dependency
        from me4brain.engine.hybrid_router.types import DomainClassification, DomainComplexity

        # Build domains list
        if self.domains:
            domain_objects = [
                DomainComplexity(name=d["name"], complexity=d.get("complexity", "medium"))
                for d in self.domains
            ]
        else:
            # Fallback to single domain
            domain_objects = [DomainComplexity(name=self.domain, complexity="medium")]

        return DomainClassification(
            domains=domain_objects,
            confidence=self.confidence,
            query_summary=self.query_summary or "",
        )


class CacheManager:
    """Redis-backed cache manager for domain classification results.

    Features:
    - Async Redis operations with connection pooling
    - TTL-based cache expiration
    - Pattern-based cache invalidation
    - Graceful fallback when Redis is unavailable
    """

    def __init__(
        self,
        redis_url: str | None = None,
        pool_size: int = 10,
        max_overflow: int = 20,
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
    ) -> None:
        """Initialize CacheManager.

        Args:
            redis_url: Redis connection URL
            pool_size: Connection pool size
            max_overflow: Max overflow connections
            socket_timeout: Socket read timeout
            socket_connect_timeout: Socket connect timeout
        """
        self._redis_url = redis_url or DEFAULT_REDIS_URL
        self._pool_size = pool_size
        self._max_overflow = max_overflow
        self._socket_timeout = socket_timeout
        self._socket_connect_timeout = socket_connect_timeout
        self._pool: ConnectionPool | None = None
        self._redis: redis.Redis | None = None
        self._connected = False

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis client with connection pooling."""
        if self._redis is None or not self._connected:
            try:
                self._pool = redis.ConnectionPool.from_url(
                    self._redis_url,
                    max_connections=self._pool_size,
                    socket_timeout=self._socket_timeout,
                    socket_connect_timeout=self._socket_connect_timeout,
                    decode_responses=True,
                )
                self._redis = redis.Redis(connection_pool=self._pool)
                # Test connection
                await self._redis.ping()
                self._connected = True
                logger.info("cache_manager_connected", redis_url=self._redis_url)
            except (redis.RedisError, OSError, ConnectionError) as e:
                logger.warning(
                    "cache_manager_connection_failed",
                    error=str(e),
                    redis_url=self._redis_url,
                )
                self._connected = False
                self._redis = None
                self._pool = None
                raise
        return self._redis

    async def get(self, key: str) -> CachedResponse | None:
        """Get cached response by key.

        Args:
            key: Cache key

        Returns:
            CachedResponse if found, None otherwise
        """
        try:
            client = await self._get_redis()
            full_key = f"{CACHE_KEY_PREFIX}{key}"
            data = await client.get(full_key)

            if data is None:
                return None

            return CachedResponse.model_validate_json(data)

        except (redis.RedisError, OSError, ConnectionError) as e:
            logger.warning("cache_get_failed", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: CachedResponse,
        ttl: int = 3600,
    ) -> bool:
        """Set cache value with TTL.

        Args:
            key: Cache key
            value: CachedResponse to store
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        try:
            client = await self._get_redis()
            full_key = f"{CACHE_KEY_PREFIX}{key}"
            data = value.model_dump_json()
            await client.set(full_key, data, ex=ttl)
            return True

        except (redis.RedisError, OSError, ConnectionError) as e:
            logger.warning("cache_set_failed", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Delete cache entry by key.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False otherwise
        """
        try:
            client = await self._get_redis()
            full_key = f"{CACHE_KEY_PREFIX}{key}"
            result = await client.delete(full_key)
            return result > 0

        except (redis.RedisError, OSError, ConnectionError) as e:
            logger.warning("cache_delete_failed", key=key, error=str(e))
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern.

        Args:
            pattern: Pattern to match (e.g., "me4brain:domain:*" or "domain:*")

        Returns:
            Number of keys deleted
        """
        try:
            client = await self._get_redis()
            # Ensure pattern has prefix
            if not pattern.startswith(CACHE_KEY_PREFIX):
                pattern = f"{CACHE_KEY_PREFIX}{pattern}"

            # Find all matching keys using keys() for simplicity in testing
            # Note: In production with large keyspaces, use scan_iter() instead
            keys = await client.keys(pattern)

            if not keys:
                return 0

            # Delete all matching keys
            deleted = await client.delete(*keys)
            logger.info("cache_pattern_invalidated", pattern=pattern, count=deleted)
            return deleted

        except (redis.RedisError, OSError, ConnectionError) as e:
            logger.warning("cache_invalidate_pattern_failed", pattern=pattern, error=str(e))
            return 0

    async def close(self) -> None:
        """Close Redis connection pool."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None
        self._connected = False
        logger.info("cache_manager_closed")

    async def health_check(self) -> dict[str, Any]:
        """Check Redis connection health.

        Returns:
            Health status dict
        """
        try:
            client = await self._get_redis()
            start = asyncio.get_event_loop().time()
            await client.ping()
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000

            return {
                "status": "up",
                "latency_ms": round(latency_ms, 2),
                "connected": self._connected,
            }

        except Exception as e:
            return {
                "status": "down",
                "error": str(e),
                "connected": False,
            }


# Singleton instance
_cache_manager: CacheManager | None = None


def get_cache_manager() -> CacheManager:
    """Get singleton CacheManager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager
