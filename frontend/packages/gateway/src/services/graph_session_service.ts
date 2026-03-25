/**
 * Graph Session Service
 *
 * Client Gateway per il Session Knowledge Graph di Me4Brain.
 * Gestisce comunicazione con gli endpoint /sessions/graph/* e /prompts/library/*
 *
 * Retry Logic:
 *   Tutte le chiamate HTTP includono retry automatico con exponential backoff
 *   per gestire fallimenti transienti di rete o servizio.
 */

import { ofetch } from 'ofetch';
import { retry } from '@persan/shared';

// ── Types ────────────────────────────────────────────────────────────

export interface SessionCluster {
    id: string;
    name: string;
    description: string;
    sessionCount: number;
    topics: string[];
    sessionIds: string[];
}

export interface SessionSearchResult {
    sessionId: string;
    title: string;
    score: number;
    topics: string[];
    clusterName: string;
    turnCount: number;
    updatedAt: string;
}

export interface TopicInfo {
    id: string;
    name: string;
    sessionCount: number;
}

export interface PromptTemplate {
    id: string;
    label: string;
    content: string;
    category: string;
    topics: string[];
    usageCount: number;
    lastUsedAt?: string;
    variables: string[];
}

export interface ReindexReport {
    total: number;
    success: number;
    errors: number;
    clustersCreated: number;
    errorDetails: Array<{ sessionId: string; error: string }>;
}

export interface ConnectedNode {
    id: string;
    name: string;
    nodeType: string;
    connectionScore: number;
    relationType: string;
    sharedSessions: number;
    description: string;
}

// ── Service ──────────────────────────────────────────────────────────

class GraphSessionService {
    private baseUrl: string;
    private tenantId: string;

    constructor() {
        // Backend canonical port is 8000 (FastAPI), Gateway on 3030
        // ME4BRAIN_URL should be full URL like http://localhost:8000/v1
        const me4brainUrl = process.env.ME4BRAIN_URL ?? '';
        if (me4brainUrl) {
            // Ensure /v1 suffix
            this.baseUrl = me4brainUrl.endsWith('/v1') ? me4brainUrl : `${me4brainUrl}/v1`;
        } else {
            // Fallback to port 8000 (canonical), not 8089 (legacy)
            const backendPort = process.env.ME4BRAIN_PORT ?? '8000';
            this.baseUrl = `http://localhost:${backendPort}/v1`;
        }
        this.tenantId = process.env.TENANT_ID ?? 'default';
    }

    private get headers(): Record<string, string> {
        const headers: Record<string, string> = {
            'X-Tenant-ID': this.tenantId,
            'X-User-ID': 'gateway',
            'Content-Type': 'application/json',
        };

        if (process.env.ME4BRAIN_API_KEY) {
            headers['X-API-Key'] = process.env.ME4BRAIN_API_KEY;
        }

        return headers;
    }

    // ── Session Graph ────────────────────────────────────────────────

    /** Retry configuration for ingest operations */
    private static readonly INGEST_MAX_ATTEMPTS = 3;
    private static readonly INGEST_INITIAL_DELAY_MS = 1000;

    /**
     * Indicizza una sessione nel grafo Neo4j.
     * Chiamato automaticamente dopo salvataggio su Redis.
     *
     * Implementa retry automatico con exponential backoff per gestire
     * fallimenti transienti (5xx, network errors).
     */
    async ingestSession(
        sessionId: string,
        title: string,
        turns: Array<{ role: string; content: string; timestamp?: string }>,
        createdAt?: string,
        updatedAt?: string,
    ): Promise<{ sessionId: string; turnCount: number; status: string }> {
        return retry(
            async () => {
                const result = await ofetch(`${this.baseUrl}/sessions/graph/ingest`, {
                    method: 'POST',
                    headers: this.headers,
                    body: {
                        session_id: sessionId,
                        title,
                        turns,
                        created_at: createdAt,
                        updated_at: updatedAt,
                    },
                    timeout: 30_000, // 30s per ingestione con embedding
                });
                return {
                    sessionId: result.session_id,
                    turnCount: result.turn_count,
                    status: result.status,
                };
            },
            {
                maxAttempts: GraphSessionService.INGEST_MAX_ATTEMPTS,
                initialDelayMs: GraphSessionService.INGEST_INITIAL_DELAY_MS,
                exponentialBase: 2,
                jitter: true,
                // Only retry on server errors (5xx) or network errors
                nonRetryableCodes: ['E400', 'E401', 'E403', 'E404'],
                onRetry: (attempt: number, error: Error, delay: number) => {
                    console.warn(
                        `[GraphSession] Ingest retry ${attempt} for session ${sessionId} after ${delay}ms: ${error.message}`,
                    );
                },
            },
        );
    }

