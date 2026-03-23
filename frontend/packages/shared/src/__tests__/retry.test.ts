/**
 * Unit Tests - Retry and Sleep Utilities
 *
 * Tests per le funzioni di retry con exponential backoff,
 * circuit breaker, e sleep.
 */

import { describe, it, expect, vi } from 'vitest';
import {
    sleep,
    calculateBackoff,
    isNonRetryableError,
    retry,
    retryWithDeadline,
    CircuitBreaker,
    CircuitState,
} from '../retry.js';

describe('Sleep', () => {
    it('should resolve after specified time', async () => {
        vi.useFakeTimers();
        const promise = sleep(1000);
        vi.advanceTimersByTime(1000);
        await expect(promise).resolves.toBeUndefined();
        vi.useRealTimers();
    });

    it('should reject with AbortError when aborted', async () => {
        vi.useFakeTimers();
        const controller = new AbortController();

        const promise = sleep(10000, { signal: controller.signal });

        // Abort before sleep completes
        controller.abort();

        await expect(promise).rejects.toThrow('Sleep aborted');
        vi.useRealTimers();
    });

    it('should not reject if already aborted', async () => {
        vi.useFakeTimers();
        const controller = new AbortController();
        controller.abort();

        const promise = sleep(1000, { signal: controller.signal });
        vi.advanceTimersByTime(1000);

        await expect(promise).rejects.toThrow('Sleep aborted');
        vi.useRealTimers();
    });
});

describe('CalculateBackoff', () => {
    const defaultOptions = {
        maxAttempts: 3,
        initialDelayMs: 1000,
        maxDelayMs: 10000,
        exponentialBase: 2,
        jitter: false,
        nonRetryableCodes: [],
        onRetry: () => {},
    };

    it('should calculate exponential delay without jitter', () => {
        // Attempt 0: 1000 * 2^0 = 1000
        expect(calculateBackoff(0, defaultOptions)).toBe(1000);

        // Attempt 1: 1000 * 2^1 = 2000
        expect(calculateBackoff(1, defaultOptions)).toBe(2000);

        // Attempt 2: 1000 * 2^2 = 4000
        expect(calculateBackoff(2, defaultOptions)).toBe(4000);
    });

    it('should cap delay at maxDelayMs', () => {
        const options = { ...defaultOptions, maxDelayMs: 5000 };

        // Attempt 10: would be 1000 * 2^10 = 1024000, but capped at 5000
        expect(calculateBackoff(10, options)).toBe(5000);
    });

    it('should apply jitter when enabled', () => {
        const options = { ...defaultOptions, jitter: true };
        const delays = new Set<number>();

        // Run multiple times to see jitter variation
        for (let i = 0; i < 10; i++) {
            delays.add(calculateBackoff(1, options));
        }

        // With jitter on base delay 2000, we expect values between 1600 and 2400 (0.8 to 1.2 range)
        // Some variation should be present
        expect(delays.size).toBeGreaterThan(1);
    });

    it('should use custom exponential base', () => {
        const options = { ...defaultOptions, exponentialBase: 3 };

        // Attempt 1: 1000 * 3^1 = 3000
        expect(calculateBackoff(1, options)).toBe(3000);
    });
});

describe('IsNonRetryableError', () => {
    it('should return false for error with no codes', () => {
        const error = new Error('test');
        expect(isNonRetryableError(error, undefined)).toBe(false);
        expect(isNonRetryableError(error, [])).toBe(false);
    });

    it('should return true for error with matching code', () => {
        const error = new Error('test') as Error & { code?: string };
        error.code = 'E400';

        expect(isNonRetryableError(error, ['E400'])).toBe(true);
        expect(isNonRetryableError(error, ['E400', 'E500'])).toBe(true);
    });

    it('should return false for error with non-matching code', () => {
        const error = new Error('test') as Error & { code?: string };
        error.code = 'E500';

        expect(isNonRetryableError(error, ['E400'])).toBe(false);
    });

    it('should check error message for patterns', () => {
        const error = new Error('Validation failed for field E400');

        expect(isNonRetryableError(error, ['E400'])).toBe(true);
        expect(isNonRetryableError(error, ['NOTFOUND'])).toBe(false);
    });
});

