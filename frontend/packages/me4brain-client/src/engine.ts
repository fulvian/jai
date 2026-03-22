/**
 * Engine Namespace
 * 
 * Provides access to Tool Calling Engine endpoints.
 */

import type { Me4BrAInClient } from './client.js';
import { Agent } from 'undici';
import type {
    EngineQueryResponse,
    ToolInfo,
    CatalogStats,
    QueryOptions,
    StreamOptions,
    StreamChunk,
    ToolFilter,
} from './types.js';

export class EngineNamespace {
    /**
     * Custom undici Agent that disables default headersTimeout and bodyTimeout.
     * Without this, Node.js fetch() kills connections after 5 min even if AbortSignal allows more.
     *
     * keepAliveTimeout set very high (30 min) — we rely on activity-based timeout instead.
     */
    private static longRunningAgent = new Agent({
        headersTimeout: 0,
        bodyTimeout: 0,
        keepAliveTimeout: 1_800_000,  // 30 min — aligned with max possible query duration
    });

    /** Default silence timeout: abort if no SSE chunk received for this many seconds. */
    private static readonly CHUNK_SILENCE_TIMEOUT_MS = 900_000; // 15 minutes — aligned with backend STEP_TIMEOUT_SECONDS

    constructor(private client: Me4BrAInClient) { }

    /**
     * Execute a natural language query through the Tool Calling Engine.
     */
    async query(query: string, options: QueryOptions = {}): Promise<EngineQueryResponse> {
        const response = await this.client.request<{
            query: string;
            answer: string;
            tools_called: Array<{
                tool_name: string;
                arguments: Record<string, unknown>;
                success: boolean;
                latency_ms: number;
                error?: string;
            }>;
            total_latency_ms: number;
            raw_results?: unknown[];
        }>('POST', '/engine/query', {
            body: {
                query,
                stream: false,
                include_raw_results: options.includeRawResults ?? false,
                timeout_seconds: options.timeoutSeconds ?? 1800,
                session_id: options.sessionId ?? null,
            },
            // AbortSignal.timeout handles both connect and response wait reliably
            signal: AbortSignal.timeout((options.timeoutSeconds ?? 1800) * 1000 + 10000),
        });

        return {
            query: response.query,
            answer: response.answer,
            toolsCalled: response.tools_called.map((t) => ({
                toolName: t.tool_name,
                arguments: t.arguments,
                success: t.success,
                latencyMs: t.latency_ms,
                error: t.error,
            })),
            totalLatencyMs: response.total_latency_ms,
            rawResults: response.raw_results,
        };
    }

