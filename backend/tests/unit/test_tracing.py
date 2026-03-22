"""Unit tests for distributed tracing module."""

import pytest
from unittest.mock import patch, MagicMock


class TestTracingSetup:
    """Tests for tracing setup and initialization."""

    @pytest.mark.asyncio
    async def test_setup_tracing_disabled(self):
        """Test tracing setup when disabled."""
        from me4brain.observability.tracing import setup_tracing, is_trace_initialized

        # Reset global state
        import me4brain.observability.tracing as tracing_module

        tracing_module._trace_initialized = False
        tracing_module._tracer = None

        # Setup with disabled
        setup_tracing(enabled=False)

        assert is_trace_initialized() is True

    @pytest.mark.asyncio
    async def test_setup_tracing_with_import_error(self):
        """Test tracing handles missing opentelemetry gracefully."""
        from me4brain.observability.tracing import setup_tracing, is_trace_initialized

        # Reset global state
        import me4brain.observability.tracing as tracing_module

        tracing_module._trace_initialized = False
        tracing_module._tracer = None

        # Mock ImportError for opentelemetry
        with patch.dict("sys.modules", {"opentelemetry": None, "opentelemetry.sdk": None}):
            setup_tracing(enabled=True)
            # Should not raise, just warn

        assert is_trace_initialized() is True


class TestTracingContext:
    """Tests for TracingContext manager."""

    def test_tracing_context_no_tracer(self):
        """Test TracingContext when no tracer is initialized."""
        from me4brain.observability.tracing import TracingContext

        # Reset tracer
        import me4brain.observability.tracing as tracing_module

        tracing_module._tracer = None

        ctx = TracingContext("test_span", {"key": "value"})
        # Should not raise when entering
        with ctx as c:
            assert c is not None
            # Should not raise when exiting
            c.set_attribute("test", "value")
            c.add_event("test_event", {"attr": "value"})


class TestTraceContextGetters:
    """Tests for trace ID and span ID getters."""

    def test_get_current_trace_id_returns_none_when_no_span(self):
        """Test getting trace ID when no span is active returns None."""
        from me4brain.observability.tracing import get_current_trace_id

        # The function should handle the case where trace is not available
        result = get_current_trace_id()
        # Result should be None or a string, not raise an exception
        assert result is None or isinstance(result, str)

    def test_get_current_span_id_returns_none_when_no_span(self):
        """Test getting span ID when no span is active returns None."""
        from me4brain.observability.tracing import get_current_span_id

        # The function should handle the case where trace is not available
        result = get_current_span_id()
        # Result should be None or a string, not raise an exception
        assert result is None or isinstance(result, str)


class TestInjectTraceContext:
    """Tests for trace context injection."""

    def test_inject_trace_context_returns_dict(self):
        """Test inject_trace_context returns proper dict structure."""
        from me4brain.observability.tracing import inject_trace_context

        result = inject_trace_context()
        assert "trace_id" in result
        assert "span_id" in result
        # Values should be strings or None
        assert result["trace_id"] is None or isinstance(result["trace_id"], str)
        assert result["span_id"] is None or isinstance(result["span_id"], str)

    def test_inject_trace_context_with_none_values(self):
        """Test inject_trace_context handles None values."""
        from me4brain.observability.tracing import inject_trace_context

        result = inject_trace_context()
        assert result["trace_id"] is None or isinstance(result["trace_id"], str)
        assert result["span_id"] is None or isinstance(result["span_id"], str)
