/**
 * Me4BrAIn Client Types
 */

// Re-export session types from shared
export type { SessionType, SessionConfig, TemplatePrompt } from '@persan/shared';

// === Config ===

export interface Me4BrAInConfig {
    baseUrl?: string;
    apiKey?: string;
    tenantId?: string;
    timeout?: number;
}

// === Errors ===

export class Me4BrAInError extends Error {
    public statusCode?: number;
    public data?: unknown;

    constructor(message: string, statusCode?: number, data?: unknown) {
        super(message);
        this.name = 'Me4BrAInError';
        this.statusCode = statusCode;
        this.data = data;
    }
}

// === Query ===

export interface QueryOptions {
    includeRawResults?: boolean;
    timeoutSeconds?: number;
    sessionId?: string;
}

export interface StreamOptions extends QueryOptions {
    sessionId?: string;
    /** Activity-based timeout: max ms of silence before aborting (default 360_000 = 6 min). */
    chunkSilenceTimeoutMs?: number;
}

export type StreamChunkType =
    | 'start' | 'status' | 'content' | 'tool' | 'done' | 'error'
    | 'thinking' | 'plan' | 'step_start' | 'step_complete' | 'step_error' | 'step_thinking' | 'synthesizing';

export interface StreamChunk {
    type: StreamChunkType;
    session_id?: string;
    content?: string;
    // Activity streaming fields
    message?: string;
    icon?: string;
    step?: number;
    total?: number;
    areas?: string[];
    steps_count?: number;
    domain?: string;
    // Additional fields from backend
    tool?: string;
    tools_called?: string[];
    latency_ms?: number;
    // Tool fields
    tool_call?: {
        tool: string;
        success: boolean;
        latency_ms: number;
        error?: string;
        result?: any;
    };
    total_latency_ms?: number;
    tools_count?: number;
    execution_time_ms?: number;
    error?: string;
}

export interface ToolCallInfo {
    toolName: string;
    arguments: Record<string, unknown>;
    success: boolean;
    latencyMs: number;
    error?: string;
}

export interface EngineQueryResponse {
    query: string;
    answer: string;
    toolsCalled: ToolCallInfo[];
    totalLatencyMs: number;
    rawResults?: unknown[];
}

// === Tools ===

export interface ToolFilter {
    domain?: string;
    category?: string;
    search?: string;
}

export interface ToolInfo {
    name: string;
    description: string;
    domain?: string;
    category?: string;
    parameters?: Record<string, unknown>;
}

export interface DomainStats {
    domain: string;
    toolCount: number;
    tools: string[];
}

export interface CatalogStats {
    totalTools: number;
    domains: DomainStats[];
}

// === Memory (Sessions) ===

export interface Session {
    sessionId: string;
    userId: string;
    createdAt: Date;
    metadata?: Record<string, unknown>;
    config?: import('@persan/shared').SessionConfig;
}

export interface Turn {
    id?: string;
    role: 'user' | 'assistant' | 'system' | 'tool';
    content: string;
    timestamp?: Date;
    metadata?: Record<string, unknown>;
}

export interface SessionContext {
    sessionId: string;
    turns: Turn[];
    turnCount: number;
}

export interface SessionSummary {
    sessionId: string;
    userId: string;
    createdAt: Date;
    messageCount: number;
    config?: import('@persan/shared').SessionConfig;
}

export interface CreateSessionRequest {
    userId?: string;
    metadata?: Record<string, unknown>;
    config?: import('@persan/shared').SessionConfig;
}

export interface AddTurnRequest {
    role: 'user' | 'assistant' | 'system' | 'tool';
    content: string;
    metadata?: Record<string, unknown>;
}

// === Skills (v0.15.0+) ===

/**
 * Risk level for skill security classification.
 */
export type RiskLevel = 'SAFE' | 'NOTIFY' | 'CONFIRM' | 'DENY';

/**
 * Skill pending approval status.
 */
export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'expired';

/**
 * Skill pending HITL approval.
 */
export interface PendingSkill {
    id: string;
    name: string;
    description: string;
    riskLevel: RiskLevel;
    toolChain: string[];
    status: ApprovalStatus;
    createdAt: string;
    reviewedAt?: string;
}

/**
 * Approval action request.
 */
export interface ApprovalRequest {
    note?: string;
}

/**
 * Approval statistics.
 */
export interface ApprovalStats {
    pending: number;
    approved: number;
    rejected: number;
}

/**
 * Skill basic info.
 */
export interface SkillInfo {
    id: string;
    name: string;
    description: string;
    type: 'explicit' | 'crystallized';
    enabled: boolean;
    usageCount: number;
    successRate: number;
    confidence: number;
    version?: string;
}

/**
 * Skill list response.
 */
export interface SkillListResponse {
    skills: SkillInfo[];
    total: number;
}

