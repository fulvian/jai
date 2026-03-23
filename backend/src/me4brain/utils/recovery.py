"""Recovery utilities for transient error handling.

Provides:
- Retry decorators with multiple strategies
- Circuit breaker pattern
- Fallback handlers
- Recovery hooks for LLM, DB, and external API calls
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, TypeVar

import structlog

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class ErrorCategory(str, Enum):
    """Categories of transient errors."""

    NETWORK = "network"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVICE_UNAVAILABLE = "service_unavailable"
    RESOURCE_EXHAUSTED = "resource_exhausted"
    UNKNOWN = "unknown"


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
    )


@dataclass
class CircuitState:
    """State for circuit breaker pattern."""

    failure_count: int = 0
    last_failure_time: float = 0.0
    state: str = "closed"
    recovery_timeout: float = 60.0
    failure_threshold: int = 5


@dataclass
class RecoveryResult:
    """Result of a recovery attempt."""

    success: bool
    value: Any = None
    error: Exception | None = None
    attempts: int = 1
    total_delay: float = 0.0
    category: ErrorCategory = ErrorCategory.UNKNOWN


class CircuitBreaker:
    """Circuit breaker for preventing cascading failures."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> None:
        self.name = name
        self.state = CircuitState(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        self._lock = asyncio.Lock()

    async def is_available(self) -> bool:
        """Check if circuit allows requests."""
        async with self._lock:
            if self.state.state == "open":
                elapsed = time.monotonic() - self.state.last_failure_time
                if elapsed >= self.state.recovery_timeout:
                    self.state.state = "half-open"
                    logger.info(
                        "circuit_breaker_half_open",
                        name=self.name,
                    )
                    return True
                return False
            return True

    async def record_success(self) -> None:
        """Record successful operation."""
        async with self._lock:
            if self.state.state == "half-open":
                self.state.state = "closed"
                logger.info(
                    "circuit_breaker_closed",
                    name=self.name,
                )
            self.state.failure_count = 0

    async def record_failure(self) -> None:
        """Record failed operation."""
        async with self._lock:
            self.state.failure_count += 1
            self.state.last_failure_time = time.monotonic()

            if self.state.failure_count >= self.state.failure_threshold:
                self.state.state = "open"
                logger.warning(
                    "circuit_breaker_open",
                    name=self.name,
                    failure_count=self.state.failure_count,
                )


def categorize_error(error: Exception) -> ErrorCategory:
    """Categorize an error for appropriate handling."""
    error_name = type(error).__name__.lower()
    error_msg = str(error).lower()

    if "timeout" in error_name or "timeout" in error_msg:
        return ErrorCategory.TIMEOUT

    if "rate" in error_msg or "limit" in error_msg or "429" in error_msg:
        return ErrorCategory.RATE_LIMIT

    if "connection" in error_name or "network" in error_name:
        return ErrorCategory.NETWORK

    if "unavailable" in error_msg or "503" in error_msg:
        return ErrorCategory.SERVICE_UNAVAILABLE

    if "exhausted" in error_msg or "resource" in error_msg:
        return ErrorCategory.RESOURCE_EXHAUSTED

    return ErrorCategory.UNKNOWN


def calculate_delay(
    attempt: int,
    config: RetryConfig,
    category: ErrorCategory,
) -> float:
    """Calculate delay for retry attempt with category-specific adjustments."""
    delay = config.base_delay * (config.exponential_base ** (attempt - 1))
    delay = min(delay, config.max_delay)

    if category == ErrorCategory.RATE_LIMIT:
        delay *= 2

    if category == ErrorCategory.SERVICE_UNAVAILABLE:
        delay *= 1.5

    if config.jitter:
        import random

        delay *= 0.5 + random.random()

    return delay


async def retry_with_backoff[T](
    func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    config: RetryConfig | None = None,
    on_retry: Callable[[int, Exception, float], None] | None = None,
    **kwargs: Any,
) -> RecoveryResult:
    """Execute function with retry and exponential backoff."""
    if config is None:
        config = RetryConfig()

    attempts = 0
    total_delay = 0.0
    last_error: Exception | None = None

    while attempts < config.max_attempts:
        attempts += 1
        try:
            result = await func(*args, **kwargs)
            return RecoveryResult(
                success=True,
                value=result,
                attempts=attempts,
                total_delay=total_delay,
            )
        except config.retryable_exceptions as e:
            last_error = e
            category = categorize_error(e)

            if attempts < config.max_attempts:
                delay = calculate_delay(attempts, config, category)
                total_delay += delay

                logger.warning(
                    "retry_attempt",
                    attempt=attempts,
                    max_attempts=config.max_attempts,
                    delay=delay,
                    error=str(e),
                    category=category.value,
                )

                if on_retry:
                    on_retry(attempts, e, delay)

                await asyncio.sleep(delay)
            else:
                break
        except Exception as e:
            last_error = e
            break

    return RecoveryResult(
        success=False,
        error=last_error,
        attempts=attempts,
        total_delay=total_delay,
        category=categorize_error(last_error) if last_error else ErrorCategory.UNKNOWN,
    )


def with_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: tuple[type[Exception], ...] | None = None,
):
    """Decorator for async functions with retry logic."""
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        max_delay=max_delay,
        retryable_exceptions=retryable_exceptions or RetryConfig.retryable_exceptions,
    )

    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            result = await retry_with_backoff(func, *args, config=config, **kwargs)
            if result.success:
                return result.value
            raise result.error or Exception("Retry failed")

        return wrapper

    return decorator


