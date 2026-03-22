/**
 * Hook per il Session Knowledge Graph.
 *
 * Gestisce la comunicazione con gli endpoint graph del gateway.
 * Stato SWR-like con cache e invalidation.
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

// ── Helper ───────────────────────────────────────────────────────────

async function graphFetch<T>(path: string, options?: RequestInit): Promise<T | null> {
    try {
        const res = await fetch(`${API_URL}${path}`, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        if (!res.ok) return null;
        return await res.json();
    } catch {
        return null;
    }
}

// ── Hook: Clusters ───────────────────────────────────────────────────

export function useSessionClusters() {
    const [clusters, setClusters] = useState<SessionCluster[]>([]);
    const [loading, setLoading] = useState(false);
    const fetchedRef = useRef(false);

    const fetchClusters = useCallback(async () => {
        setLoading(true);
        const data = await graphFetch<SessionCluster[]>('/api/graph/clusters');
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

    return { clusters, loading, refetch: fetchClusters };
}

// ── Hook: Related Sessions ───────────────────────────────────────────

export function useRelatedSessions(sessionId: string | null) {
    const [related, setRelated] = useState<SessionSearchResult[]>([]);
    const [loading, setLoading] = useState(false);

    const fetch = useCallback(async () => {
        if (!sessionId) { setRelated([]); return; }
        setLoading(true);
        const data = await graphFetch<SessionSearchResult[]>(
            `/api/graph/related/${sessionId}?limit=5`
        );
        setRelated(data ?? []);
        setLoading(false);
    }, [sessionId]);

    useEffect(() => { fetch(); }, [fetch]);

    return { related, loading, refetch: fetch };
}

// ── Hook: Semantic Search ────────────────────────────────────────────

export function useSessionSearch() {
    const [results, setResults] = useState<SessionSearchResult[]>([]);
    const [loading, setLoading] = useState(false);

    const search = useCallback(async (query: string) => {
        if (!query.trim()) { setResults([]); return; }
        setLoading(true);
        const data = await graphFetch<SessionSearchResult[]>('/api/graph/search', {
            method: 'POST',
            body: JSON.stringify({ query, top_k: 10, use_reranking: true }),
        });
        setResults(data ?? []);
        setLoading(false);
    }, []);

    return { results, loading, search, clear: () => setResults([]) };
}

// ── Hook: Topics ─────────────────────────────────────────────────────

export function useTopics() {
    const [topics, setTopics] = useState<TopicInfo[]>([]);
    const [loading, setLoading] = useState(false);

    const fetchTopics = useCallback(async () => {
        setLoading(true);
        const data = await graphFetch<TopicInfo[]>('/api/graph/topics?limit=50');
        setTopics(data ?? []);
        setLoading(false);
    }, []);

    useEffect(() => { fetchTopics(); }, [fetchTopics]);

    return { topics, loading, refetch: fetchTopics };
}

// ── Hook: Prompt Library ─────────────────────────────────────────────

export function usePromptLibrary() {
    const [prompts, setPrompts] = useState<PromptTemplate[]>([]);
    const [loading, setLoading] = useState(false);

    const fetchPrompts = useCallback(async (category?: string) => {
        setLoading(true);
        const path = category
            ? `/api/graph/prompts?category=${category}`
            : '/api/graph/prompts';
        const data = await graphFetch<PromptTemplate[]>(path);
        setPrompts(data ?? []);
        setLoading(false);
    }, []);

    const savePrompt = useCallback(async (prompt: Omit<PromptTemplate, 'usageCount' | 'lastUsedAt'>) => {
        const res = await graphFetch<{ id: string }>('/api/graph/prompts', {
            method: 'POST',
            body: JSON.stringify(prompt),
        });
        if (res) await fetchPrompts();
        return res;
    }, [fetchPrompts]);

    const searchPrompts = useCallback(async (query: string) => {
        setLoading(true);
        const data = await graphFetch<PromptTemplate[]>('/api/graph/prompts/search', {
            method: 'POST',
            body: JSON.stringify({ query, top_k: 5 }),
        });
        setPrompts(data ?? []);
        setLoading(false);
    }, []);

    useEffect(() => { fetchPrompts(); }, [fetchPrompts]);

    return { prompts, loading, fetchPrompts, savePrompt, searchPrompts };
}

// ── Hook: Connected Nodes (Graph Exploration) ────────────────────────

export function useConnectedNodes(sessionId: string | null, topK = 3) {
    const [nodes, setNodes] = useState<ConnectedNode[]>([]);
    const [loading, setLoading] = useState(false);

    const fetchNodes = useCallback(async () => {
        if (!sessionId) { setNodes([]); return; }
        setLoading(true);
        const data = await graphFetch<ConnectedNode[]>(
            `/api/graph/connected-nodes/${sessionId}?top_k=${topK}`
        );
        setNodes(data ?? []);
        setLoading(false);
    }, [sessionId, topK]);

    useEffect(() => { fetchNodes(); }, [fetchNodes]);

    return { nodes, loading, refetch: fetchNodes };
}
