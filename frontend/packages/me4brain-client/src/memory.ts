/**
 * Memory Namespace
 *
 * Provides session management functionality for Me4BrAIn Working Memory.
 */

import type { Me4BrAInClient } from './client.js';
import type {
    Session,
    SessionContext,
    Turn,
} from './types.js';

export class MemoryNamespace {
    constructor(private client: Me4BrAInClient) { }

    /**
     * Create a new working memory session.
     * The session is persisted in Me4Brain's Redis store.
     * 
     * @param userId - User ID (default: 'default')
     * @param metadata - Optional metadata for the session
     * @returns Session with sessionId, userId, and createdAt
     */
    async createSession(userId: string = 'default', metadata: Record<string, unknown> = {}): Promise<Session> {
        const response = await this.client.request<{
            session_id: string;
            user_id: string;
            created_at: string;
        }>('POST', '/working/sessions', {
            body: { user_id: userId, metadata },
        });

        return {
            sessionId: response.session_id,
            userId: response.user_id,
            createdAt: new Date(response.created_at),
        };
    }

    /**
     * Get session context (conversation history).
     */
    async getSession(sessionId: string, userId: string = 'default', maxTurns: number = 20): Promise<SessionContext> {
        const response = await this.client.request<{
            session_id: string;
            messages: Array<{
                id: string;
                role: string;
                content: string;
                timestamp: string;
                metadata?: Record<string, unknown>;
            }>;
            count: number;
        }>('GET', `/working/sessions/${sessionId}/messages`, {
            params: { user_id: userId, count: String(maxTurns) },
        });

        return {
            sessionId: response.session_id,
            turns: response.messages.map((m) => ({
                id: m.id,
                role: m.role as 'user' | 'assistant' | 'system' | 'tool',
                content: m.content,
                timestamp: new Date(m.timestamp),
                metadata: m.metadata,
            })),
            turnCount: response.count,
        };
    }

    /**
     * Add a turn (message) to a session.
     */
    async addTurn(
        sessionId: string,
        role: 'user' | 'assistant' | 'system' | 'tool',
        content: string,
        userId: string = 'default',
        metadata: Record<string, unknown> = {}
    ): Promise<Turn> {
        const response = await this.client.request<{
            id: string;
            role: string;
            content: string;
            timestamp: string;
            metadata: Record<string, unknown>;
        }>('POST', `/working/sessions/${sessionId}/messages`, {
            params: { user_id: userId },
            body: { role, content, metadata },
        });

        return {
            id: response.id,
            role: response.role as 'user' | 'assistant' | 'system' | 'tool',
            content: response.content,
            timestamp: new Date(response.timestamp),
            metadata: response.metadata,
        };
    }

    /**
     * Delete a session.
     */
    async deleteSession(sessionId: string, userId: string = 'default'): Promise<boolean> {
        const response = await this.client.request<{ deleted: boolean }>('DELETE', `/working/sessions/${sessionId}`, {
            params: { user_id: userId },
        });
        return response.deleted;
    }
}
