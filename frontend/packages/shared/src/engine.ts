/**
 * Engine Types - Me4BrAIn Engine Interaction
 * 
 * Tipi unificati per l'interazione con Me4BrAIn Tool Calling Engine.
 * Sostituisce i tipi duplicati in me4brain-client e backend Python.
 */

// ============================================================================
// SSE Stream Events
// ============================================================================

export type StreamChunkType =
    | 'thinking'
    | 'plan'
    | 'step_start'
    | 'step_complete'
    | 'tool_call'
    | 'tool_result'
    | 'content'
    | 'done'
    | 'error'
    | 'heartbeat';

export interface BaseStreamChunk {
    type: StreamChunkType;
    timestamp?: number;
}

export interface ThinkingChunk extends BaseStreamChunk {
    type: 'thinking';
    content: string;
}

export interface PlanChunk extends BaseStreamChunk {
    type: 'plan';
    steps: Array<{
        id: number;
        description: string;
        domain: string;
    }>;
}

export interface StepStartChunk extends BaseStreamChunk {
    type: 'step_start';
    step_id: number;
    description: string;
    domain: string;
}

export interface StepCompleteChunk extends BaseStreamChunk {
    type: 'step_complete';
    step_id: number;
    tools_used: string[];
    execution_time_ms: number;
}

export interface ToolCallChunk extends BaseStreamChunk {
    type: 'tool_call';
    tool: string;
    args: Record<string, unknown>;
    status: 'pending' | 'running' | 'complete' | 'error';
}

export interface ToolResultChunk extends BaseStreamChunk {
    type: 'tool_result';
    tool: string;
    result: unknown;
    success: boolean;
    latency_ms?: number;
}

export interface ContentChunk extends BaseStreamChunk {
    type: 'content';
    delta: string;
    done: boolean;
}

export interface DoneChunk extends BaseStreamChunk {
    type: 'done';
    toolsCalled: string[];
    latencyMs: number;
    tokensUsed?: number;
}

export interface ErrorChunk extends BaseStreamChunk {
    type: 'error';
    error: string;
    code?: string;
    details?: unknown;
}

export interface HeartbeatChunk extends BaseStreamChunk {
    type: 'heartbeat';
}

export type StreamChunk =
    | ThinkingChunk
    | PlanChunk
    | StepStartChunk
    | StepCompleteChunk
    | ToolCallChunk
    | ToolResultChunk
    | ContentChunk
    | DoneChunk
    | ErrorChunk
    | HeartbeatChunk;

// ============================================================================
// Query Options
// ============================================================================

export interface EngineQueryOptions {
    /** Session ID per memoria conversazionale */
    sessionId?: string;
    /** Timeout in millisecondi (default: 300000 = 5min) */
    timeout?: number;
    /** Include raw tool results in response */
    includeRaw?: boolean;
    /** User ID per multi-tenancy */
    userId?: string;
    /** Tenant ID per multi-tenancy */
    tenantId?: string;
}

// ============================================================================
// Tool Call Info
// ============================================================================

export interface ToolCallInfo {
    name: string;
    success: boolean;
    latencyMs: number;
    error?: string;
}

// ============================================================================
// Engine Stats
// ============================================================================

export interface EngineStats {
    totalQueries: number;
    avgLatencyMs: number;
    toolCallsCount: number;
    errorRate: number;
    uptime: number;
}

