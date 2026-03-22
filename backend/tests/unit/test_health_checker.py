"""Unit tests for enhanced health check functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import time


class TestHealthCheckerEnhancements:
    """Tests for new health check components added in Phase 8."""

    @pytest.mark.asyncio
    async def test_check_tracing_initialized(self):
        """Test tracing health check when initialized."""
        from me4brain.api.routes.health import check_tracing

        with patch("me4brain.observability.tracing.is_trace_initialized", return_value=True):
            result = await check_tracing()

            assert result.name == "tracing"
            assert result.status == "ok"
            assert result.details["jaeger_configured"] is True

    @pytest.mark.asyncio
    async def test_check_tracing_not_initialized(self):
        """Test tracing health check when not initialized."""
        from me4brain.api.routes.health import check_tracing

        with patch("me4brain.observability.tracing.is_trace_initialized", return_value=False):
            result = await check_tracing()

            assert result.name == "tracing"
            assert result.status == "degraded"
            assert result.details["jaeger_configured"] is False

    @pytest.mark.asyncio
    async def test_check_tracing_exception(self):
        """Test tracing health check handles exceptions."""
        from me4brain.api.routes.health import check_tracing

        with patch(
            "me4brain.observability.tracing.is_trace_initialized",
            side_effect=Exception("Unknown error"),
        ):
            result = await check_tracing()

            assert result.name == "tracing"
            assert result.status == "error"
            assert result.error is not None


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    @pytest.mark.asyncio
    async def test_health_check_model_structure(self):
        """Test that health check returns proper model structure."""
        from me4brain.api.routes.health import HealthStatus

        # Verify the HealthStatus model exists and has proper fields
        assert hasattr(HealthStatus, "model_fields")
        fields = HealthStatus.model_fields
        assert "status" in fields
        assert "version" in fields
        assert "uptime_seconds" in fields
        assert "services" in fields

    @pytest.mark.asyncio
    async def test_service_health_model_structure(self):
        """Test that ServiceHealth model has proper structure."""
        from me4brain.api.routes.health import ServiceHealth

        # Verify the ServiceHealth model exists and has proper fields
        assert hasattr(ServiceHealth, "model_fields")
        fields = ServiceHealth.model_fields
        assert "name" in fields
        assert "status" in fields
        assert "latency_ms" in fields
        assert "error" in fields
        assert "details" in fields


class TestReadinessCheck:
    """Tests for readiness check endpoint."""

    @pytest.mark.asyncio
    async def test_readiness_response_model_structure(self):
        """Test ReadinessResponse model has proper structure."""
        from me4brain.api.routes.health import ReadinessResponse

        # Verify the ReadinessResponse model exists and has proper fields
        assert hasattr(ReadinessResponse, "model_fields")
        fields = ReadinessResponse.model_fields
        assert "ready" in fields
        assert "checks" in fields
        assert "critical_failures" in fields
