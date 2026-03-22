/**
 * Configuration Schemas - SOTA 2026 Pattern
 * 
 * Zod schemas for runtime validation of environment variables and config objects.
 * Based on Perplexity research: type-safe validation with defaults and coercion.
 */

import { z } from 'zod';

/**
 * Backend/Gateway environment schema
 * Validates process.env at startup with fail-fast behavior
 */
export const EnvSchema = z.object({
    // Environment
    NODE_ENV: z.enum(['development', 'staging', 'production']).default('development'),
    PORT: z.coerce.number().int().positive().default(3030),

    // External Services
    ME4BRAIN_URL: z.string().url().default('http://localhost:8000'),
    REDIS_URL: z.string().url().default('redis://localhost:6379'),
    REDIS_PASSWORD: z.string().optional(),

    // Session Cache Configuration
    SESSION_CACHE_TTL: z.coerce.number().int().positive().default(1800), // 30min
    SESSION_L1_SIZE: z.coerce.number().int().positive().default(1000),
    CACHE_LOCK_TTL: z.coerce.number().int().positive().default(10),

    // Logging
    LOG_LEVEL: z.enum(['debug', 'info', 'warn', 'error']).default('info'),

    // API Timeouts
    API_TIMEOUT: z.coerce.number().int().positive().default(300000), // 5min
});

export type Env = z.infer<typeof EnvSchema>;

/**
 * Frontend configuration schema
 * Validates client-side config (from env vars or runtime)
 */
export const FrontendConfigSchema = z.object({
    gatewayUrl: z.string().url(),
    websocketUrl: z.string().refine(
        (url) => {
            try {
                const parsed = new URL(url);
                return ['ws:', 'wss:', 'http:', 'https:'].includes(parsed.protocol);
            } catch {
                return false;
            }
        },
        { message: 'websocketUrl must be a valid URL with ws://, wss://, http://, or https:// scheme' }
    ),
    timeout: z.number().int().positive().default(300000),
});

export type FrontendConfig = z.infer<typeof FrontendConfigSchema>;

/**
 * Validate environment variables with Zod
 * Throws on validation failure (fail-fast at startup)
 * 
 * @param env - Raw environment object (typically process.env)
 * @returns Validated and typed environment
 * @throws Error if validation fails
 */
export function validateEnv(env: unknown): Env {
    const result = EnvSchema.safeParse(env);

    if (!result.success) {
        const formatted = result.error.format();
        console.error('❌ Environment validation failed:', formatted);
        throw new Error(`Invalid environment configuration: ${result.error.message}`);
    }

    return result.data;
}

/**
 * Validate frontend configuration
 * 
 * @param config - Raw config object
 * @returns Validated and typed frontend config
 * @throws Error if validation fails
 */
export function validateFrontendConfig(config: unknown): FrontendConfig {
    const result = FrontendConfigSchema.safeParse(config);

    if (!result.success) {
        console.error('❌ Frontend config validation failed:', result.error.format());
        throw new Error(`Invalid frontend configuration: ${result.error.message}`);
    }

    return result.data;
}