    /**
     * Execute a query and stream real-time progress via AsyncIterator.
     *
     * Uses an **activity-based timeout**: the timer resets every time a chunk
     * is received from the backend. The connection is aborted only if no data
     * arrives for CHUNK_SILENCE_TIMEOUT_MS (default 6 minutes).
     *
     * This allows queries of unlimited total duration as long as the backend
     * keeps sending progress events (step_thinking, step_complete, content, etc.).
     */
    async *queryStream(query: string, options: StreamOptions = {}): AsyncIterableIterator<StreamChunk> {
        // 1. Emit start
        yield { type: 'start', session_id: options.sessionId };

        // Activity-based timeout: AbortController + resettable timer
        const controller = new AbortController();
        const silenceMs = options.chunkSilenceTimeoutMs ?? EngineNamespace.CHUNK_SILENCE_TIMEOUT_MS;
        let silenceTimer: ReturnType<typeof setTimeout> | null = null;

        const resetSilenceTimer = (): void => {
            if (silenceTimer) clearTimeout(silenceTimer);
            silenceTimer = setTimeout(() => {
                controller.abort(new Error(
                    `No data received from Me4BrAIn for ${silenceMs / 1000}s — connection presumed dead`
                ));
            }, silenceMs);
        };

        const clearSilenceTimer = (): void => {
            if (silenceTimer) {
                clearTimeout(silenceTimer);
                silenceTimer = null;
            }
        };

        try {
            // 2. Call Me4BrAIn with stream: true (real SSE)
            const url = `${this.client.config.baseUrl}/engine/query`;

            // Start the silence timer before the fetch (covers initial connection)
            resetSilenceTimer();

            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Tenant-ID': this.client.config.tenantId,
                    'Accept': 'text/event-stream',
                },
                body: JSON.stringify({
                    query,
                    stream: true,
                    include_raw_results: options.includeRawResults ?? false,
                    timeout_seconds: options.timeoutSeconds ?? 1800,
                    session_id: options.sessionId ?? null,
                }),
                signal: controller.signal,
                keepalive: true,
                // @ts-expect-error - dispatcher is a valid fetch option for Node.js undici
                dispatcher: EngineNamespace.longRunningAgent,
            });

            if (!response.ok) {
                throw new Error(`Me4BrAIn HTTP ${response.status}: ${response.statusText}`);
            }

            const reader = response.body?.getReader();
            if (!reader) {
                throw new Error('No response body from Me4BrAIn');
            }

            // Reset timer after successful connection
            resetSilenceTimer();

            // 3. Parse SSE stream with activity-based timeout
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                // ✅ Activity detected — reset the silence timer
                resetSilenceTimer();

                buffer += decoder.decode(value, { stream: true });

                // Parse SSE lines
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';

                for (const line of lines) {
                    if (!line.startsWith('data: ')) continue;

                    const data = line.slice(6).trim();
                    if (data === '[DONE]') continue;
                    if (data === '') continue;

                    try {
                        const event: StreamChunk = JSON.parse(data);
                        yield event;
                    } catch {
                        // Skip malformed SSE lines
                    }
                }
            }

            // ✅ BUG-12 FIX: Emit synthetic 'done' event after stream ends
            // This ensures the Gateway always receives a completion signal
            yield {
                type: 'done',
                tools_called: [],
                latency_ms: 0,
            };

        } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            yield {
                type: 'error',
                error: message,
            };
        } finally {
            clearSilenceTimer();
        }
    }

    /**
     * Call a tool directly by name.
     */
    async call(toolName: string, args: Record<string, unknown>): Promise<unknown> {
        const response = await this.client.request<{
            success: boolean;
            result: unknown;
            error?: string;
        }>('POST', '/engine/call', {
            body: {
                tool_name: toolName,
                arguments: args,
            },
        });

        if (!response.success) {
            throw new Error(response.error ?? 'Tool execution failed');
        }

        return response.result;
    }

    /**
     * List available tools in the catalog.
     */
    async listTools(filter?: ToolFilter): Promise<ToolInfo[]> {
        const params: Record<string, string> = {};
        if (filter?.domain) params.domain = filter.domain;
        if (filter?.category) params.category = filter.category;
        if (filter?.search) params.search = filter.search;

        const response = await this.client.request<{
            tools: Array<{
                name: string;
                description: string;
                domain?: string;
                category?: string;
                parameters?: Record<string, unknown>;
            }>;
        }>('GET', '/engine/tools', { params });

        return response.tools.map((t) => ({
            name: t.name,
            description: t.description,
            domain: t.domain,
            category: t.category,
            parameters: t.parameters,
        }));
    }

    /**
     * Get details of a specific tool.
     */
    async getTool(toolName: string): Promise<ToolInfo> {
        return this.client.request<ToolInfo>('GET', `/engine/tools/${toolName}`);
    }

    /**
     * Get catalog statistics.
     */
    async stats(): Promise<CatalogStats> {
        const response = await this.client.request<{
            total_tools: number;
            domains: Array<{
                domain: string;
                tool_count: number;
                tools: string[];
            }>;
        }>('GET', '/engine/stats');

        return {
            totalTools: response.total_tools,
            domains: response.domains.map((d) => ({
                domain: d.domain,
                toolCount: d.tool_count,
                tools: d.tools,
            })),
        };
    }
}