def with_circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
):
    """Decorator with circuit breaker pattern."""
    breaker = CircuitBreaker(
        name=name,
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
    )

    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            if not await breaker.is_available():
                raise Exception(f"Circuit breaker '{name}' is open")

            try:
                result = await func(*args, **kwargs)
                await breaker.record_success()
                return result
            except Exception:
                await breaker.record_failure()
                raise

        return wrapper

    return decorator


def with_fallback(
    fallback_func: Callable[..., Coroutine[Any, Any, Any]],
    fallback_on: tuple[type[Exception], ...] | None = None,
):
    """Decorator with fallback function on error."""
    if fallback_on is None:
        fallback_on = (Exception,)

    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T | Any]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T | Any:
            try:
                return await func(*args, **kwargs)
            except fallback_on as e:
                logger.warning(
                    "fallback_triggered",
                    function=func.__name__,
                    error=str(e),
                )
                return await fallback_func(*args, **kwargs)

        return wrapper

    return decorator


class RecoveryHooks:
    """Central registry for recovery hooks."""

    _hooks: dict[str, list[Callable]] = {}

    @classmethod
    def register(cls, event: str, hook: Callable) -> None:
        """Register a hook for an event."""
        if event not in cls._hooks:
            cls._hooks[event] = []
        cls._hooks[event].append(hook)

    @classmethod
    def trigger_sync(cls, event: str, *args: Any, **kwargs: Any) -> None:
        """Trigger all hooks for an event (sync version)."""
        hooks = cls._hooks.get(event, [])
        for hook in hooks:
            try:
                result = hook(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(result)
                    else:
                        loop.run_until_complete(result)
            except Exception as e:
                logger.error(
                    "recovery_hook_failed",
                    event=event,
                    error=str(e),
                )

    @classmethod
    async def trigger(cls, event: str, *args: Any, **kwargs: Any) -> None:
        """Trigger all hooks for an event (async version)."""
        hooks = cls._hooks.get(event, [])
        for hook in hooks:
            try:
                result = hook(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as e:
                logger.error(
                    "recovery_hook_failed",
                    event=event,
                    error=str(e),
                )

    @classmethod
    def clear(cls, event: str | None = None) -> None:
        """Clear hooks for an event or all hooks."""
        if event:
            cls._hooks.pop(event, None)
        else:
            cls._hooks.clear()


RECOVERY_EVENTS = {
    "llm_failure": "Called when LLM call fails",
    "tool_failure": "Called when tool execution fails",
    "db_failure": "Called when database operation fails",
    "cache_failure": "Called when cache operation fails",
    "external_api_failure": "Called when external API call fails",
}
