"""Diagnostic logging utilities for production debugging.

Provides structured logging helpers for:
- Latency tracking
- Decision tracing
- Error context enrichment
- Performance metrics
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


@dataclass
class LatencyMetrics:
    """Metrics for a single operation."""

    operation: str
    duration_ms: float
    success: bool
    error: str | None = None
    metadata: dict[str, Any] | None = None


class LatencyTracker:
    """Track latency for operations."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.start_time: float | None = None
        self.end_time: float | None = None
        self.metadata: dict[str, Any] = {}

    def start(self, **metadata: Any) -> None:
        """Start timing."""
        self.start_time = time.monotonic()
        self.metadata.update(metadata)

    def stop(self, success: bool = True, error: str | None = None) -> LatencyMetrics:
        """Stop timing and return metrics."""
        self.end_time = time.monotonic()
        duration_ms = (self.end_time - (self.start_time or 0)) * 1000

        return LatencyMetrics(
            operation=self.name,
            duration_ms=duration_ms,
            success=success,
            error=error,
            metadata=self.metadata if self.metadata else None,
        )


@asynccontextmanager
async def track_latency(
    operation: str,
    log_threshold_ms: float = 1000.0,
    **metadata: Any,
):
    """Context manager to track operation latency."""
    tracker = LatencyTracker(operation)
    tracker.start(**metadata)
    error: str | None = None
    success = True

    try:
        yield tracker
    except Exception as e:
        success = False
        error = str(e)
        raise
    finally:
        metrics = tracker.stop(success=success, error=error)

        if metrics.duration_ms >= log_threshold_ms:
            logger.warning(
                "slow_operation",
                operation=metrics.operation,
                duration_ms=round(metrics.duration_ms, 2),
                success=metrics.success,
                error=metrics.error,
                **(metrics.metadata or {}),
            )
        else:
            logger.debug(
                "operation_complete",
                operation=metrics.operation,
                duration_ms=round(metrics.duration_ms, 2),
                success=metrics.success,
            )


def log_decision(
    decision_point: str,
    decision: str,
    reasoning: str | None = None,
    confidence: float | None = None,
    alternatives: list[str] | None = None,
    **context: Any,
) -> None:
    """Log a routing/processing decision for tracing."""
    log_data = {
        "decision_point": decision_point,
        "decision": decision,
    }

    if reasoning:
        log_data["reasoning"] = reasoning
    if confidence is not None:
        log_data["confidence"] = confidence
    if alternatives:
        log_data["alternatives"] = alternatives
    if context:
        log_data.update(context)

    logger.info("decision_trace", **log_data)


def log_error_with_context(
    error: Exception,
    operation: str,
    context: dict[str, Any] | None = None,
    include_traceback: bool = False,
) -> None:
    """Log error with full context for debugging."""
    import traceback

    log_data = {
        "operation": operation,
        "error_type": type(error).__name__,
        "error_message": str(error),
    }

    if context:
        log_data["context"] = context

    if include_traceback:
        log_data["traceback"] = traceback.format_exc()

    logger.error("operation_error", **log_data)


def log_phase_transition(
    phase: str,
    from_stage: str,
    to_stage: str,
    duration_ms: float | None = None,
    **metadata: Any,
) -> None:
    """Log phase transitions in the query processing pipeline."""
    log_data = {
        "phase": phase,
        "from_stage": from_stage,
        "to_stage": to_stage,
    }

    if duration_ms is not None:
        log_data["duration_ms"] = round(duration_ms, 2)

    if metadata:
        log_data.update(metadata)

    logger.debug("phase_transition", **log_data)


def with_timing(
    operation: str | None = None,
    log_threshold_ms: float = 1000.0,
):
    """Decorator to log function timing."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        op_name = operation or func.__name__

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            start = time.monotonic()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.monotonic() - start) * 1000

                if duration_ms >= log_threshold_ms:
                    logger.warning(
                        "slow_function",
                        function=op_name,
                        duration_ms=round(duration_ms, 2),
                    )
                else:
                    logger.debug(
                        "function_timing",
                        function=op_name,
                        duration_ms=round(duration_ms, 2),
                    )

                return result
            except Exception as e:
                duration_ms = (time.monotonic() - start) * 1000
                log_error_with_context(
                    e,
                    operation=op_name,
                    context={"duration_ms": round(duration_ms, 2)},
                )
                raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> T:
            start = time.monotonic()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.monotonic() - start) * 1000

                if duration_ms >= log_threshold_ms:
                    logger.warning(
                        "slow_function",
                        function=op_name,
                        duration_ms=round(duration_ms, 2),
                    )
                else:
                    logger.debug(
                        "function_timing",
                        function=op_name,
                        duration_ms=round(duration_ms, 2),
                    )

                return result
            except Exception as e:
                duration_ms = (time.monotonic() - start) * 1000
                log_error_with_context(
                    e,
                    operation=op_name,
                    context={"duration_ms": round(duration_ms, 2)},
                )
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class QueryTrace:
    """Trace a complete query through the system."""

    def __init__(self, query: str, session_id: str | None = None) -> None:
        self.query = query
        self.session_id = session_id
        self.start_time = time.monotonic()
        self.phases: list[dict[str, Any]] = []
        self.decisions: list[dict[str, Any]] = []
        self.tools_called: list[str] = []
        self.errors: list[dict[str, Any]] = []

    def record_phase(
        self,
        phase: str,
        duration_ms: float,
        success: bool = True,
        **metadata: Any,
    ) -> None:
        """Record a processing phase."""
        self.phases.append(
            {
                "phase": phase,
                "duration_ms": round(duration_ms, 2),
                "success": success,
                "timestamp": time.monotonic() - self.start_time,
                **metadata,
            }
        )

    def record_decision(
        self,
        decision_point: str,
        decision: str,
        reasoning: str | None = None,
    ) -> None:
        """Record a routing decision."""
        self.decisions.append(
            {
                "decision_point": decision_point,
                "decision": decision,
                "reasoning": reasoning,
                "timestamp": time.monotonic() - self.start_time,
            }
        )

    def record_tool_call(self, tool_name: str, success: bool = True) -> None:
        """Record a tool call."""
        self.tools_called.append(tool_name)

    def record_error(self, error: Exception, phase: str | None = None) -> None:
        """Record an error."""
        self.errors.append(
            {
                "error_type": type(error).__name__,
                "error_message": str(error),
                "phase": phase,
                "timestamp": time.monotonic() - self.start_time,
            }
        )

    def finalize(self, success: bool = True) -> dict[str, Any]:
        """Finalize and return trace summary."""
        total_duration_ms = (time.monotonic() - self.start_time) * 1000

        summary = {
            "query_preview": self.query[:100],
            "session_id": self.session_id,
            "total_duration_ms": round(total_duration_ms, 2),
            "success": success,
            "phases_count": len(self.phases),
            "decisions_count": len(self.decisions),
            "tools_count": len(self.tools_called),
            "errors_count": len(self.errors),
        }

        if self.errors:
            summary["errors"] = self.errors

        logger.info("query_trace_complete", **summary)

        return summary
