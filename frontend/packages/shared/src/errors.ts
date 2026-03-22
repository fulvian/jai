/**
 * Error Types - SOTA 2026 Pattern
 * 
 * Hierarchical error system with discriminated unions for type-safe error handling.
 * Based on Perplexity research: functional Result types + exhaustive switch patterns.
 */

import { z } from 'zod';

// Error codes enum - organized by category
export enum ErrorCode {
    // Network errors (E001-E099)
    NETWORK_TIMEOUT = 'E001',
    NETWORK_FAILURE = 'E002',
    CONNECTION_REFUSED = 'E003',

    // Validation errors (E100-E199)
    VALIDATION_FAILED = 'E100',
    INVALID_FILE_TYPE = 'E101',
    FILE_TOO_LARGE = 'E102',
    INVALID_SESSION_ID = 'E103',
    INVALID_TURN_INDEX = 'E104',

    // Business logic errors (E200-E299)
    SESSION_NOT_FOUND = 'E200',
    TURN_NOT_FOUND = 'E201',
    SESSION_ALREADY_EXISTS = 'E202',
    UNAUTHORIZED = 'E203',

    // External service errors (E300-E399)
    ME4BRAIN_ERROR = 'E300',
    REDIS_ERROR = 'E301',
    REDIS_UNAVAILABLE = 'E302',

    // Unknown/Generic
    UNKNOWN_ERROR = 'E999',
}

/**
 * Base error class for all application errors.
 * Extends Error with operational flag and timestamp.
 */
export abstract class AppError extends Error {
    public readonly code: ErrorCode;
    public readonly isOperational: boolean = true;
    public readonly timestamp: string;

    constructor(code: ErrorCode, message: string) {
        super(message);
        this.code = code;
        this.timestamp = new Date().toISOString();
        this.name = this.constructor.name;

        // Maintains proper stack trace for where error was thrown
        Error.captureStackTrace(this, this.constructor);
    }
}

/**
 * Network-related errors (timeouts, connection failures, HTTP errors)
 */
export class NetworkError extends AppError {
    constructor(
        code: ErrorCode,
        public status: number,
        public url: string,
        message?: string
    ) {
        super(code, message || `Network failure: ${status} at ${url}`);
    }
}

/**
 * Validation errors (invalid input, schema validation failures)
 */
export class ValidationError extends AppError {
    constructor(
        code: ErrorCode,
        public field: string,
        public details?: unknown,
        message?: string
    ) {
        super(code, message || `Validation failed: ${field}`);
    }
}

/**
 * Business logic errors (not found, already exists, unauthorized)
 */
export class BusinessError extends AppError {
    constructor(
        code: ErrorCode,
        message: string,
        public context?: unknown
    ) {
        super(code, message);
    }
}

/**
 * External service errors (Me4BrAIn, Redis, etc.)
 */
export class ExternalServiceError extends AppError {
    constructor(
        code: ErrorCode,
        public service: string,
        message: string,
        public originalError?: unknown
    ) {
        super(code, `${service} error: ${message}`);
    }
}

/**
 * Result type for functional error handling.
 * Enables exhaustive pattern matching and avoids throwing exceptions.
 * 
 * @example
 * ```typescript
 * function getSession(id: string): Result<Session> {
 *   if (!exists(id)) {
 *     return { success: false, error: new BusinessError(ErrorCode.SESSION_NOT_FOUND, 'Session not found') };
 *   }
 *   return { success: true, data: session };
 * }
 * 
 * const result = getSession('123');
 * if (result.success) {
 *   console.log(result.data);
 * } else {
 *   console.error(result.error.code);
 * }
 * ```
 */
export type Result<T, E extends AppError = AppError> =
    | { success: true; data: T }
    | { success: false; error: E };

/**
 * Zod schema for error serialization (API responses, logging)
 */
export const ErrorSchema = z.object({
    code: z.nativeEnum(ErrorCode),
    message: z.string(),
    timestamp: z.string(),
    details: z.unknown().optional(),
});

export type SerializedError = z.infer<typeof ErrorSchema>;

/**
 * Helper to serialize AppError for API responses
 */
export function serializeError(error: AppError): SerializedError {
    return {
        code: error.code,
        message: error.message,
        timestamp: error.timestamp,
    };
}

/**
 * Helper to determine HTTP status code from ErrorCode
 */
export function getStatusCodeForError(code: ErrorCode): number {
    const codeStr = code.toString();

    // E1xx = 400 (Validation)
    if (codeStr.startsWith('E1')) return 400;

    // E2xx = 404 or 409 (Business logic)
    if (codeStr.startsWith('E2')) {
        if (code === ErrorCode.SESSION_ALREADY_EXISTS) return 409;
        if (code === ErrorCode.UNAUTHORIZED) return 401;
        return 404;
    }

    // E3xx = 502 (External service)
    if (codeStr.startsWith('E3')) return 502;

    // Default = 500
    return 500;
}
