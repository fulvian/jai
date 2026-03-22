/**
 * Global Error Handler Middleware - SOTA 2026 Pattern
 * 
 * Standardized error handling with structured logging, correlation IDs, and AppError hierarchy.
 * Based on Perplexity research: Pino logging + error classification + graceful degradation.
 */

import type { FastifyError, FastifyReply, FastifyRequest } from 'fastify';
import {
    AppError,
    ValidationError,
    BusinessError,
    ErrorCode,
    serializeError,
    getStatusCodeForError
} from '@persan/shared';
import { randomUUID } from 'crypto';

/**
 * Global error handler for Fastify
 * Catches all errors, logs them with Pino, and returns standardized responses
 */
export function errorHandler(
    error: FastifyError | AppError | Error,
    request: FastifyRequest,
    reply: FastifyReply
) {
    // Generate correlation ID for tracing
    const correlationId = request.headers['x-correlation-id'] as string || randomUUID();

    // Attach correlation ID to response
    reply.header('x-correlation-id', correlationId);

    // Determine if error is operational (expected) or programmer error
    const isOperational = error instanceof AppError ? error.isOperational : false;

    // Log error with context
    const logContext = {
        correlationId,
        method: request.method,
        url: request.url,
        ip: request.ip,
        userAgent: request.headers['user-agent'],
        error: {
            name: error.name,
            message: error.message,
            stack: error.stack,
            code: (error as AppError).code || 'UNKNOWN',
            isOperational,
        },
    };

    if (isOperational) {
        request.log.warn(logContext, 'Operational error occurred');
    } else {
        request.log.error(logContext, 'Unexpected error occurred');
    }

    // Handle AppError hierarchy
    if (error instanceof AppError) {
        const statusCode = getStatusCodeForError(error.code);
        const serialized = serializeError(error);

        return reply.status(statusCode).send({
            error: serialized,
            correlationId,
        });
    }

    // Handle Fastify validation errors
    if ((error as FastifyError).validation) {
        const validationError = new ValidationError(
            ErrorCode.VALIDATION_FAILED,
            'request',
            (error as FastifyError).validation,
            error.message
        );

        return reply.status(400).send({
            error: serializeError(validationError),
            correlationId,
        });
    }

    // Handle generic errors (fallback)
    const genericError = new BusinessError(ErrorCode.UNKNOWN_ERROR, error.message || 'Internal server error');

    return reply.status(500).send({
        error: serializeError(genericError),
        correlationId,
    });
}

/**
 * Middleware to add correlation ID to all requests
 */
export function correlationIdMiddleware(
    request: FastifyRequest,
    reply: FastifyReply,
    done: () => void
) {
    const correlationId = request.headers['x-correlation-id'] as string || randomUUID();
    request.headers['x-correlation-id'] = correlationId;
    reply.header('x-correlation-id', correlationId);
    done();
}
