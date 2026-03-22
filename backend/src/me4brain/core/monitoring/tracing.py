"""Tracing Middleware - OpenTelemetry instrumentation per FastAPI."""

from __future__ import annotations

import os
from typing import Optional

import structlog

logger = structlog.get_logger(__name__)


def setup_tracing(
    service_name: str = "me4brain",
    otlp_endpoint: Optional[str] = None,
) -> None:
    """
    Configura OpenTelemetry tracing.

    Args:
        service_name: Nome servizio
        otlp_endpoint: Endpoint OTLP (default: env OTEL_EXPORTER_OTLP_ENDPOINT)
    """
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

    # Resource con info servizio
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": os.getenv("APP_VERSION", "0.1.0"),
        }
    )

    # Tracer provider
    provider = TracerProvider(resource=resource)

    # Exporter
    endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

    if endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("otel_otlp_exporter_configured", endpoint=endpoint)
        except ImportError:
            logger.warning("otlp_exporter_not_available")
    else:
        # Console exporter per dev
        if os.getenv("OTEL_DEBUG", "false").lower() == "true":
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    logger.info("otel_tracing_configured", service=service_name)


def instrument_fastapi(app) -> None:
    """
    Instrumenta FastAPI con OpenTelemetry.

    Args:
        app: FastAPI application
    """
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("fastapi_instrumented")

    except Exception as e:
        logger.warning("fastapi_instrumentation_failed", error=str(e))


def get_tracer(name: str = "me4brain"):
    """
    Ottiene tracer per spans custom.

    Args:
        name: Nome tracer

    Returns:
        Tracer instance
    """
    from opentelemetry import trace

    return trace.get_tracer(name)


class TracingContext:
    """
    Context manager per spans custom.

    Esempio:
        with TracingContext("process_query") as span:
            span.set_attribute("query", query)
            result = process(query)
    """

    def __init__(self, name: str, attributes: Optional[dict] = None):
        """
        Args:
            name: Nome span
            attributes: Attributi iniziali
        """
        self.name = name
        self.attributes = attributes or {}
        self._span = None

    def __enter__(self):
        tracer = get_tracer()
        self._span = tracer.start_span(self.name)

        for key, value in self.attributes.items():
            self._span.set_attribute(key, value)

        return self._span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._span.record_exception(exc_val)
            self._span.set_status(trace.Status(trace.StatusCode.ERROR, str(exc_val)))
        self._span.end()
        return False


async def trace_async(name: str, attributes: Optional[dict] = None):
    """
    Decorator per funzioni async con tracing.

    Esempio:
        @trace_async("fetch_data", {"source": "api"})
        async def fetch():
            ...
    """

    def decorator(func):
        async def wrapper(*args, **kwargs):
            tracer = get_tracer()
            with tracer.start_as_current_span(name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                return await func(*args, **kwargs)

        return wrapper

    return decorator


# Importa trace per uso in TracingContext
try:
    from opentelemetry import trace
except ImportError:
    trace = None
