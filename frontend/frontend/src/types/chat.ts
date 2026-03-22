/**
 * Chat types for PersAn.
 */

// Re-export session management types
export type { SessionType, SessionConfig, TemplatePrompt, SessionCluster, SessionGraphMeta, TopicInfo } from '@persan/shared';

export type MessageRole = 'user' | 'assistant' | 'system';

export interface Message {
    id: string;
    role: MessageRole;
    content: string;
    timestamp: Date;
    sources?: Source[];
    toolsUsed?: string[];
    isStreaming?: boolean;
    /** Flag per identificare messaggi parziali (disconnessione durante streaming) */
    isPartial?: boolean;
    /** 🎯 NEW: Thinking/reasoning process captured during streaming */
    thinking?: string;
    feedback?: {
        score: 1 | -1;
        comment?: string;
        timestamp: string;
    };
}

export interface Source {
    title: string;
    url?: string;
    snippet?: string;
    domain?: string;
}

export type ChunkType =
    | 'content' | 'reasoning' | 'tool' | 'sources' | 'session' | 'done' | 'error'
    | 'thinking' | 'plan' | 'step_start' | 'step_thinking' | 'step_complete' | 'step_error' | 'synthesizing'
    | 'status' | 'edit_applied';

export interface StreamChunk {
    type: ChunkType;
    content?: string;
    session_id?: string;
    // Activity streaming
    message?: string;
    icon?: string;
    step?: number;
    total?: number;
    areas?: string[];
    steps_count?: number;
    // Tool info
    tool_name?: string;
    tool_result?: Record<string, unknown>;
    sources?: Source[];
    error?: string;
    tools_count?: number;
    latency_ms?: number;
}

export interface ChatRequest {
    message: string;
    session_id?: string;
    use_memory?: boolean;
}

export interface Session {
    id: string;
    createdAt: Date;
    lastMessage?: string;
    messageCount: number;
    primaryDomain?: string;
    config?: import('@persan/shared').SessionConfig;
}