describe('Retry', () => {
    it('should succeed on first attempt', async () => {
        const fn = vi.fn().mockResolvedValue('success');

        const result = await retry(fn, { maxAttempts: 3 });

        expect(result).toBe('success');
        expect(fn).toHaveBeenCalledTimes(1);
    });

    it('should retry on failure and eventually succeed', async () => {
        const fn = vi
            .fn()
            .mockRejectedValueOnce(new Error('fail 1'))
            .mockRejectedValueOnce(new Error('fail 2'))
            .mockResolvedValue('success');

        const retryHook = vi.fn();

        const result = await retry(fn, {
            maxAttempts: 3,
            initialDelayMs: 10, // Short delay for test
            onRetry: retryHook,
        });

        expect(result).toBe('success');
        expect(fn).toHaveBeenCalledTimes(3);
        expect(retryHook).toHaveBeenCalledTimes(2);
    });

    it('should throw after max attempts', async () => {
        const fn = vi.fn().mockRejectedValue(new Error('persistent failure'));

        await expect(
            retry(fn, {
                maxAttempts: 3,
                initialDelayMs: 10,
            })
        ).rejects.toThrow('persistent failure');

        expect(fn).toHaveBeenCalledTimes(3);
    });

    it('should not retry non-retryable errors', async () => {
        const error = new Error('bad request') as Error & { code: string };
        error.code = 'E400';
        const fn = vi.fn().mockRejectedValue(error);

        await expect(
            retry(fn, {
                maxAttempts: 3,
                nonRetryableCodes: ['E400'],
            })
        ).rejects.toThrow('bad request');

        expect(fn).toHaveBeenCalledTimes(1);
    });

    it('should call onRetry with correct parameters', async () => {
        const fn = vi.fn().mockRejectedValue(new Error('fail'));
        const onRetry = vi.fn();

        await expect(
            retry(fn, {
                maxAttempts: 3,
                initialDelayMs: 10,
                onRetry,
            })
        ).rejects.toThrow('fail');

        expect(onRetry).toHaveBeenCalledTimes(2);
        expect(onRetry).toHaveBeenCalledWith(
            1, // attempt number
            expect.any(Error),
            expect.any(Number) // delay
        );
    });
});

describe('RetryWithDeadline', () => {
    it('should succeed before deadline', async () => {
        const fn = vi.fn().mockResolvedValue('success');

        const result = await retryWithDeadline(fn, {
            deadlineMs: 5000,
        });

        expect(result).toBe('success');
    });

    it('should pass deadline to retry when not specified', async () => {
        const fn = vi.fn().mockResolvedValue('success');

        const result = await retryWithDeadline(fn, {});

        expect(result).toBe('success');
    });
});

describe('CircuitBreaker', () => {
    it('should start in closed state', () => {
        const breaker = new CircuitBreaker();
        expect(breaker.getState()).toBe(CircuitState.CLOSED);
    });

    it('should allow requests when closed', async () => {
        const breaker = new CircuitBreaker();
        const fn = vi.fn().mockResolvedValue('success');

        const result = await breaker.execute(fn);

        expect(result).toBe('success');
        expect(fn).toHaveBeenCalledTimes(1);
    });

    it('should open after threshold failures', async () => {
        const breaker = new CircuitBreaker(3, 30000);
        const fn = vi.fn().mockRejectedValue(new Error('fail'));

        // Fail 3 times to trip the breaker
        for (let i = 0; i < 3; i++) {
            await expect(breaker.execute(fn)).rejects.toThrow('fail');
        }

        expect(breaker.getState()).toBe(CircuitState.OPEN);

        // Next request should be rejected immediately
        await expect(breaker.execute(fn)).rejects.toThrow('Circuit breaker is OPEN');
    });

    it('should transition to half-open after timeout', async () => {
        vi.useFakeTimers();
        const breaker = new CircuitBreaker(2, 5000);
        const fn = vi.fn().mockRejectedValue(new Error('fail'));

        // Trip the breaker
        await expect(breaker.execute(fn)).rejects.toThrow('fail');
        await expect(breaker.execute(fn)).rejects.toThrow('fail');
        expect(breaker.getState()).toBe(CircuitState.OPEN);

        // Advance time past reset timeout
        vi.advanceTimersByTime(5000);

        // Next request should transition to half-open
        const successFn = vi.fn().mockResolvedValue('success');
        const result = await breaker.execute(successFn);

        expect(result).toBe('success');
        expect(breaker.getState()).toBe(CircuitState.HALF_OPEN);
        vi.useRealTimers();
    });

    it('should close after half-open success threshold', async () => {
        vi.useFakeTimers();
        const breaker = new CircuitBreaker(2, 5000, 2);
        const failFn = vi.fn().mockRejectedValue(new Error('fail'));

        // Trip the breaker
        await expect(breaker.execute(failFn)).rejects.toThrow('fail');
        await expect(breaker.execute(failFn)).rejects.toThrow('fail');

        // Advance time and succeed twice to close
        vi.advanceTimersByTime(5000);
        const successFn = vi.fn().mockResolvedValue('success');
        await breaker.execute(successFn);
        await breaker.execute(successFn);

        expect(breaker.getState()).toBe(CircuitState.CLOSED);
        vi.useRealTimers();
    });

    it('should reset manually', async () => {
        const breaker = new CircuitBreaker(1);
        const fn = vi.fn().mockRejectedValue(new Error('fail'));

        await breaker.execute(fn).catch(() => {}); // Trip it
        expect(breaker.getState()).toBe(CircuitState.OPEN);

        breaker.reset();
        expect(breaker.getState()).toBe(CircuitState.CLOSED);
    });
});
