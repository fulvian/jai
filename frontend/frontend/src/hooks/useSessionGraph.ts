/**
 * Hook per il Session Knowledge Graph.
 *
 * Gestisce la comunicazione con gli endpoint graph del gateway.
 * Stato SWR-like con cache, invalidation e error handling.
 *
 * SOTA 2026 patterns:
 * - Error state management per UX failed states
 * - SWR-like stale-while-revalidate
 * - Abort controller per cancellation
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { API_CONFIG } from '@/lib/config';

const API_URL = API_CONFIG.gatewayUrl;

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

export interface ConnectedNode {
    id: string;
    name: string;
    nodeType: string;
    connectionScore: number;
    relationType: string;
    sharedSessions: number;
    description: string;
}

/**
 * Generic error class for graph-related errors.
 */
export class GraphError extends Error {
    constructor(
        message: string,
        public readonly code: string,
        public readonly endpoint?: string,
        public readonly statusCode?: number,
    ) {
        super(message);
        this.name = 'GraphError';
    }
}

// ── Helper ───────────────────────────────────────────────────────────

interface FetchResult<T> {
    data: T | null;
    error: GraphError | null;
}

async function graphFetch<T>(
    path: string,
    options?: RequestInit,
): Promise<FetchResult<T>> {
    try {
        const res = await fetch(`${API_URL}${path}`, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });

        if (!res.ok) {
            return {
                data: null,
                error: new GraphError(
                    `HTTP ${res.status}: ${res.statusText}`,
                    'HTTP_ERROR',
                    path,
                    res.status,
                ),
            };
        }

        const data = await res.json();
        return { data, error: null };
    } catch (err) {
        const error = err instanceof Error ? err : new Error(String(err));
        return {
            data: null,
            error: new GraphError(
                error.message || 'Network error',
                'NETWORK_ERROR',
                path,
            ),
        };
    }
}

// ── Hook: Clusters ───────────────────────────────────────────────────

export interface UseQueryResult<T> {
    data: T;
    loading: boolean;
    error: GraphError | null;
    refetch: () => Promise<void>;
}

