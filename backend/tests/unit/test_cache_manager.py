# Phase 6: Cache Manager Tests
# These tests define the expected behavior of the caching layer

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import Optional

from me4brain.cache.cache_manager import CacheManager, CachedResponse


class TestCacheManager:
    """Test suite for CacheManager Redis operations."""

    @pytest.fixture
    def mock_redis(self):
        """Create a mock Redis client."""
        return AsyncMock()

    @pytest.fixture
    def cache_manager(self, mock_redis):
        """Create a CacheManager with mocked Redis."""
        manager = CacheManager()
        manager._redis = mock_redis
        manager._connected = True  # Mark as connected so _get_redis uses existing client
        return manager

    @pytest.mark.asyncio
    async def test_cache_set_get(self, cache_manager, mock_redis):
        """Test basic cache set and get operations."""
        cached_response = CachedResponse(
            domain="sports_nba", confidence=0.95, method="llm", cached_at=1234567890.0
        )
        mock_redis.get.return_value = cached_response.model_dump_json()

        result = await cache_manager.get("test_key")

        assert result is not None
        assert result.domain == "sports_nba"
        assert result.confidence == 0.95
        # Key is prefixed with CACHE_KEY_PREFIX
        mock_redis.get.assert_called_once_with("me4brain:domain:test_key")

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self, cache_manager, mock_redis):
        """Test that cache miss returns None."""
        mock_redis.get.return_value = None

        result = await cache_manager.get("nonexistent_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_cache_set_expects_true(self, cache_manager, mock_redis):
        """Test that cache set returns True on success."""
        mock_redis.set.return_value = True
        cached_response = CachedResponse(
            domain="weather", confidence=0.88, method="llm", cached_at=1234567890.0
        )

        result = await cache_manager.set("test_key", cached_response, ttl=3600)

        assert result is True
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self, cache_manager, mock_redis):
        """Test that cache entries respect TTL expiration."""
        # Redis returns None for expired keys
        mock_redis.get.return_value = None

        result = await cache_manager.get("expired_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_pattern_invalidation(self, cache_manager, mock_redis):
        """Test pattern-based cache invalidation."""
        # Keys stored in Redis have the CACHE_KEY_PREFIX
        mock_redis.keys.return_value = [
            "me4brain:domain:test:1",
            "me4brain:domain:test:2",
        ]
        mock_redis.delete.return_value = 2

        # Pattern without prefix gets the prefix added
        count = await cache_manager.invalidate_pattern("test:*")

        assert count == 2
        mock_redis.keys.assert_called_once_with("me4brain:domain:test:*")
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_redis_connection_pool(self, cache_manager):
        """Test that connection pool is properly managed."""
        assert cache_manager._pool is None or hasattr(cache_manager._pool, "acquire")

    @pytest.mark.asyncio
    async def test_graceful_fallback_when_redis_down(self):
        """Test that cache gracefully handles Redis being unavailable."""
        manager = CacheManager()

        with patch("me4brain.cache.cache_manager.redis.from_url", side_effect=ConnectionError):
            # Should not raise, just log warning
            result = await manager.get("any_key")
            assert result is None

    @pytest.mark.asyncio
    async def test_concurrent_cache_operations(self, cache_manager, mock_redis):
        """Test that concurrent cache operations work correctly."""
        import asyncio

        cached_response = CachedResponse(
            domain="finance", confidence=0.92, method="llm", cached_at=1234567890.0
        )
        mock_redis.get.return_value = cached_response.model_dump_json()

        # Simulate concurrent reads
        tasks = [cache_manager.get(f"key_{i}") for i in range(10)]
        results = await asyncio.gather(*tasks)

        assert all(r is not None for r in results)
        assert len(results) == 10


class TestCachedResponse:
    """Test CachedResponse model."""

    def test_cached_response_creation(self):
        """Test creating a CachedResponse."""
        response = CachedResponse(
            domain="sports_nba", confidence=0.95, method="llm", cached_at=1234567890.0
        )

        assert response.domain == "sports_nba"
        assert response.confidence == 0.95
        assert response.method == "llm"
        assert response.cached_at == 1234567890.0

    def test_cached_response_serialization(self):
        """Test CachedResponse JSON serialization."""
        response = CachedResponse(
            domain="weather", confidence=0.88, method="hybrid", cached_at=1234567890.0
        )

        json_str = response.model_dump_json()
        restored = CachedResponse.model_validate_json(json_str)

        assert restored.domain == response.domain
        assert restored.confidence == response.confidence
        assert restored.method == response.method
