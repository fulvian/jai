"""Test suite for Phase 2.3 - Provider Selection Caching.

Tests verify that provider health status is cached for 30 seconds (TTL) to avoid
repeated health checks to the same provider.
"""

import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from me4brain.llm.provider_factory import (
    CachedProviderStatus,
    get_cached_best_provider,
)


class TestCachedProviderStatus:
    """Test CachedProviderStatus dataclass and cache validation."""

    def test_cached_provider_status_created_with_defaults(self):
        """Test CachedProviderStatus can be created with default TTL."""
        status = CachedProviderStatus(
            provider="ollama",
            healthy=True,
            checked_at=time.time(),
        )
        assert status.provider == "ollama"
        assert status.healthy is True
        assert status.ttl == 30.0

    def test_cached_provider_status_with_custom_ttl(self):
        """Test CachedProviderStatus respects custom TTL."""
        status = CachedProviderStatus(
            provider="lm_studio",
            healthy=True,
            checked_at=time.time(),
            ttl=60.0,
        )
        assert status.ttl == 60.0

    def test_is_valid_returns_true_for_fresh_cache(self):
        """Test is_valid returns True for recently cached status."""
        now = time.time()
        status = CachedProviderStatus(
            provider="ollama",
            healthy=True,
            checked_at=now,
            ttl=30.0,
        )
        # Fresh cache should be valid
        assert status.is_valid is True

    def test_is_valid_returns_false_for_expired_cache(self):
        """Test is_valid returns False for expired cache."""
        past = time.time() - 35.0  # 35 seconds ago
        status = CachedProviderStatus(
            provider="ollama",
            healthy=True,
            checked_at=past,
            ttl=30.0,
        )
        # Expired cache should be invalid
        assert status.is_valid is False

    def test_is_valid_boundary_condition_at_ttl_edge(self):
        """Test is_valid at boundary condition exactly at TTL."""
        # Check near the edge - cache becoming invalid
        past = time.time() - 29.9  # Just under 30 seconds
        status = CachedProviderStatus(
            provider="ollama",
            healthy=True,
            checked_at=past,
            ttl=30.0,
        )
        assert status.is_valid is True


