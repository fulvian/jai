"""E2E Tests for Core Client and Health."""

from __future__ import annotations

import pytest


@pytest.mark.e2e
@pytest.mark.asyncio
class TestClientHealth:
    """Test client health and connectivity."""

    async def test_health_check(self, async_client):
        """Test API health check endpoint."""
        health = await async_client.health()

        assert health is not None
        assert isinstance(health, dict)
        assert health.get("status") == "healthy"
        assert "version" in health

    async def test_health_services(self, async_client):
        """Test individual service health."""
        health = await async_client.health()

        # Should have services
        services = health.get("services", [])
        assert len(services) > 0, "Should have at least one service"

        service_names = [s.get("name") for s in services]
        assert "redis" in service_names, "Redis should be in services"
        assert "qdrant" in service_names, "Qdrant should be in services"
        assert "neo4j" in service_names, "Neo4j should be in services"

        # All services should be OK
        for service in services:
            assert service.get("status") == "ok", f"Service {service.get('name')} should be OK"
            assert service.get("latency_ms", 0) > 0, (
                f"Service {service.get('name')} should have latency"
            )


@pytest.mark.e2e
@pytest.mark.asyncio
class TestClientContext:
    """Test client context manager."""

    async def test_async_context_manager(self):
        """Test async client as context manager."""
        import os

        from me4brain_sdk import AsyncMe4BrAInClient

        # Use same base_url as other tests
        base_url = os.getenv("ME4BRAIN_BASE_URL", "http://localhost:8089")

        async with AsyncMe4BrAInClient(
            base_url=base_url,
        ) as client:
            health = await client.health()
            assert health.get("status") == "healthy"

    def test_sync_client_creation(self):
        """Test sync client can be created (but not used in async context)."""
        import os

        from me4brain_sdk import Me4BrAInClient

        # Use same base_url as other tests
        base_url = os.getenv("ME4BRAIN_BASE_URL", "http://localhost:8089")

        # Just test creation, not execution (anyio needs special setup)
        client = Me4BrAInClient(
            base_url=base_url,
        )
        assert client is not None
        # Can't call close() here due to anyio requirements
