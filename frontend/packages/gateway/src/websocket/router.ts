import { WebSocket } from 'ws';
import * as crypto from 'crypto';
import { getApprovalQueue } from '../services/approval_queue.js';
import { sessionManager } from '../services/session_manager_instance.js';
import type { WSMessage, ChatMessage } from '@persan/shared';

export class MessageRouter {
    constructor() { }

    async handle(socket: WebSocket, sessionId: string, msg: WSMessage): Promise<void> {
        switch (msg.type) {
            case 'chat:message':
                await this.handleChat(socket, sessionId, msg.data as ChatMessage, msg.requestId);
                break;

            case 'session:resubscribe':
                await this.handleResubscribe(socket, sessionId, msg);
                break;

            case 'ping':
                socket.send(JSON.stringify({
                    type: 'pong',
                    data: {},
                    timestamp: Date.now(),
                    requestId: msg.requestId,
                }));
                break;

            // HITL Approval handlers
            case 'approval:response':
                await this.handleApprovalResponse(socket, sessionId, msg);
                break;

            default:
                socket.send(JSON.stringify({
                    type: 'error',
                    data: { message: `Unknown message type: ${msg.type}`, code: 'UNKNOWN_TYPE' },
                    timestamp: Date.now(),
                    requestId: msg.requestId,
                }));
        }
    }

    private async handleApprovalResponse(socket: WebSocket, _sessionId: string, msg: WSMessage): Promise<void> {
        const data = msg.data as { requestId: string; approved: boolean };
        const userId = 'default'; // TODO: Get from session/auth
        const queue = getApprovalQueue();

        const success = data.approved
            ? await queue.approve(data.requestId, userId)
            : await queue.deny(data.requestId, userId);

        socket.send(JSON.stringify({
            type: 'approval:ack',
            data: { requestId: data.requestId, success, approved: data.approved },
            timestamp: Date.now(),
            requestId: msg.requestId,
        }));
    }

    private async handleResubscribe(socket: WebSocket, sessionIdFromSocket: string, msg: WSMessage): Promise<void> {
        const { sessionIds } = msg.data as { sessionIds: string[] };
        const { connectionRegistry } = await import('./registry.js');
        const { queryExecutor } = await import('../services/query_executor.js');

        console.log(`[MessageRouter] 🔄 Resubscribe request from connection ${sessionIdFromSocket} for sessions: ${sessionIds.join(', ')}`);

        for (const targetSessionId of sessionIds) {
            // 1. Registra Alias
            connectionRegistry.addAlias(socket, targetSessionId);

            // 2. Replay Buffer (ultimo requestId se presente)
            const bufferedMessages = await queryExecutor.getBuffer(targetSessionId);
            if (bufferedMessages.length > 0) {
                console.log(`[MessageRouter] ⏪ Replaying ${bufferedMessages.length} buffered messages for session ${targetSessionId}`);
                for (const bufferedMsg of bufferedMessages) {
                    socket.send(JSON.stringify(bufferedMsg));
                }
            }
        }

        socket.send(JSON.stringify({
            type: 'session:resubscribe:ack',
            data: { success: true, count: sessionIds.length },
            timestamp: Date.now(),
            requestId: msg.requestId,
        }));
    }

    // FIX Issue #8: Track alias registration to prevent race conditions
    private aliasLock: Set<string> = new Set();

    async handleChat(
        socket: WebSocket,
        sessionIdFromSocket: string,
        msg: ChatMessage,
        requestId?: string
    ): Promise<void> {
        const userId = 'default'; // TODO: Get from session/auth
        const reqId = requestId ?? crypto.randomUUID();

        // SOTA 2026: Supporta multiplexing. Se il messaggio arriva con un sessionId 
        // diverso da quello originale della connessione, registralo come alias.
        const targetSessionId = msg.sessionId || sessionIdFromSocket;

        // FIX Issue #8: Serialize alias registration to prevent race on concurrent messages
        const aliasKey = `${sessionIdFromSocket}:${targetSessionId}`;
        if (!this.aliasLock.has(aliasKey)) {
            this.aliasLock.add(aliasKey);
            const { connectionRegistry } = await import('./registry.js');
            connectionRegistry.addAlias(socket, targetSessionId);
            // Clean up lock after a short delay to allow future re-registrations
            setTimeout(() => this.aliasLock.delete(aliasKey), 5000);
        }

        try {
            // 1. Persist User Message
            await sessionManager.addTurn(targetSessionId, {
                id: crypto.randomUUID(),
                role: 'user',
                content: msg.content,
                timestamp: new Date().toISOString(),
            });

            // 2. Delegate execution to QueryExecutor
            const { queryExecutor } = await import('../services/query_executor.js');
            await queryExecutor.execute(targetSessionId, msg.content, reqId, userId);

            console.log(`[MessageRouter] Query delegated to background executor for session ${targetSessionId}`);
        } catch (error: any) {
            console.error('💥 Failed to delegate chat execution:', error?.message);
            console.error('💥 Stack trace:', error?.stack);
            console.error('💥 Config: ME4BRAIN_URL =', process.env.ME4BRAIN_URL, '| REDIS_URL =', process.env.REDIS_URL);
            socket.send(JSON.stringify({
                type: 'error',
                data: {
                    message: 'Failed to start background execution',
                    code: 'EXECUTION_START_ERROR',
                    sessionId: targetSessionId,
                    detail: error?.message || 'Unknown error',
                },
                timestamp: Date.now(),
                requestId: reqId,
            }));
        }
    }
}