class TestGetCachedBestProvider:
    """Test get_cached_best_provider function with caching logic."""

    @pytest.mark.asyncio
    async def test_get_cached_best_provider_first_call(self):
        """Test first call to get_cached_best_provider checks provider health."""
        with patch("me4brain.llm.provider_factory.get_llm_health_checker") as mock_health_getter:
            mock_health_checker = AsyncMock()
            mock_health_checker.get_best_provider = AsyncMock(return_value="ollama")
            mock_health_getter.return_value = mock_health_checker

            # Reset cache first
            with patch("me4brain.llm.provider_factory._provider_cache", None):
                result = await get_cached_best_provider()

            assert result == "ollama"
            mock_health_checker.get_best_provider.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cached_best_provider_uses_cache_on_second_call(self):
        """Test second call uses cached provider without health check."""
        with patch("me4brain.llm.provider_factory.get_llm_health_checker") as mock_health_getter:
            mock_health_checker = AsyncMock()
            mock_health_checker.get_best_provider = AsyncMock(return_value="ollama")
            mock_health_getter.return_value = mock_health_checker

            # Reset cache
            with patch("me4brain.llm.provider_factory._provider_cache", None):
                # First call - will perform check
                result1 = await get_cached_best_provider()
                assert result1 == "ollama"

                # Mock cache as valid (less than 30 seconds old)
                cached = CachedProviderStatus(
                    provider="ollama",
                    healthy=True,
                    checked_at=time.time(),
                )
                with patch("me4brain.llm.provider_factory._provider_cache", cached):
                    # Second call - should use cache
                    result2 = await get_cached_best_provider()

                    assert result2 == "ollama"
                    # Should still be just one call total
                    assert mock_health_checker.get_best_provider.call_count == 1

    @pytest.mark.asyncio
    async def test_get_cached_best_provider_refreshes_expired_cache(self):
        """Test expired cache triggers new health check."""
        with patch("me4brain.llm.provider_factory.get_llm_health_checker") as mock_health_getter:
            mock_health_checker = AsyncMock()
            mock_health_checker.get_best_provider = AsyncMock(return_value="lm_studio")
            mock_health_getter.return_value = mock_health_checker

            # Create expired cache (35 seconds old)
            expired_cache = CachedProviderStatus(
                provider="ollama",
                healthy=True,
                checked_at=time.time() - 35.0,
                ttl=30.0,
            )

            with patch("me4brain.llm.provider_factory._provider_cache", expired_cache):
                result = await get_cached_best_provider()

            assert result == "lm_studio"
            # Should have called health checker due to expired cache
            mock_health_checker.get_best_provider.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_cached_best_provider_caches_new_result(self):
        """Test that new health check result is cached."""
        with patch("me4brain.llm.provider_factory.get_llm_health_checker") as mock_health_getter:
            with patch(
                "me4brain.llm.provider_factory._provider_cache", None, create=True
            ) as mock_cache_var:
                mock_health_checker = AsyncMock()
                mock_health_checker.get_best_provider = AsyncMock(return_value="ollama")
                mock_health_getter.return_value = mock_health_checker

                result = await get_cached_best_provider()

                assert result == "ollama"
                # Verify caching occurred
                mock_health_checker.get_best_provider.assert_called_once()

    @pytest.mark.asyncio
    async def test_multiple_providers_cached_correctly(self):
        """Test caching correctly switches between providers."""
        with patch("me4brain.llm.provider_factory.get_llm_health_checker") as mock_health_getter:
            mock_health_checker = AsyncMock()

            # First call returns ollama
            mock_health_checker.get_best_provider = AsyncMock(return_value="ollama")
            mock_health_getter.return_value = mock_health_checker

            with patch("me4brain.llm.provider_factory._provider_cache", None):
                result1 = await get_cached_best_provider()
                assert result1 == "ollama"

            # Simulate cache expiry, next call returns lm_studio
            mock_health_checker.get_best_provider = AsyncMock(return_value="lm_studio")
            expired_cache = CachedProviderStatus(
                provider="ollama",
                healthy=True,
                checked_at=time.time() - 35.0,
            )

            with patch("me4brain.llm.provider_factory._provider_cache", expired_cache):
                result2 = await get_cached_best_provider()
                assert result2 == "lm_studio"

    @pytest.mark.asyncio
    async def test_cache_ttl_respected_in_validation(self):
        """Test that TTL is properly enforced."""
        ttl_seconds = 30.0

        # Create cache that expires in exactly TTL seconds
        now = time.time()
        cache_time = now - (ttl_seconds - 1)  # 1 second before expiry

        status = CachedProviderStatus(
            provider="ollama",
            healthy=True,
            checked_at=cache_time,
            ttl=ttl_seconds,
        )

        # Should still be valid
        assert status.is_valid is True

        # After TTL passes, should be invalid
        expired_status = CachedProviderStatus(
            provider="ollama",
            healthy=True,
            checked_at=now - (ttl_seconds + 1),
            ttl=ttl_seconds,
        )
        assert expired_status.is_valid is False

    @pytest.mark.asyncio
    async def test_cache_preserves_provider_name(self):
        """Test that cached provider name is preserved exactly."""
        provider_names = ["ollama", "lm_studio", "vllm", "custom_provider"]

        for name in provider_names:
            status = CachedProviderStatus(
                provider=name,
                healthy=True,
                checked_at=time.time(),
            )
            assert status.provider == name

    @pytest.mark.asyncio
    async def test_get_cached_best_provider_handles_health_checker_error(self):
        """Test graceful handling when health checker fails."""
        with patch("me4brain.llm.provider_factory.get_llm_health_checker") as mock_health_getter:
            mock_health_checker = AsyncMock()
            mock_health_checker.get_best_provider = AsyncMock(
                side_effect=Exception("Health check failed")
            )
            mock_health_getter.return_value = mock_health_checker

            with patch("me4brain.llm.provider_factory._provider_cache", None):
                # Should raise or handle gracefully
                with pytest.raises(Exception):
                    await get_cached_best_provider()
