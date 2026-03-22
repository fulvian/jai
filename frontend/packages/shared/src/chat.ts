/**
 * Chat Message Types
 */

export type Channel = 'webchat' | 'telegram' | 'whatsapp';

export interface ChatMessage {
    sessionId: string;
    content: string;
    channel: Channel;
    userId?: string;
}

export interface ToolCallResult {
    name: string;
    success: boolean;
    latencyMs: number;
}

export interface ChatResponse {
    requestId: string;
    content: string;
    isStreaming?: boolean;
    done?: boolean;
    toolsCalled?: ToolCallResult[];
    latencyMs?: number;
}

// === Chat Turn (Unified) ===

export interface ChatTurn {
    id: string;
    role: 'user' | 'assistant' | 'system';
    content: string;
    timestamp: string;
    /** Tools utilizzati in questo turn (solo assistant) */
    toolsUsed?: string[];
    /** Feedback utente su questo turn */
    feedback?: {
        score: 1 | -1;
        comment?: string;
        timestamp: string;
    };
    /** Flag per identificare risposte parziali (disconnessione durante streaming) */
    isPartial?: boolean;
}

// === Chat Session (Complete) ===

export interface ChatSession {
    session_id: string;
    title: string;
    created_at: string;
    updated_at: string;
    turns: ChatTurn[];
    config?: SessionConfig;
}

export interface SessionSummary {
    session_id: string;
    title: string;
    created_at: string;
    updated_at: string;
    message_count: number;
    config?: SessionConfig;
}

// === Session Management ===

export type SessionType = 'free' | 'topic' | 'template';

export interface TemplatePrompt {
    id: string;
    label: string;
    content: string;
    enabled: boolean;
    variables?: string[];
    createdAt: string;
    updatedAt: string;
}

export interface SessionConfig {
    type: SessionType;
    /** Topic sessions: argomento di ricerca */
    topic?: string;
    /** Topic sessions: tags di categorizzazione */
    tags?: string[];
    /** Template sessions: prompt predefiniti riutilizzabili */
    prompts?: TemplatePrompt[];
    /** Template sessions: cron expression per esecuzione futura (agente autonomo) */
    schedule?: string;
}

// === Graph-Based Session Types (Session Knowledge Graph) ===

export interface SessionCluster {
    id: string;
    name: string;
    description: string;
    sessionCount: number;
    topics: string[];
    sessionIds: string[];
}

export interface SessionGraphMeta {
    /** Topic estratti automaticamente dalla conversazione */
    topics: string[];
    /** Cluster di appartenenza */
    clusterName?: string;
    /** Sessioni semanticamente correlate */
    relatedSessionIds?: string[];
    /** Se la sessione è stata indicizzata nel grafo */
    isIndexed: boolean;
}

export interface TopicInfo {
    id: string;
    name: string;
    sessionCount: number;
}

// === Cache-Aside Types (Phase 2) ===

export interface CachedSession {
    data: ChatSession;
    createdAt: number;
    ttl: number;
}

export interface CacheMetrics {
    hitRate: number;
    l1Hits: number;
    l2Hits: number;
    misses: number;
    apiErrors: number;
}
