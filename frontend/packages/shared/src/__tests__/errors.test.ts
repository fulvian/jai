/**
 * Error Types Tests
 */

import { describe, it, expect } from 'vitest';
import {
    AppError,
    NetworkError,
    ValidationError,
    BusinessError,
    ExternalServiceError,
    ErrorCode,
    serializeError,
    getStatusCodeForError,
} from '../errors.js';

describe('Error Types', () => {
    describe('NetworkError', () => {
        it('should create NetworkError with correct properties', () => {
            const error = new NetworkError(ErrorCode.NETWORK_TIMEOUT, 503, '/api/test');

            expect(error.code).toBe(ErrorCode.NETWORK_TIMEOUT);
            expect(error.status).toBe(503);
            expect(error.url).toBe('/api/test');
            expect(error.isOperational).toBe(true);
            expect(error.message).toContain('503');
            expect(error.message).toContain('/api/test');
            expect(error.timestamp).toBeDefined();
        });

        it('should accept custom message', () => {
            const error = new NetworkError(
                ErrorCode.NETWORK_FAILURE,
                500,
                '/api/chat',
                'Custom error message'
            );

            expect(error.message).toBe('Custom error message');
        });
    });

    describe('ValidationError', () => {
        it('should create ValidationError with field info', () => {
            const error = new ValidationError(ErrorCode.VALIDATION_FAILED, 'email');

            expect(error.code).toBe(ErrorCode.VALIDATION_FAILED);
            expect(error.field).toBe('email');
            expect(error.message).toContain('email');
        });

        it('should include details when provided', () => {
            const details = { expected: 'string', received: 'number' };
            const error = new ValidationError(
                ErrorCode.INVALID_FILE_TYPE,
                'fileType',
                details
            );

            expect(error.details).toEqual(details);
        });
    });

    describe('BusinessError', () => {
        it('should create BusinessError with context', () => {
            const context = { sessionId: '123', userId: 'user1' };
            const error = new BusinessError(
                ErrorCode.SESSION_NOT_FOUND,
                'Session not found',
                context
            );

            expect(error.code).toBe(ErrorCode.SESSION_NOT_FOUND);
            expect(error.message).toBe('Session not found');
            expect(error.context).toEqual(context);
        });
    });

    describe('ExternalServiceError', () => {
        it('should create ExternalServiceError with service name', () => {
            const originalError = new Error('Connection refused');
            const error = new ExternalServiceError(
                ErrorCode.ME4BRAIN_ERROR,
                'Me4BrAIn',
                'Query failed',
                originalError
            );

            expect(error.code).toBe(ErrorCode.ME4BRAIN_ERROR);
            expect(error.service).toBe('Me4BrAIn');
            expect(error.message).toContain('Me4BrAIn');
            expect(error.message).toContain('Query failed');
            expect(error.originalError).toBe(originalError);
        });
    });

    describe('serializeError', () => {
        it('should serialize AppError to plain object', () => {
            const error = new BusinessError(
                ErrorCode.SESSION_NOT_FOUND,
                'Session not found'
            );

            const serialized = serializeError(error);

            expect(serialized).toEqual({
                code: ErrorCode.SESSION_NOT_FOUND,
                message: 'Session not found',
                timestamp: error.timestamp,
            });
        });
    });

    describe('getStatusCodeForError', () => {
        it('should return 400 for validation errors (E1xx)', () => {
            expect(getStatusCodeForError(ErrorCode.VALIDATION_FAILED)).toBe(400);
            expect(getStatusCodeForError(ErrorCode.INVALID_FILE_TYPE)).toBe(400);
            expect(getStatusCodeForError(ErrorCode.FILE_TOO_LARGE)).toBe(400);
        });

        it('should return 404 for not found errors', () => {
            expect(getStatusCodeForError(ErrorCode.SESSION_NOT_FOUND)).toBe(404);
            expect(getStatusCodeForError(ErrorCode.TURN_NOT_FOUND)).toBe(404);
        });

        it('should return 409 for already exists errors', () => {
            expect(getStatusCodeForError(ErrorCode.SESSION_ALREADY_EXISTS)).toBe(409);
        });

        it('should return 401 for unauthorized', () => {
            expect(getStatusCodeForError(ErrorCode.UNAUTHORIZED)).toBe(401);
        });

        it('should return 502 for external service errors (E3xx)', () => {
            expect(getStatusCodeForError(ErrorCode.ME4BRAIN_ERROR)).toBe(502);
            expect(getStatusCodeForError(ErrorCode.REDIS_ERROR)).toBe(502);
        });

        it('should return 500 for unknown errors', () => {
            expect(getStatusCodeForError(ErrorCode.UNKNOWN_ERROR)).toBe(500);
        });
    });

    describe('Error inheritance', () => {
        it('should be instance of Error', () => {
            const error = new BusinessError(ErrorCode.SESSION_NOT_FOUND, 'Test');
            expect(error instanceof Error).toBe(true);
        });

        it('should be instance of AppError', () => {
            const error = new NetworkError(ErrorCode.NETWORK_TIMEOUT, 503, '/api');
            expect(error instanceof AppError).toBe(true);
        });

        it('should have proper stack trace', () => {
            const error = new ValidationError(ErrorCode.VALIDATION_FAILED, 'test');
            expect(error.stack).toBeDefined();
            expect(error.stack).toContain('ValidationError');
        });
    });
});
