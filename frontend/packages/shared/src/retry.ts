/**
 * Retry and Sleep Utilities
 *
 * SOTA 2026 patterns for resilient network operations:
 * - Exponential backoff with jitter
 * - Circuit breaker pattern
 * - Deadline-aware retry
 */

export interface RetryOptions {
    /** Maximum number of attempts (default: 3) */
    maxAttempts?: number;
    /** Initial delay in ms (default: 1000) */
    initialDelayMs?: number;
    /** Maximum delay in ms (default: 10000) */
    maxDelayMs?: number;
    /** Exponential base (default: 2) */
    exponentialBase?: number;
    /** Enable jitter to prevent thundering herd (default: true) */
    jitter?: boolean;
    /** List of error codes that should NOT be retried */
    nonRetryableCodes?: string[];
    /** Callback called on each retry attempt */
    onRetry?: (attempt: number, error: Error, delay: number) => void;
}

export interface SleepOptions {
    /** Abort signal for cancellation */
    signal?: AbortSignal;
}

/**
 * Sleep for specified milliseconds.
 *
 * @param ms - Milliseconds to sleep
 * @param options - Options including abort signal
 * @returns Promise that resolves after ms
 */
export function sleep(ms: number, options?: SleepOptions): Promise<void> {
    return new Promise((resolve, reject) => {
        const timeout = setTimeout(resolve, ms);

        if (options?.signal) {
            if (options.signal.aborted) {
                clearTimeout(timeout);
                reject(new DOMException('Sleep aborted', 'AbortError'));
                return;
            }

            const handler = () => {
                clearTimeout(timeout);
                reject(new DOMException('Sleep aborted', 'AbortError'));
            };

            options.signal.addEventListener('abort', handler, { once: true });
        }
    });
}

/**
 * Sleep for specified milliseconds (sync version for testing).
 *
 * @param ms - Milliseconds to sleep
 */
export function sleepSync(ms: number): void {
    const end = Date.now() + ms;
    while (Date.now() < end) {
        // Busy wait - use only in tests
    }
}

/**
 * Calculate delay with exponential backoff and optional jitter.
 *
 * @param attempt - Current attempt number (0-indexed)
 * @param options - Retry options
 * @returns Delay in milliseconds
 */
export function calculateBackoff(attempt: number, options: Required<RetryOptions>): number {
    const { initialDelayMs, exponentialBase, maxDelayMs, jitter } = options;

    // Exponential delay: initial * (base ^ attempt)
    let delay = initialDelayMs * Math.pow(exponentialBase, attempt);

    // Cap at max delay
    delay = Math.min(delay, maxDelayMs);

    // Add jitter if enabled (0.8 to 1.2 range)
    if (jitter) {
        const jitterFactor = 0.8 + Math.random() * 0.4;
        delay = delay * jitterFactor;
    }

    return Math.round(delay);
}

/**
 * Check if an error is retryable based on error codes.
 *
 * @param error - Error to check
 * @param nonRetryableCodes - List of non-retryable error codes
 * @returns True if the error should not be retried
 */
export function isNonRetryableError(
    error: Error,
    nonRetryableCodes?: string[],
): boolean {
    if (!nonRetryableCodes?.length) {
        return false;
    }

    // Check for error code in various properties
    const errorCode = (error as { code?: string }).code ||
        (error as { errorCode?: string }).errorCode;

    if (errorCode && nonRetryableCodes.includes(errorCode)) {
        return true;
    }

    // Check error message for specific patterns
    const message = error.message.toLowerCase();
    for (const code of nonRetryableCodes) {
        if (message.includes(code.toLowerCase())) {
            return true;
        }
    }

    return false;
}

/**
 * Retry a function with exponential backoff.
 *
 * @param fn - Async function to retry
 * @param options - Retry options
 * @returns Promise resolving to the function's result
 * @throws The last error if all attempts fail
 *
 * @example
 * ```typescript
 * const result = await retry(
 *   async () => fetch('/api/data'),
 *   {
 *     maxAttempts: 3,
 *     initialDelayMs: 1000,
 *     onRetry: (attempt, error, delay) => {
 *       console.log(`Retry ${attempt} after ${delay}ms: ${error.message}`);
 *     }
 *   }
 * );
 * ```
 */
