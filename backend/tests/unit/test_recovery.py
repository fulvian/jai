"""Tests for recovery module."""

import asyncio

import pytest

from me4brain.utils.recovery import (
    categorize_error,
    calculate_delay,
    CircuitBreaker,
    ErrorCategory,
    RecoveryHooks,
    RetryConfig,
    retry_with_backoff,
    with_retry,
    with_circuit_breaker,
    with_fallback,
)


class TestErrorCategory:
    """Tests for error categorization."""

    def test_categorize_timeout(self):
        error = TimeoutError("Connection timed out")
        assert categorize_error(error) == ErrorCategory.TIMEOUT

    def test_categorize_connection(self):
        error = ConnectionError("Failed to connect")
        assert categorize_error(error) == ErrorCategory.NETWORK

    def test_categorize_rate_limit(self):
        error = Exception("Rate limit exceeded: 429")
        assert categorize_error(error) == ErrorCategory.RATE_LIMIT

    def test_categorize_unknown(self):
        error = ValueError("Some value error")
        assert categorize_error(error) == ErrorCategory.UNKNOWN


class TestRetryConfig:
    """Tests for RetryConfig."""

    def test_default_config(self):
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0

    def test_custom_config(self):
        config = RetryConfig(max_attempts=5, base_delay=0.5)
        assert config.max_attempts == 5
        assert config.base_delay == 0.5


class TestCalculateDelay:
    """Tests for delay calculation."""

    def test_exponential_backoff(self):
        config = RetryConfig(jitter=False)

        delay1 = calculate_delay(1, config, ErrorCategory.NETWORK)
        delay2 = calculate_delay(2, config, ErrorCategory.NETWORK)
        delay3 = calculate_delay(3, config, ErrorCategory.NETWORK)

        assert delay1 == 1.0
        assert delay2 == 2.0
        assert delay3 == 4.0

    def test_rate_limit_multiplier(self):
        config = RetryConfig(jitter=False)

        normal_delay = calculate_delay(1, config, ErrorCategory.NETWORK)
        rate_limit_delay = calculate_delay(1, config, ErrorCategory.RATE_LIMIT)

        assert rate_limit_delay == normal_delay * 2

    def test_max_delay_cap(self):
        config = RetryConfig(base_delay=100, max_delay=30, jitter=False)

        delay = calculate_delay(10, config, ErrorCategory.NETWORK)

        assert delay == 30.0


class TestCircuitBreaker:
    """Tests for CircuitBreaker."""

    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        breaker = CircuitBreaker("test")
        assert await breaker.is_available()

    @pytest.mark.asyncio
    async def test_opens_after_threshold(self):
        breaker = CircuitBreaker("test", failure_threshold=2)

        await breaker.record_failure()
        assert await breaker.is_available()

        await breaker.record_failure()
        assert not await breaker.is_available()

    @pytest.mark.asyncio
    async def test_closes_on_success(self):
        breaker = CircuitBreaker("test_close", failure_threshold=1, recovery_timeout=1.0)

        await breaker.record_failure()
        assert not await breaker.is_available()

        # Wait for recovery timeout
        await asyncio.sleep(1.1)
        assert await breaker.is_available()  # half-open

        await breaker.record_success()
        assert await breaker.is_available()  # closed again


class TestRetryWithBackoff:
    """Tests for retry_with_backoff function."""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        async def success_func():
            return "success"

        result = await retry_with_backoff(success_func)

        assert result.success
        assert result.value == "success"
        assert result.attempts == 1

    @pytest.mark.asyncio
    async def test_retry_on_transient_error(self):
        call_count = 0

        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary failure")
            return "success"

        config = RetryConfig(
            max_attempts=3,
            base_delay=0.01,
            retryable_exceptions=(ConnectionError,),
        )
        result = await retry_with_backoff(flaky_func, config=config)

        assert result.success
        assert result.value == "success"
        assert result.attempts == 3

    @pytest.mark.asyncio
    async def test_fail_after_max_attempts(self):
        async def always_fail():
            raise ConnectionError("Always fails")

        config = RetryConfig(
            max_attempts=2,
            base_delay=0.01,
            retryable_exceptions=(ConnectionError,),
        )
        result = await retry_with_backoff(always_fail, config=config)

        assert not result.success
        assert result.attempts == 2


class TestWithRetry:
    """Tests for with_retry decorator."""

    @pytest.mark.asyncio
    async def test_decorator_success(self):
        @with_retry(max_attempts=2, base_delay=0.01)
        async def success():
            return "ok"

        result = await success()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_decorator_retry(self):
        call_count = 0

        @with_retry(max_attempts=3, base_delay=0.01)
        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("fail")
            return "ok"

        result = await flaky()
        assert result == "ok"
        assert call_count == 2


class TestWithCircuitBreaker:
    """Tests for with_circuit_breaker decorator."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_decorator(self):
        @with_circuit_breaker("test", failure_threshold=1)
        async def success():
            return "success"

        result = await success()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens(self):
        call_count = 0

        @with_circuit_breaker("test_open", failure_threshold=1)
        async def failing():
            nonlocal call_count
            call_count += 1
            raise ValueError("error")

        with pytest.raises(ValueError):
            await failing()


class TestWithFallback:
    """Tests for with_fallback decorator."""

    @pytest.mark.asyncio
    async def test_fallback_on_error(self):
        async def fallback(*args, **kwargs):
            return "fallback"

        @with_fallback(fallback)
        async def failing():
            raise ValueError("error")

        result = await failing()
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_no_fallback_on_success(self):
        async def fallback(*args, **kwargs):
            return "fallback"

        @with_fallback(fallback)
        async def success():
            return "success"

        result = await success()
        assert result == "success"


class TestRecoveryHooks:
    """Tests for RecoveryHooks."""

    def test_register_and_trigger(self):
        called = []

        def hook(value):
            called.append(value)

        RecoveryHooks.register("test_event", hook)
        RecoveryHooks.trigger_sync("test_event", "test_value")

        assert "test_value" in called
        RecoveryHooks.clear("test_event")

    @pytest.mark.asyncio
    async def test_async_hook(self):
        called = []

        async def async_hook(value):
            called.append(value)

        RecoveryHooks.register("async_event", async_hook)
        await RecoveryHooks.trigger("async_event", "async_value")

        assert "async_value" in called
        RecoveryHooks.clear("async_event")

    def test_clear_hooks(self):
        RecoveryHooks.register("event1", lambda: None)
        RecoveryHooks.register("event2", lambda: None)

        RecoveryHooks.clear()

        assert RecoveryHooks._hooks == {}
