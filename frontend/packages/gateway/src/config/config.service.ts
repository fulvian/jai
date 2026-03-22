/**
 * Configuration Service - SOTA 2026 Pattern
 * 
 * Singleton service for centralized configuration management with runtime validation.
 * Based on Perplexity research: Zod validation + structured logging + hot-reload support.
 */

import { validateEnv, type Env } from '@persan/shared';
import pino from 'pino';

const logger = pino({ level: 'info' });

/**
 * Singleton ConfigService for centralized configuration management.
 * Validates environment variables at startup with fail-fast behavior.
 */
export class ConfigService {
    private static instance: ConfigService;
    private config: Env;

    private constructor() {
        this.config = this.loadConfig();
    }

    /**
     * Get singleton instance
     */
    static getInstance(): ConfigService {
        if (!ConfigService.instance) {
            ConfigService.instance = new ConfigService();
        }
        return ConfigService.instance;
    }

    /**
     * Load and validate configuration from environment
     */
    private loadConfig(): Env {
        try {
            const validated = validateEnv(process.env);
            logger.info(
                { config: this.sanitizeForLog(validated) },
                '✅ Configuration loaded and validated'
            );
            return validated;
        } catch (error) {
            logger.error({ error }, '❌ Configuration validation failed');
            throw error;
        }
    }

    /**
     * Sanitize config for logging (remove sensitive data)
     */
    private sanitizeForLog(config: Env): Partial<Env> {
        const { REDIS_URL, REDIS_PASSWORD, ...safe } = config;

        // Mask credentials in URLs
        const sanitizedRedisUrl = REDIS_URL.replace(/:\/\/.*@/, '://***@');

        return {
            ...safe,
            REDIS_URL: sanitizedRedisUrl,
            REDIS_PASSWORD: REDIS_PASSWORD ? '***' : undefined,
        };
    }

    /**
     * Get a specific config value by key
     */
    get<T extends keyof Env>(key: T): Env[T] {
        return this.config[key];
    }

    /**
     * Get all config values (readonly)
     */
    getAll(): Readonly<Env> {
        return Object.freeze({ ...this.config });
    }

    /**
     * Hot-reload configuration (future enhancement)
     * Useful for runtime config updates without restart
     */
    async reload(): Promise<void> {
        logger.info('🔄 Reloading configuration...');
        this.config = this.loadConfig();
        logger.info('✅ Configuration reloaded successfully');
    }
}

/**
 * Export singleton instance for use across the application
 */
export const config = ConfigService.getInstance();
