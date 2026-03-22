/**
 * Me4BrAIn Client
 *
 * Main client class for interacting with Me4BrAIn API.
 */

import { ofetch, FetchError } from 'ofetch';
import { Agent } from 'undici';
import { EngineNamespace } from './engine.js';
import { MemoryNamespace } from './memory.js';
import { SkillsNamespace } from './skills.js';
import { Me4BrAInError } from './types.js';
import type { Me4BrAInConfig } from './types.js';

/**
 * Custom undici Agent that disables default headersTimeout (300s) and bodyTimeout (300s).
 * Without this, Node.js fetch() kills connections after 5 min even if AbortSignal allows more.
 */
const longRunningAgent = new Agent({
    headersTimeout: 0,    // No timeout waiting for response headers
    bodyTimeout: 0,       // No timeout waiting for response body
    keepAliveTimeout: 1_800_000,  // 30 min — aligned with engine.ts activity-based timeout
});

export class Me4BrAInClient {
    private baseUrl: string;
    private headers: Record<string, string>;

    public readonly engine: EngineNamespace;
    public readonly memory: MemoryNamespace;
    public readonly skills: SkillsNamespace;

    constructor(config: Me4BrAInConfig = {}) {
        let url = config.baseUrl ?? process.env.ME4BRAIN_URL ?? 'http://localhost:8000';

        // Ensure /v1 suffix
        if (!url.endsWith('/v1')) {
            url = url.endsWith('/') ? `${url}v1` : `${url}/v1`;
        }

        this.baseUrl = url;
        this.headers = {
            'Content-Type': 'application/json',
            'X-Tenant-ID': config.tenantId ?? 'default',
        };

        if (config.apiKey) {
            this.headers['X-API-Key'] = config.apiKey;
        }

        this.engine = new EngineNamespace(this);
        this.memory = new MemoryNamespace(this);
        this.skills = new SkillsNamespace(this);
    }

    async request<T>(
        method: string,
        path: string,
        options: {
            body?: unknown;
            params?: Record<string, string>;
            timeout?: number;
            signal?: AbortSignal;
        } = {}
    ): Promise<T> {
        const timeoutMs = options.timeout ?? 900000; // 15 minutes default
        try {
            // Use explicit AbortSignal.timeout to override Node.js default socket timeout (~30s)
            const signal = options.signal ?? AbortSignal.timeout(timeoutMs);
            const response = await ofetch<T>(`${this.baseUrl}${path}`, {
                method,
                headers: this.headers,
                body: options.body as Record<string, unknown> | undefined,
                query: options.params,
                // Do NOT pass timeout to ofetch — use signal instead for reliable long-request handling
                signal,
                retry: 0, // No retry for long-running engine queries
                keepalive: true, // Keep TCP connection alive for long requests
                // Override undici's default headersTimeout (300s) and bodyTimeout (300s)
                dispatcher: longRunningAgent,
            });
            return response;
        } catch (error) {
            if (error instanceof FetchError) {
                throw new Me4BrAInError(
                    error.message,
                    error.statusCode,
                    error.data
                );
            }
            throw error;
        }
    }

    get config(): { baseUrl: string; tenantId: string } {
        return {
            baseUrl: this.baseUrl,
            tenantId: this.headers['X-Tenant-ID'],
        };
    }
}
