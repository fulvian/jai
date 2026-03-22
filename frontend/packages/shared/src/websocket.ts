/**
 * WebSocket Message Protocol
 */

export type WSMessageType =
    | 'session:init'
    | 'session:resubscribe'
    | 'session:resubscribe:ack'
    | 'chat:message'
    | 'chat:thinking'
    | 'chat:status'
    | 'chat:response'
    | 'chat:stream'
    | 'chat:tool'
    | 'tool:start'
    | 'tool:complete'
    | 'canvas:push'
    | 'canvas:update'
    | 'canvas:remove'
    // Monitor notifications (Phase 5)
    | 'monitor:alert'
    | 'monitor:update'
    | 'monitor:created'
    | 'monitor:deleted'
    // HITL Approval (OpenClaw Security)
    | 'approval:request'
    | 'approval:response'
    | 'approval:resolved'
    | 'approval:ack'
    | 'ping'
    | 'pong'
    | 'error';

export interface WSMessage<T = unknown> {
    type: WSMessageType;
    data: T;
    timestamp: number;
    requestId?: string;
}

export interface SessionInitData {
    sessionId: string;
}

export interface ErrorData {
    message: string;
    code: string;
    details?: unknown;
}

// Monitor Alert Data (Phase 4.3)
export interface MonitorAlertData {
    monitorId: string;
    monitorName: string;
    monitorType: string;
    message: string;
    severity: 'info' | 'warning' | 'critical';
    timestamp: string;
    data?: Record<string, unknown>;
}

export interface MonitorUpdateData {
    monitorId: string;
    state: 'active' | 'paused' | 'triggered' | 'completed' | 'error';
    checksCount?: number;
    triggersCount?: number;
    lastCheck?: number;
    nextCheck?: number;
}

