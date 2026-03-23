"""
Distributed Tracing - OpenTelemetry integration for distributed request tracing.

Provides:
- OpenTelemetry setup with Jaeger exporter
- Custom spans for key operations
- Correlation ID propagation
- FastAPI instrumentation
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

# Global tracer instance
_tracer = None
_trace_initialized = False


def get_tracer():
    """Get the global tracer instance."""
    global _tracer
    return _tracer


def is_trace_initialized() -> bool:
    """Check if tracing has been initialized."""
    global _trace_initialized
    return _trace_initialized


def setup_tracing(
    service_name: str = "me4brain",
    jaeger_host: str = "localhost",
    jaeger_port: int = 6831,
    enabled: bool = True,
) -> None:
    """Initialize OpenTelemetry tracing.

    Args:
        service_name: Name of this service
        jaeger_host: Jaeger agent host
        jaeger_port: Jaeger agent port
        enabled: Whether tracing is enabled
    """
    global _tracer, _trace_initialized

    if not enabled:
        logger.info("tracing_disabled")
        _trace_initialized = True
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.jaeger.thrift import JaegerExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # Create resource with service name
        resource = Resource.create({"service.name": service_name})

        # Create tracer provider
        provider = TracerProvider(resource=resource)

        # Configure Jaeger exporter
        jaeger_exporter = JaegerExporter(
            agent_host_name=jaeger_host,
            agent_port=jaeger_port,
        )

        # Add batch span processor
        provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))

        # Set global tracer provider
        trace.set_tracer_provider(provider)

        # Get tracer
        _tracer = trace.get_tracer(__name__)

        logger.info(
            "tracing_initialized",
            service_name=service_name,
            jaeger_host=jaeger_host,
            jaeger_port=jaeger_port,
        )
        _trace_initialized = True

    except ImportError as e:
        logger.warning(
            "tracing_import_error",
            error=str(e),
            message="opentelemetry packages not installed, tracing disabled",
        )
        _trace_initialized = True
    except Exception as e:
        logger.error(
            "tracing_init_error",
            error=str(e),
            message="Failed to initialize tracing, continuing without it",
        )
        _trace_initialized = True


def setup_fastapi_instrumentation(app) -> None:
    """Instrument FastAPI application with OpenTelemetry.

    Args:
        app: FastAPI application instance
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("fastapi_instrumented")
    except ImportError:
        logger.warning("opentelemetry-fastapi not installed, skipping instrumentation")
    except Exception as e:
        logger.error("fastapi_instrumentation_error", error=str(e))


def create_span(
    name: str,
    attributes: dict | None = None,
):
    """Create a new span context manager.

    Args:
        name: Name of the span
        attributes: Optional attributes to add to the span

    Usage:
        with create_span("classify_domain", {"query": "test"}) as span:
            # do work
            span.set_attribute("result", "success")
    """
    tracer = get_tracer()
    if tracer is None:
        # Return a no-op context manager
        from contextlib import nullcontext

        return nullcontext()

    span = tracer.start_as_current_span(name)
    if attributes:
        for key, value in attributes.items():
            span.set_attribute(key, value)
    return span


class TracingContext:
    """Context manager for creating traced spans.

    Usage:
        with TracingContext("operation_name", attr1="value1") as ctx:
            # do work
            ctx.set_attribute("key", "value")
    """

    def __init__(
        self,
        name: str,
        attributes: dict | None = None,
    ):
        self.name = name
        self.attributes = attributes or {}
        self.span = None

    def __enter__(self):
        tracer = get_tracer()
        if tracer is not None:
            self.span = tracer.start_as_current_span(self.name)
            for key, value in self.attributes.items():
                self.span.set_attribute(key, value)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span is not None:
            if exc_type is not None:
                self.span.set_attribute("error", True)
                self.span.set_attribute("error.type", exc_type.__name__)
                self.span.set_attribute("error.message", str(exc_val))
            self.span.end()
        return False

    def set_attribute(self, key: str, value) -> None:
        """Set an attribute on the current span."""
        if self.span is not None:
            self.span.set_attribute(key, value)

    def add_event(self, name: str, attributes: dict | None = None) -> None:
        """Add an event to the current span."""
        if self.span is not None:
            self.span.add_event(name, attributes=attributes or {})


def get_current_trace_id() -> str | None:
    """Get the current trace ID as a hex string.

    Returns:
        Trace ID or None if no active span
    """
    try:
        from opentelemetry import trace

        current_span = trace.get_current_span()
        if current_span is None:
            return None
        span_context = current_span.get_span_context()
        if span_context.is_valid:
            return format(span_context.trace_id, "032x")
        return None
    except Exception:
        return None


def get_current_span_id() -> str | None:
    """Get the current span ID as a hex string.

    Returns:
        Span ID or None if no active span
    """
    try:
        from opentelemetry import trace

        current_span = trace.get_current_span()
        if current_span is None:
            return None
        span_context = current_span.get_span_context()
        if span_context.is_valid:
            return format(span_context.span_id, "016x")
        return None
    except Exception:
        return None


def inject_trace_context() -> dict:
    """Get trace context as a dictionary for propagation.

    Returns:
        Dict with trace_id and span_id
    """
    return {
        "trace_id": get_current_trace_id(),
        "span_id": get_current_span_id(),
    }