    /**
     * Recupera i cluster tematici per il tenant corrente.
     */
    async getClusters(): Promise<SessionCluster[]> {
        try {
            const data = await ofetch(`${this.baseUrl}/sessions/graph/clusters`, {
                headers: this.headers,
                timeout: 10_000,
            });
            return (data as Array<Record<string, unknown>>).map((c) => ({
                id: c.id as string,
                name: c.name as string,
                description: c.description as string,
                sessionCount: c.session_count as number,
                topics: c.topics as string[],
                sessionIds: c.session_ids as string[],
            }));
        } catch (error) {
            console.warn('[GraphSession] getClusters failed:', (error as Error).message);
            return [];
        }
    }

    /**
     * Recupera sessioni correlate.
     */
    async getRelatedSessions(
        sessionId: string,
        limit = 5,
    ): Promise<SessionSearchResult[]> {
        try {
            const data = await ofetch(
                `${this.baseUrl}/sessions/graph/related/${sessionId}?limit=${limit}`,
                {
                    headers: this.headers,
                    timeout: 10_000,
                },
            );
            return this.mapSearchResults(data as Array<Record<string, unknown>>);
        } catch (error) {
            console.warn('[GraphSession] getRelated failed:', (error as Error).message);
            return [];
        }
    }

    /**
     * Ricerca semantica sessioni (pipeline 5-stage).
     */
    async searchSessions(
        query: string,
        topK = 10,
        useReranking = true,
    ): Promise<SessionSearchResult[]> {
        try {
            const data = await ofetch(`${this.baseUrl}/sessions/graph/search`, {
                method: 'POST',
                headers: this.headers,
                body: {
                    query,
                    top_k: topK,
                    use_reranking: useReranking,
                },
                timeout: 15_000,
            });
            return this.mapSearchResults(data as Array<Record<string, unknown>>);
        } catch (error) {
            console.warn('[GraphSession] search failed:', (error as Error).message);
            return [];
        }
    }

    /**
     * Recupera i topic con conteggio sessioni.
     */
    async getTopics(limit = 50): Promise<TopicInfo[]> {
        try {
            const data = await ofetch(
                `${this.baseUrl}/sessions/graph/topics?limit=${limit}`,
                {
                    headers: this.headers,
                    timeout: 10_000,
                },
            );
            return (data as Array<Record<string, unknown>>).map((t) => ({
                id: t.id as string,
                name: t.name as string,
                sessionCount: t.session_count as number,
            }));
        } catch (error) {
            console.warn('[GraphSession] getTopics failed:', (error as Error).message);
            return [];
        }
    }

    /**
     * Esegue community detection per creare/aggiornare cluster.
     */
    async detectCommunities(minClusterSize = 2): Promise<SessionCluster[]> {
        try {
            const data = await ofetch(
                `${this.baseUrl}/sessions/graph/detect-communities?min_cluster_size=${minClusterSize}`,
                {
                    method: 'POST',
                    headers: this.headers,
                    timeout: 30_000,
                },
            );
            return (data as Array<Record<string, unknown>>).map((c) => ({
                id: c.id as string,
                name: c.name as string,
                description: c.description as string,
                sessionCount: c.session_count as number,
                topics: c.topics as string[],
                sessionIds: c.session_ids as string[],
            }));
        } catch (error) {
            console.warn('[GraphSession] detectCommunities failed:', (error as Error).message);
            return [];
        }
    }