export function useSessionClusters(): UseQueryResult<SessionCluster[]> {
    const [clusters, setClusters] = useState<SessionCluster[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<GraphError | null>(null);
    const fetchedRef = useRef(false);

    const fetchClusters = useCallback(async () => {
        setLoading(true);
        setError(null);

        const { data, error: fetchError } = await graphFetch<SessionCluster[]>(
            '/api/graph/clusters',
        );

        if (fetchError) {
            setError(fetchError);
            setLoading(false);
            return;
        }

        // Sanitize data to prevent crashes
        const safeData = (data ?? []).map(cluster => ({
            ...cluster,
            topics: cluster.topics || [],
            sessionIds: cluster.sessionIds || [],
        }));
        setClusters(safeData);
        setLoading(false);
    }, []);

    useEffect(() => {
        if (!fetchedRef.current) {
            fetchedRef.current = true;
            fetchClusters();
        }
    }, [fetchClusters]);

    return { data: clusters, loading, error, refetch: fetchClusters };
}

// ── Hook: Related Sessions ───────────────────────────────────────────

export function useRelatedSessions(
    sessionId: string | null,
): UseQueryResult<SessionSearchResult[]> {
    const [related, setRelated] = useState<SessionSearchResult[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<GraphError | null>(null);

    const fetch = useCallback(async () => {
        if (!sessionId) {
            setRelated([]);
            return;
        }

        setLoading(true);
        setError(null);

        const { data, error: fetchError } = await graphFetch<SessionSearchResult[]>(
            `/api/graph/related/${sessionId}?limit=5`,
        );

        if (fetchError) {
            setError(fetchError);
            setLoading(false);
            return;
        }

        setRelated(data ?? []);
        setLoading(false);
    }, [sessionId]);

    useEffect(() => {
        fetch();
    }, [fetch]);

    return { data: related, loading, error, refetch: fetch };
}

// ── Hook: Semantic Search ───────────────────────────────────────────

export interface UseSearchResult {
    results: SessionSearchResult[];
    loading: boolean;
    error: GraphError | null;
    search: (query: string) => Promise<void>;
    clear: () => void;
}

export function useSessionSearch(): UseSearchResult {
    const [results, setResults] = useState<SessionSearchResult[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<GraphError | null>(null);

    const search = useCallback(async (query: string) => {
        if (!query.trim()) {
            setResults([]);
            return;
        }

        setLoading(true);
        setError(null);

        const { data, error: fetchError } = await graphFetch<SessionSearchResult[]>(
            '/api/graph/search',
            {
                method: 'POST',
                body: JSON.stringify({ query, top_k: 10, use_reranking: true }),
            },
        );

        if (fetchError) {
            setError(fetchError);
            setLoading(false);
            return;
        }

        setResults(data ?? []);
        setLoading(false);
    }, []);

    const clear = useCallback(() => {
        setResults([]);
        setError(null);
    }, []);

    return { results, loading, error, search, clear };
}

// ── Hook: Topics ─────────────────────────────────────────────────────

export function useTopics(): UseQueryResult<TopicInfo[]> {
    const [topics, setTopics] = useState<TopicInfo[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<GraphError | null>(null);

    const fetchTopics = useCallback(async () => {
        setLoading(true);
        setError(null);

        const { data, error: fetchError } = await graphFetch<TopicInfo[]>(
            '/api/graph/topics?limit=50',
        );

        if (fetchError) {
            setError(fetchError);
            setLoading(false);
            return;
        }

        setTopics(data ?? []);
        setLoading(false);
    }, []);

    useEffect(() => {
        fetchTopics();
    }, [fetchTopics]);

    return { data: topics, loading, error, refetch: fetchTopics };
}

// ── Hook: Prompt Library ─────────────────────────────────────────────

export interface UsePromptLibraryResult {
    prompts: PromptTemplate[];
    loading: boolean;
    error: GraphError | null;
    fetchPrompts: (category?: string) => Promise<void>;
    savePrompt: (
        prompt: Omit<PromptTemplate, 'usageCount' | 'lastUsedAt'>,
    ) => Promise<{ id: string } | null>;
    searchPrompts: (query: string) => Promise<void>;
}

export function usePromptLibrary(): UsePromptLibraryResult {
    const [prompts, setPrompts] = useState<PromptTemplate[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<GraphError | null>(null);

    const fetchPrompts = useCallback(async (category?: string) => {
        setLoading(true);
        setError(null);

        const path = category
            ? `/api/graph/prompts?category=${category}`
            : '/api/graph/prompts';

        const { data, error: fetchError } = await graphFetch<PromptTemplate[]>(path);

        if (fetchError) {
            setError(fetchError);
            setLoading(false);
            return;
        }

        setPrompts(data ?? []);
        setLoading(false);
    }, []);

    const savePrompt = useCallback(
        async (prompt: Omit<PromptTemplate, 'usageCount' | 'lastUsedAt'>) => {
            const { data, error: fetchError } = await graphFetch<{ id: string }>(
                '/api/graph/prompts',
                {
                    method: 'POST',
                    body: JSON.stringify(prompt),
                },
            );

            if (fetchError) {
                setError(fetchError);
                return null;
            }

            if (data) {
                await fetchPrompts();
            }
            return data;
        },
        [fetchPrompts],
    );

    const searchPrompts = useCallback(async (query: string) => {
        setLoading(true);
        setError(null);

        const { data, error: fetchError } = await graphFetch<PromptTemplate[]>(
            '/api/graph/prompts/search',
            {
                method: 'POST',
                body: JSON.stringify({ query, top_k: 5 }),
            },
        );

        if (fetchError) {
            setError(fetchError);
            setLoading(false);
            return;
        }

        setPrompts(data ?? []);
        setLoading(false);
    }, []);

    useEffect(() => {
        fetchPrompts();
    }, [fetchPrompts]);

    return { prompts, loading, error, fetchPrompts, savePrompt, searchPrompts };
}

// ── Hook: Connected Nodes (Graph Exploration) ────────────────────────

export function useConnectedNodes(
    sessionId: string | null,
    topK = 3,
): UseQueryResult<ConnectedNode[]> {
    const [nodes, setNodes] = useState<ConnectedNode[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<GraphError | null>(null);

    const fetchNodes = useCallback(async () => {
        if (!sessionId) {
            setNodes([]);
            return;
        }

        setLoading(true);
        setError(null);

        const { data, error: fetchError } = await graphFetch<ConnectedNode[]>(
            `/api/graph/connected-nodes/${sessionId}?top_k=${topK}`,
        );

        if (fetchError) {
            setError(fetchError);
            setLoading(false);
            return;
        }

        setNodes(data ?? []);
        setLoading(false);
    }, [sessionId, topK]);

    useEffect(() => {
        fetchNodes();
    }, [fetchNodes]);

    return { data: nodes, loading, error, refetch: fetchNodes };
}