export async function retry<T>(
    fn: () => Promise<T>,
    options: RetryOptions = {},
): Promise<T> {
    const {
        maxAttempts = 3,
        initialDelayMs = 1000,
        maxDelayMs = 10000,
        exponentialBase = 2,
        jitter = true,
        nonRetryableCodes,
        onRetry,
    } = options;

    const resolvedOptions: Required<RetryOptions> = {
        maxAttempts,
        initialDelayMs,
        maxDelayMs,
        exponentialBase,
        jitter,
        nonRetryableCodes: nonRetryableCodes ?? [],
        onRetry: onRetry ?? (() => {}),
    };

    let lastError: Error;

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
        try {
            return await fn();
        } catch (error) {
            lastError = error instanceof Error ? error : new Error(String(error));

            // Check if error is non-retryable
            if (isNonRetryableError(lastError, resolvedOptions.nonRetryableCodes)) {
                throw lastError;
            }

            // Don't wait after last attempt
            if (attempt === maxAttempts - 1) {
                break;
            }

            const delay = calculateBackoff(attempt, resolvedOptions);
            resolvedOptions.onRetry(attempt + 1, lastError, delay);

            await sleep(delay);
        }
    }

    throw lastError!;
}

/**
 * Retry a function with deadline awareness.
 * Cancels retry if overall deadline is exceeded.
 *
 * @param fn - Async function to retry
 * @param options - Retry options including deadlineMs
 * @returns Promise resolving to the function's result
 * @throws Error if deadline is exceeded
 */
export async function retryWithDeadline<T>(
    fn: () => Promise<T>,
    options: RetryOptions & { deadlineMs?: number },
): Promise<T> {
    const { deadlineMs, ...retryOptions } = options;

    if (!deadlineMs) {
        return retry(fn, retryOptions);
    }

    const deadline = Date.now() + deadlineMs;
    let lastError: Error;

    const {
        maxAttempts = 3,
        initialDelayMs = 1000,
        maxDelayMs = 10000,
        exponentialBase = 2,
        jitter = true,
        nonRetryableCodes,
        onRetry,
    } = retryOptions;

    const resolvedOptions: Required<RetryOptions> = {
        maxAttempts,
        initialDelayMs,
        maxDelayMs,
        exponentialBase,
        jitter,
        nonRetryableCodes: nonRetryableCodes ?? [],
        onRetry: onRetry ?? (() => {}),
    };

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
        // Check deadline before each attempt
        if (Date.now() >= deadline) {
            throw new Error(`Deadline exceeded after ${attempt} attempts`);
        }

        try {
            return await fn();
        } catch (error) {
            lastError = error instanceof Error ? error : new Error(String(error));

            if (isNonRetryableError(lastError, resolvedOptions.nonRetryableCodes)) {
                throw lastError;
            }

            if (attempt === maxAttempts - 1) {
                break;
            }

            const delay = calculateBackoff(attempt, resolvedOptions);
            const remainingTime = deadline - Date.now();

            // Don't wait if we've already exceeded deadline
            if (delay > remainingTime) {
                throw new Error(`Deadline exceeded during backoff`);
            }

            resolvedOptions.onRetry(attempt + 1, lastError, delay);
            await sleep(delay);
        }
    }

    throw lastError!;
}

/**
 * Circuit breaker states
 */
export enum CircuitState {
    CLOSED = 'closed',    // Normal operation, requests pass through
    OPEN = 'open',        // Failing, requests are rejected immediately
    HALF_OPEN = 'half_open', // Testing if the service recovered
}

/**
 * Circuit breaker for preventing cascading failures.
 * Based on SOTA 2026 patterns.
 */
export class CircuitBreaker {
    private state: CircuitState = CircuitState.CLOSED;
    private failureCount = 0;
    private lastFailureTime = 0;
    private successCount = 0;

    constructor(
        private readonly threshold: number = 5,
        private readonly resetTimeoutMs: number = 30000,
        private readonly halfOpenSuccessThreshold: number = 3,
    ) {}

    /**
     * Execute a function with circuit breaker protection.
     */
    async execute<T>(fn: () => Promise<T>): Promise<T> {
        if (this.state === CircuitState.OPEN) {
            // Check if we should transition to half-open
            if (Date.now() - this.lastFailureTime >= this.resetTimeoutMs) {
                this.state = CircuitState.HALF_OPEN;
                this.successCount = 0;
            } else {
                throw new Error('Circuit breaker is OPEN - request rejected');
            }
        }

        try {
            const result = await fn();

            if (this.state === CircuitState.HALF_OPEN) {
                this.successCount++;
                if (this.successCount >= this.halfOpenSuccessThreshold) {
                    this.state = CircuitState.CLOSED;
                    this.failureCount = 0;
                }
            }

            return result;
        } catch (error) {
            this.failureCount++;
            this.lastFailureTime = Date.now();

            if (this.failureCount >= this.threshold) {
                this.state = CircuitState.OPEN;
            }

            throw error;
        }
    }

    /**
     * Get current circuit breaker state.
     */
    getState(): CircuitState {
        return this.state;
    }

    /**
     * Reset the circuit breaker to closed state.
     */
    reset(): void {
        this.state = CircuitState.CLOSED;
        this.failureCount = 0;
        this.successCount = 0;
    }
}
