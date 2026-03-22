/**
 * Config Validation Tests
 */

import { describe, it, expect } from 'vitest';
import {
    validateEnv,
    validateFrontendConfig,
    EnvSchema,
    FrontendConfigSchema,
} from '../config.js';

describe('Config Validation', () => {
    describe('validateEnv', () => {
        it('should validate correct environment', () => {
            const env = {
                NODE_ENV: 'development',
                PORT: '3030',
                ME4BRAIN_URL: 'http://localhost:8000',
                REDIS_URL: 'redis://localhost:6379',
                LOG_LEVEL: 'info',
            };

            const result = validateEnv(env);

            expect(result.NODE_ENV).toBe('development');
            expect(result.PORT).toBe(3030); // Coerced to number
            expect(result.ME4BRAIN_URL).toBe('http://localhost:8000');
            expect(result.REDIS_URL).toBe('redis://localhost:6379');
            expect(result.LOG_LEVEL).toBe('info');
        });

        it('should apply defaults for missing values', () => {
            const env = {};

            const result = validateEnv(env);

            expect(result.NODE_ENV).toBe('development');
            expect(result.PORT).toBe(3030);
            expect(result.ME4BRAIN_URL).toBe('http://localhost:8000');
            expect(result.REDIS_URL).toBe('redis://localhost:6379');
            expect(result.SESSION_CACHE_TTL).toBe(1800);
            expect(result.SESSION_L1_SIZE).toBe(1000);
            expect(result.CACHE_LOCK_TTL).toBe(10);
            expect(result.LOG_LEVEL).toBe('info');
            expect(result.API_TIMEOUT).toBe(300000);
        });

        it('should coerce string numbers to numbers', () => {
            const env = {
                PORT: '8080',
                SESSION_CACHE_TTL: '3600',
                SESSION_L1_SIZE: '500',
            };

            const result = validateEnv(env);

            expect(result.PORT).toBe(8080);
            expect(result.SESSION_CACHE_TTL).toBe(3600);
            expect(result.SESSION_L1_SIZE).toBe(500);
        });

        it('should throw on invalid URL', () => {
            const env = {
                ME4BRAIN_URL: 'not-a-url',
            };

            expect(() => validateEnv(env)).toThrow('Invalid environment configuration');
        });

        it('should throw on invalid NODE_ENV', () => {
            const env = {
                NODE_ENV: 'invalid',
            };

            expect(() => validateEnv(env)).toThrow();
        });

        it('should throw on invalid LOG_LEVEL', () => {
            const env = {
                LOG_LEVEL: 'trace',
            };

            expect(() => validateEnv(env)).toThrow();
        });

        it('should throw on negative PORT', () => {
            const env = {
                PORT: '-1',
            };

            expect(() => validateEnv(env)).toThrow();
        });

        it('should accept optional REDIS_PASSWORD', () => {
            const env = {
                REDIS_PASSWORD: 'secret123',
            };

            const result = validateEnv(env);

            expect(result.REDIS_PASSWORD).toBe('secret123');
        });
    });

    describe('validateFrontendConfig', () => {
        it('should validate correct frontend config', () => {
            const config = {
                gatewayUrl: 'http://localhost:3030',
                websocketUrl: 'ws://localhost:3030/ws',
                timeout: 300000,
            };

            const result = validateFrontendConfig(config);

            expect(result.gatewayUrl).toBe('http://localhost:3030');
            expect(result.websocketUrl).toBe('ws://localhost:3030/ws');
            expect(result.timeout).toBe(300000);
        });

        it('should apply default timeout', () => {
            const config = {
                gatewayUrl: 'http://localhost:3030',
                websocketUrl: 'ws://localhost:3030/ws',
            };

            const result = validateFrontendConfig(config);

            expect(result.timeout).toBe(300000);
        });

        it('should throw on invalid gatewayUrl', () => {
            const config = {
                gatewayUrl: 'not-a-url',
                websocketUrl: 'ws://localhost:3030/ws',
            };

            expect(() => validateFrontendConfig(config)).toThrow('Invalid frontend configuration');
        });

        it('should throw on invalid websocketUrl', () => {
            const config = {
                gatewayUrl: 'http://localhost:3030',
                websocketUrl: 'invalid',
            };

            expect(() => validateFrontendConfig(config)).toThrow();
        });

        it('should throw on negative timeout', () => {
            const config = {
                gatewayUrl: 'http://localhost:3030',
                websocketUrl: 'ws://localhost:3030/ws',
                timeout: -1,
            };

            expect(() => validateFrontendConfig(config)).toThrow();
        });
    });

    describe('Schema exports', () => {
        it('should export EnvSchema', () => {
            expect(EnvSchema).toBeDefined();
            expect(typeof EnvSchema.parse).toBe('function');
        });

        it('should export FrontendConfigSchema', () => {
            expect(FrontendConfigSchema).toBeDefined();
            expect(typeof FrontendConfigSchema.parse).toBe('function');
        });
    });
});