    /**
     * Recupera i nodi più connessi a una sessione nel grafo.
     * Per esplorazione esterna: top-N topic hub, sessioni 2-hop, cluster.
     */
    async getConnectedNodes(sessionId: string, topK = 3): Promise<ConnectedNode[]> {
        try {
            const data = await ofetch(
                `${this.baseUrl}/sessions/graph/connected-nodes/${sessionId}?top_k=${topK}`,
                {
                    headers: this.headers,
                    timeout: 10_000,
                },
            );
            return (data as Array<Record<string, unknown>>).map((n) => ({
                id: n.id as string,
                name: n.name as string,
                nodeType: n.node_type as string,
                connectionScore: n.connection_score as number,
                relationType: n.relation_type as string,
                sharedSessions: n.shared_sessions as number,
                description: n.description as string,
            }));
        } catch (error) {
            console.warn('[GraphSession] getConnectedNodes failed:', (error as Error).message);
            return [];
        }
    }

    // ── Prompt Library ───────────────────────────────────────────────

    /**
     * Recupera la libreria prompt.
     */
    async getPromptLibrary(category?: string): Promise<PromptTemplate[]> {
        try {
            const url = category
                ? `${this.baseUrl}/prompts/library?category=${category}`
                : `${this.baseUrl}/prompts/library`;
            const data = await ofetch(url, {
                headers: this.headers,
                timeout: 10_000,
            });
            return this.mapPrompts(data as Array<Record<string, unknown>>);
        } catch (error) {
            console.warn('[GraphSession] getPromptLibrary failed:', (error as Error).message);
            return [];
        }
    }

    /**
     * Salva un prompt template nel grafo.
     */
    async savePromptTemplate(prompt: {
        id?: string;
        label: string;
        content: string;
        category?: string;
        variables?: string[];
        topics?: string[];
    }): Promise<{ id: string; status: string }> {
        const result = await ofetch(`${this.baseUrl}/prompts/library`, {
            method: 'POST',
            headers: this.headers,
            body: prompt,
            timeout: 10_000,
        });
        return result as { id: string; status: string };
    }

    /**
     * Ricerca semantica prompt.
     */
    async searchPrompts(query: string, topK = 5): Promise<PromptTemplate[]> {
        try {
            const data = await ofetch(`${this.baseUrl}/prompts/library/search`, {
                method: 'POST',
                headers: this.headers,
                body: { query, top_k: topK },
                timeout: 10_000,
            });
            return this.mapPrompts(data as Array<Record<string, unknown>>);
        } catch (error) {
            console.warn('[GraphSession] searchPrompts failed:', (error as Error).message);
            return [];
        }
    }

    /**
     * Suggerisce prompt rilevanti per una sessione.
     */
    async suggestPrompts(sessionId: string, topK = 3): Promise<PromptTemplate[]> {
        try {
            const data = await ofetch(
                `${this.baseUrl}/prompts/library/suggest/${sessionId}?top_k=${topK}`,
                {
                    headers: this.headers,
                    timeout: 10_000,
                },
            );
            return this.mapPrompts(data as Array<Record<string, unknown>>);
        } catch (error) {
            console.warn('[GraphSession] suggestPrompts failed:', (error as Error).message);
            return [];
        }
    }

    // ── Helpers ──────────────────────────────────────────────────────

    private mapSearchResults(data: Array<Record<string, unknown>>): SessionSearchResult[] {
        return data.map((r) => ({
            sessionId: r.session_id as string,
            title: r.title as string,
            score: r.score as number,
            topics: r.topics as string[],
            clusterName: r.cluster_name as string,
            turnCount: r.turn_count as number,
            updatedAt: r.updated_at as string,
        }));
    }

    private mapPrompts(data: Array<Record<string, unknown>>): PromptTemplate[] {
        return data.map((p) => ({
            id: p.id as string,
            label: p.label as string,
            content: p.content as string,
            category: (p.category as string) || 'general',
            topics: (p.topics as string[]) || [],
            usageCount: (p.usage_count as number) || 0,
            lastUsedAt: p.last_used_at as string | undefined,
            variables: (p.variables as string[]) || [],
        }));
    }
}

// Singleton instance
export const graphSessionService = new GraphSessionService();
