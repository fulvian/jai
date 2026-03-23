"""Unit tests per Cache System."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from me4brain.utils.cache import _generate_cache_key, cached


class TestCacheKey:
    """Test per generazione cache key."""

    def test_generate_simple_key(self):
        """Test chiave semplice."""
        key = _generate_cache_key(
            prefix="test",
            func_name="get_weather",
            args=("Roma",),
            kwargs={},
        )
        assert key.startswith("test:get_weather:")
        assert len(key.split(":")[-1]) == 16  # Hash 16 chars

    def test_generate_key_with_kwargs(self):
        """Test chiave con kwargs."""
        key1 = _generate_cache_key(
            prefix="test",
            func_name="search",
            args=(),
            kwargs={"query": "test", "limit": 10},
        )
        key2 = _generate_cache_key(
            prefix="test",
            func_name="search",
            args=(),
            kwargs={"query": "test", "limit": 10},
        )
        # Stessi kwargs -> stessa chiave
        assert key1 == key2

    def test_generate_key_different_args(self):
        """Test chiavi diverse per args diversi."""
        key1 = _generate_cache_key("test", "func", ("a",), {})
        key2 = _generate_cache_key("test", "func", ("b",), {})
        assert key1 != key2

    def test_generate_key_exclude_args(self):
        """Test esclusione argomenti dalla chiave."""
        key1 = _generate_cache_key(
            prefix="test",
            func_name="func",
            args=(),
            kwargs={"session_id": "123", "query": "test"},
            exclude_args=["session_id"],
        )
        key2 = _generate_cache_key(
            prefix="test",
            func_name="func",
            args=(),
            kwargs={"session_id": "456", "query": "test"},
            exclude_args=["session_id"],
        )
        # Session_id escluso -> stessa chiave
        assert key1 == key2


class TestCachedDecorator:
    """Test per decorator @cached."""

    @pytest.mark.asyncio
    async def test_cached_no_manager(self):
        """Test senza cache manager (bypass)."""
        call_count = 0

        @cached(ttl=60)
        async def expensive_func(x: int) -> int:
            nonlocal call_count
            call_count += 1
            return x * 2

        # Senza cache manager, esegue direttamente
        with patch("me4brain.core.cache.manager.get_cache_manager", return_value=None):
            result = await expensive_func(5)
            assert result == 10
            assert call_count == 1

    @pytest.mark.asyncio
    async def test_cached_hit(self):
        """Test cache hit."""
        mock_manager = MagicMock()
        mock_manager.get = AsyncMock(return_value={"cached": True})
        mock_manager.set = AsyncMock()

        @cached(ttl=60, key_prefix="test")
        async def get_data(id: int) -> dict:
            return {"cached": False}

        with patch(
            "me4brain.core.cache.manager.get_cache_manager",
            return_value=mock_manager,
        ):
            result = await get_data(1)

        assert result == {"cached": True}
        mock_manager.get.assert_called_once()
        mock_manager.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_cached_miss_and_set(self):
        """Test cache miss e salvataggio."""
        mock_manager = MagicMock()
        mock_manager.get = AsyncMock(return_value=None)  # Miss
        mock_manager.set = AsyncMock()

        @cached(ttl=120, key_prefix="test")
        async def compute(x: int) -> int:
            return x * 3

        with patch(
            "me4brain.core.cache.manager.get_cache_manager",
            return_value=mock_manager,
        ):
            result = await compute(7)

        assert result == 21
        mock_manager.get.assert_called_once()
        mock_manager.set.assert_called_once()
        # Verifica TTL
        call_args = mock_manager.set.call_args
        assert call_args.kwargs["ttl"] == 120


class TestCacheManager:
    """Test per CacheManager."""

    @pytest.mark.asyncio
    async def test_get_ttl_for_domain(self):
        """Test TTL per domain."""
        from me4brain.core.cache.manager import CacheManager

        mock_redis = MagicMock()
        manager = CacheManager(mock_redis)

        assert manager.get_ttl_for_domain("geo_weather") == 1800
        assert manager.get_ttl_for_domain("finance_crypto") == 300
        assert manager.get_ttl_for_domain("unknown") == 600  # default

    @pytest.mark.asyncio
    async def test_set_ttl_for_domain(self):
        """Test impostazione TTL custom."""
        from me4brain.core.cache.manager import CacheManager

        mock_redis = MagicMock()
        manager = CacheManager(mock_redis)

        manager.set_ttl_for_domain("custom_domain", 7200)
        assert manager.get_ttl_for_domain("custom_domain") == 7200

    @pytest.mark.asyncio
    async def test_cache_hit_rate(self):
        """Test calcolo hit rate."""
        from me4brain.core.cache.manager import CacheStats

        stats = CacheStats(hits=80, misses=20)
        assert stats.hit_rate == 0.8

        empty_stats = CacheStats()
        assert empty_stats.hit_rate == 0.0
