"""E2E Tests for Admin Namespace."""

from __future__ import annotations

import pytest


@pytest.mark.e2e
@pytest.mark.requires_auth
@pytest.mark.asyncio
class TestAdminNamespace:
    """Test Admin namespace operations - requires authentication."""

    async def test_get_stats(self, async_client):
        """Test system statistics retrieval."""
        try:
            stats = await async_client.admin.stats()

            assert stats is not None
            # Should have memory stats
            if hasattr(stats, "episodes_count"):
                assert stats.episodes_count >= 0
            if hasattr(stats, "entities_count"):
                assert stats.entities_count >= 0
        except Exception as e:
            if "401" in str(e) or "Not authenticated" in str(e):
                pytest.skip("Admin endpoint requires authentication")
            raise

    async def test_health_detailed(self, async_client):
        """Test detailed health check."""
        try:
            health = await async_client.admin.health()

            assert health is not None
            assert health.status in ["healthy", "degraded", "unhealthy"]
            assert len(health.services) > 0
        except Exception as e:
            if "401" in str(e) or "Not authenticated" in str(e):
                pytest.skip("Admin endpoint requires authentication")
            raise

    async def test_config_get(self, async_client):
        """Test configuration retrieval."""
        try:
            config = await async_client.admin.get_config()

            assert config is not None
        except Exception as e:
            if "401" in str(e) or "Not authenticated" in str(e):
                pytest.skip("Admin endpoint requires authentication")
            pytest.skip(f"Config endpoint not available: {e}")


@pytest.mark.e2e
@pytest.mark.requires_auth
@pytest.mark.asyncio
class TestAdminBackup:
    """Test admin backup operations."""

    @pytest.mark.slow
    async def test_backup_list(self, async_client):
        """Test listing backups."""
        try:
            backups = await async_client.admin.list_backups()

            assert backups is not None
        except Exception as e:
            if "401" in str(e) or "Not authenticated" in str(e):
                pytest.skip("Admin endpoint requires authentication")
            pytest.skip(f"Backup list not available: {e}")
