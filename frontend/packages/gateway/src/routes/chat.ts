/**
 * Chat Session Routes - API per gestione sessioni chat
 *
 * Endpoints:
 * - POST   /api/chat                              - Invia messaggio (SSE streaming)
 * - GET    /api/chat/sessions                      - Lista sessioni
 * - POST   /api/chat/sessions                      - Crea nuova sessione
 * - GET    /api/chat/sessions/:id                  - Carica sessione
 * - DELETE /api/chat/sessions/:id                  - Elimina sessione
 * - PATCH  /api/chat/sessions/:id                  - Aggiorna titolo
 * - POST   /api/chat/sessions/:id/message          - Aggiunge messaggio
 * - DELETE /api/chat/sessions/:id/turns/:turnIndex - Cancella singolo turn
 * - PUT    /api/chat/sessions/:id/turns/:turnIndex - Modifica turn
 * - POST   /api/chat/sessions/:id/retry/:turnIndex - Retry query
 */

import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { randomUUID } from 'crypto';
import { Me4BrAInClient } from '@persan/me4brain-client';
import type { SessionConfig, ChatTurn } from '@persan/shared';
import { sessionManager } from '../services/session_manager_instance.js';

// Types for route params
interface SessionParams {
    id: string;
}

interface TurnParams {
    id: string;
    turnIndex: string;
}

/**
 * Generate a unique turn ID
 */
function generateTurnId(): string {
    return `turn-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

// FIX Issue #7: Track sessions with active SSE streams to prevent double-streaming
// Export for /status endpoint to check SSE streaming state
export const activeSSESessions: Set<string> = new Set();

/**
 * Anomaly detector for detecting infinite loops in LLM thinking/content generation
 */
const anomalyDetectorSSE = {
    thinkingPatterns: new Map<string, string[]>(),
    contentPatterns: new Map<string, string[]>(),
    windowSize: 10,
    anomalyThreshold: 8,

    detect(sessionId: string, type: 'thinking' | 'content', content: string): boolean {
        const map = type === 'thinking' ? this.thinkingPatterns : this.contentPatterns;
        if (!map.has(sessionId)) map.set(sessionId, []);
        const history = map.get(sessionId)!;
        history.push(content);
        
        if (history.length > this.windowSize) history.shift();
        
        if (history.length >= this.windowSize) {
            const backtickCount = history.filter(c => c.includes('`')).length;
            if (backtickCount >= this.anomalyThreshold) {
                console.warn(`[SSE] 🚨 ANOMALY DETECTED: Backtick loop in ${type} for session ${sessionId}`);
                return true;
            }
            const uniqueChunks = new Set(history);
            if (uniqueChunks.size <= 2) {
                console.warn(`[SSE] 🚨 ANOMALY DETECTED: Repetitive ${type} for session ${sessionId}`);
                return true;
            }
        }
        return false;
    },

    cleanup(sessionId: string) {
        this.thinkingPatterns.delete(sessionId);
        this.contentPatterns.delete(sessionId);
    }
};

/**
 * Streams a query to Me4BrAIn and writes SSE chunks to the response.
 * Shared logic between POST /api/chat, retry, and edit.
 */
async function streamQueryToResponse(
    me4brain: Me4BrAInClient,
    sessionId: string,
    message: string,
    reply: FastifyReply
): Promise<void> {
    // FIX Issue #7: Guard against double-streaming on the same session
    if (activeSSESessions.has(sessionId)) {
        console.warn(`[SSE-Guard] ⚠️ Session ${sessionId} already has an active stream. Rejecting duplicate.`);
        reply.raw.writeHead(409, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Access-Control-Allow-Origin': '*',
        });
        reply.raw.write(`data: ${JSON.stringify({ type: 'error', error: 'Sessione già in elaborazione. Attendi il completamento della richiesta precedente.' })}\n\n`);
        reply.raw.write('data: [DONE]\n\n');
        reply.raw.end();
        return;
    }

    activeSSESessions.add(sessionId);

    // Set SSE headers
    reply.raw.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
        'Access-Control-Allow-Origin': '*',
    });

    // Send session ID first
    reply.raw.write(`data: ${JSON.stringify({ type: 'session', session_id: sessionId })}\n\n`);

    // FIX: Declare fullResponse outside try block to make it accessible in finally
    let fullResponse = '';

    try {
        // NOTE: BUG-5 FIX - Do NOT call sessionManager.addTurn() for user/assistant
        // Me4BrAIn persists these automatically via _persist_interaction() after streaming
        // Calling addTurn here would create duplicates in the Working Memory

        // Start SSE heartbeat to keep connection alive during long queries
        const heartbeatInterval = setInterval(() => {
            try {
                reply.raw.write(': heartbeat\n\n');
            } catch {
                clearInterval(heartbeatInterval);
            }
        }, 15000);

        // Stream from Me4BrAIn
        console.log('[DEBUG-SSE] Calling queryStream for session:', sessionId);
        const stream = me4brain.engine.queryStream(message, {
            sessionId,
            includeRawResults: true,
        });
        console.log('[DEBUG-SSE] queryStream returned, entering for-await...');

        for await (const chunk of stream) {
            console.log('[DEBUG-SSE] Chunk received:', chunk.type, JSON.stringify(chunk).slice(0, 100));

            // 🚨 CRITICAL FIX: Detect anomalous patterns (backtick loops, infinite thinking)
            if (chunk.type === 'thinking' && chunk.content) {
                if (anomalyDetectorSSE.detect(sessionId, 'thinking', chunk.content)) {
                    console.error(`[SSE] 🔴 Aborting stream due to anomalous thinking pattern`);
                    reply.raw.write(`data: ${JSON.stringify({ 
                        type: 'error', 
                        error: 'LLM thinking process detected infinite loop - query aborted' 
                    })}\n\n`);
                    anomalyDetectorSSE.cleanup(sessionId);
                    clearInterval(heartbeatInterval);
                    reply.raw.write('data: [DONE]\n\n');
                    reply.raw.end();
                    return;
                }
            }

            // Content chunks: accumulate response and forward
            if (chunk.type === 'content') {
                // BUG-3 FIX: Check for BOTH 'content' (Me4BrAIn) and 'delta' (legacy)
                const text = (chunk as any).content || (chunk as any).delta;
                if (text) {
                    // 🚨 Check for anomalies in content too
                    if (anomalyDetectorSSE.detect(sessionId, 'content', text)) {
                        console.error(`[SSE] 🔴 Aborting stream due to anomalous content pattern`);
                        reply.raw.write(`data: ${JSON.stringify({ 
                            type: 'error', 
                            error: 'LLM content generation detected infinite loop - query aborted' 
                        })}\n\n`);
                        anomalyDetectorSSE.cleanup(sessionId);
                        clearInterval(heartbeatInterval);
                        reply.raw.write('data: [DONE]\n\n');
                        reply.raw.end();
                        return;
                    }
                    fullResponse += text;
                    reply.raw.write(`data: ${JSON.stringify({ type: 'content', content: text })}\n\n`);
                }
                continue;
            }

            // Done: Me4BrAIn already persisted the interaction, just forward the event
            if (chunk.type === 'done') {
                anomalyDetectorSSE.cleanup(sessionId);
                reply.raw.write(`data: ${JSON.stringify({
                    type: 'done',
                    tools_count: chunk.tools_called?.length ?? 0,
                    latency_ms: chunk.latency_ms ?? 0,
                })}\n\n`);
                continue;
            }

            // Skip internal-only events
            if (chunk.type === 'start') {
                continue;
            }

            // BUG-3 FIX: Normalize 'message' field to 'content' for thinking/status events
            if (chunk.type === 'thinking' || chunk.type === 'status') {
                const message = (chunk as any).message || (chunk as any).content;
                const normalized = {
                    ...chunk,
                    content: message,
                    message: message, // Ensure legacy support for frontend hooks
                };
                reply.raw.write(`data: ${JSON.stringify(normalized)}\n\n`);
                continue;
            }

            // Forward ALL other events as-is
            reply.raw.write(`data: ${JSON.stringify(chunk)}\n\n`);
        }

        clearInterval(heartbeatInterval);
    } catch (error) {
        console.error('[DEBUG-SSE] ERROR in streaming:', error);
        anomalyDetectorSSE.cleanup(sessionId);
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        reply.raw.write(`data: ${JSON.stringify({ type: 'error', error: errorMessage })}\n\n`);
    } finally {
        // FIX Issue #7: Release the session guard
        activeSSESessions.delete(sessionId);
        anomalyDetectorSSE.cleanup(sessionId);
        console.log('[DEBUG-SSE] Finally block - ending response');

        // FIX: Save partial response if client disconnected mid-stream
        // This ensures that if user refreshes/closes tab during streaming,
        // the accumulated response is persisted to Working Memory
        if (fullResponse.trim()) {
            try {
                const partialTurn: ChatTurn = {
                    id: `turn-partial-${Date.now()}`,
                    role: 'assistant',
                    content: fullResponse,
                    timestamp: new Date().toISOString(),
                    isPartial: true, // Flag to identify incomplete responses
                };
                await sessionManager.addTurn(sessionId, partialTurn);
                console.log(`[SSE] Saved partial response (${fullResponse.length} chars) for session ${sessionId}`);
            } catch (e) {
                console.error(`[SSE] Failed to save partial response for session ${sessionId}:`, e);
            }
        }

        reply.raw.write('data: [DONE]\n\n');
        reply.raw.end();
    }
}

export async function chatRoutes(app: FastifyInstance): Promise<void> {
    // Initialize Me4BrAIn client
    const me4brain = new Me4BrAInClient({
        baseUrl: process.env.ME4BRAIN_URL ?? 'http://localhost:8000/v1',
        apiKey: process.env.ME4BRAIN_API_KEY,
    });

    /**
     * POST /api/chat - Invia messaggio e ricevi risposta in SSE streaming
     */
    app.post<{ Body: { message: string; session_id?: string } }>(
        '/api/chat',
        async (request, reply) => {
            const { message, session_id } = request.body;
            const sessionId = session_id || randomUUID();
            await streamQueryToResponse(me4brain, sessionId, message, reply);
        }
    );

    /**
     * GET /api/chat/sessions - Lista tutte le sessioni
     */
    app.get('/api/chat/sessions', async (_request: FastifyRequest, reply: FastifyReply) => {
        const sessionList = await sessionManager.listSessions(50);
        return reply.send({ sessions: sessionList });
    });

    /**
     * POST /api/chat/sessions - Crea nuova sessione
     */
    app.post('/api/chat/sessions', async (_request: FastifyRequest, reply: FastifyReply) => {
        const body = _request.body as { title?: string; config?: SessionConfig } | undefined;
        const sessionId = randomUUID();
        const title = body?.title ?? 'Nuova conversazione';
        const config = body?.config;
        await sessionManager.createSession(sessionId, title, config);
        return reply.status(201).send({ session_id: sessionId, config });
    });

    /**
     * GET /api/chat/sessions/:id - Carica una sessione specifica
     */
    app.get<{ Params: SessionParams }>(
        '/api/chat/sessions/:id',
        async (request: FastifyRequest<{ Params: SessionParams }>, reply: FastifyReply) => {
            const { id } = request.params;
            const session = await sessionManager.getSession(id);

            if (!session) {
                return reply.status(404).send({ error: 'Session not found' });
            }

            return reply.send({
                session_id: session.session_id,
                title: session.title,
                created_at: session.created_at,
                updated_at: session.updated_at,
                turns: session.turns,
                config: session.config,
            });
        }
    );

    /**
     * GET /api/chat/sessions/:id/status - Verifica se la sessione ha task attivi
     */
    app.get<{ Params: SessionParams }>(
        '/api/chat/sessions/:id/status',
        async (request: FastifyRequest<{ Params: SessionParams }>, reply: FastifyReply) => {
            const { id } = request.params;
            const { queryExecutor } = await import('../services/query_executor.js');
            // FIX: Check both WS (queryExecutor) and SSE (activeSSESessions) streaming states
            const isActiveWS = queryExecutor.isSessionActive(id);
            const isActiveSSE = activeSSESessions.has(id);
            const isActive = isActiveWS || isActiveSSE;
            return reply.send({
                session_id: id,
                isActive,
                activeWS: isActiveWS,
                activeSSE: isActiveSSE,
            });
        }
    );

    /**
     * DELETE /api/chat/sessions/:id - Elimina una sessione
     */
    app.delete<{ Params: SessionParams }>(
        '/api/chat/sessions/:id',
        async (request: FastifyRequest<{ Params: SessionParams }>, reply: FastifyReply) => {
            const { id } = request.params;
            const deleted = await sessionManager.deleteSession(id);

            if (!deleted) {
                return reply.status(404).send({ error: 'Session not found' });
            }

            return reply.status(204).send();
        }
    );

    /**
     * PATCH /api/chat/sessions/:id - Aggiorna titolo sessione
     */
    app.patch<{ Params: SessionParams; Body: { title?: string } }>(
        '/api/chat/sessions/:id',
        async (
            request: FastifyRequest<{ Params: SessionParams; Body: { title?: string } }>,
            reply: FastifyReply
        ) => {
            const { id } = request.params;
            const { title } = request.body ?? {};

            if (!title) {
                return reply.status(400).send({ error: 'Title is required' });
            }

            const updated = await sessionManager.updateTitle(id, title);
            if (!updated) {
                return reply.status(404).send({ error: 'Session not found' });
            }

            return reply.send({ success: true });
        }
    );

    /**
     * PUT /api/chat/sessions/:id/config - Aggiorna config sessione
     */
    app.put<{ Params: SessionParams }>(
        '/api/chat/sessions/:id/config',
        async (
            request: FastifyRequest<{ Params: SessionParams }>,
            reply: FastifyReply
        ) => {
            const { id } = request.params;
            const config = request.body as Partial<SessionConfig>;

            if (!config || Object.keys(config).length === 0) {
                return reply.status(400).send({ error: 'Config is required' });
            }

            const updated = await sessionManager.updateSessionConfig(id, config);
            if (!updated) {
                return reply.status(404).send({ error: 'Session not found' });
            }

            return reply.send({ success: true });
        }
    );

    /**
     * POST /api/chat/sessions/:id/message - Aggiunge un messaggio alla sessione
     * (usato internamente dal WebSocket handler)
     */
    app.post<{ Params: SessionParams }>(
        '/api/chat/sessions/:id/message',
        async (
            request: FastifyRequest<{ Params: SessionParams }>,
            reply: FastifyReply
        ) => {
            const { id } = request.params;
            const { role, content } = request.body as { role: string; content: string };

            const turn: ChatTurn = {
                id: generateTurnId(),
                role: role as 'user' | 'assistant',
                content,
                timestamp: new Date().toISOString(),
            };

            await sessionManager.addTurn(id, turn);
            return reply.send({ success: true });
        }
    );

    // ── Turn Management Endpoints ────────────────────────────────────

    /**
     * DELETE /api/chat/sessions/:id/turns/:turnIndex - Cancella singolo turn
     * Se è un messaggio user, cancella anche la risposta assistant successiva.
     */
    app.delete<{ Params: TurnParams }>(
        '/api/chat/sessions/:id/turns/:turnIndex',
        async (
            request: FastifyRequest<{ Params: TurnParams }>,
            reply: FastifyReply
        ) => {
            const { id, turnIndex } = request.params;
            const idx = parseInt(turnIndex, 10);

            if (isNaN(idx) || idx < 0) {
                return reply.status(400).send({ error: 'Invalid turn index' });
            }

            const result = await sessionManager.deleteTurn(id, idx);
            if (result.deletedCount === 0) {
                return reply.status(404).send({ error: 'Turn not found' });
            }

            return reply.send({
                success: true,
                deletedCount: result.deletedCount,
                deletedResponse: result.isUserWithResponse,
            });
        }
    );

    /**
     * PUT /api/chat/sessions/:id/turns/:turnIndex/feedback
     * Upvote/downvote di una risposta assistant.
     */
    interface FeedbackBody {
        score: 1 | -1 | 0;
        comment?: string;
    }

    app.put<{ Params: TurnParams; Body: FeedbackBody }>(
        '/api/chat/sessions/:id/turns/:turnIndex/feedback',
        async (
            request: FastifyRequest<{ Params: TurnParams; Body: FeedbackBody }>,
            reply: FastifyReply
        ) => {
            const { id, turnIndex } = request.params;
            const idx = parseInt(turnIndex, 10);
            const { score, comment } = request.body;

            if (isNaN(idx) || idx < 0) {
                return reply.status(400).send({ error: 'Invalid turn index' });
            }

            if (score !== 1 && score !== -1 && score !== 0) {
                return reply.status(400).send({ error: 'Score must be 1, -1, or 0' });
            }

            const success = await sessionManager.updateTurnFeedback(id, idx, score, comment);
            if (!success) {
                return reply.status(404).send({ error: 'Turn not found' });
            }

            return reply.send({
                success: true,
                sessionId: id,
                turnIndex: idx,
                score,
            });
        }
    );

    /**
     * PUT /api/chat/sessions/:id/turns/:turnIndex - Modifica un turn e ri-esegui
     * 1. Aggiorna il contenuto del turn
     * 2. Tronca tutti i turn successivi
     * 3. Re-invia la query modificata come SSE stream
     */
    app.put<{ Params: TurnParams }>(
        '/api/chat/sessions/:id/turns/:turnIndex',
        async (
            request: FastifyRequest<{ Params: TurnParams }>,
            reply: FastifyReply
        ) => {
            const { id, turnIndex } = request.params;
            const { content } = request.body as { content: string };
            const idx = parseInt(turnIndex, 10);

            if (isNaN(idx) || idx < 0) {
                return reply.status(400).send({ error: 'Invalid turn index' });
            }

            if (!content || typeof content !== 'string') {
                return reply.status(400).send({ error: 'Content is required' });
            }

            // 1. Update the turn content
            const updated = await sessionManager.updateTurn(id, idx, content);
            if (!updated) {
                return reply.status(404).send({ error: 'Turn not found' });
            }

            // 2. Truncate everything after this turn (remove old response + subsequent turns)
            await sessionManager.truncateAfter(id, idx + 1);

            // 3. Re-execute the query via SSE stream
            // Note: don't re-add the user message — it's already updated in the store.
            // We stream directly without calling streamQueryToResponse which adds a new user turn.
            reply.raw.writeHead(200, {
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
                'Access-Control-Allow-Origin': '*',
            });

            reply.raw.write(`data: ${JSON.stringify({ type: 'session', session_id: id })}\n\n`);
            reply.raw.write(`data: ${JSON.stringify({ type: 'edit_applied', turnIndex: idx, content })}\n\n`);

            const heartbeatInterval = setInterval(() => {
                try { reply.raw.write(': heartbeat\n\n'); } catch { clearInterval(heartbeatInterval); }
            }, 15000);

            // FIX: Declare fullResponse outside try block to make it accessible in finally
            let fullResponse = '';

            try {
                const stream = me4brain.engine.queryStream(content, {
                    sessionId: id,
                    includeRawResults: true,
                });

                for await (const chunk of stream) {
                    if (chunk.type === 'content' && chunk.content) {
                        fullResponse += chunk.content;
                        reply.raw.write(`data: ${JSON.stringify({ type: 'content', content: chunk.content })}\n\n`);
                    } else if (chunk.type === 'done') {
                        if (fullResponse) {
                            const assistantTurn: ChatTurn = {
                                id: generateTurnId(),
                                role: 'assistant',
                                content: fullResponse,
                                timestamp: new Date().toISOString(),
                            };
                            await sessionManager.addTurn(id, assistantTurn);
                        }
                        reply.raw.write(`data: ${JSON.stringify({ type: 'done', tools_count: chunk.tools_count, latency_ms: chunk.total_latency_ms })}\n\n`);
                    } else if (chunk.type !== 'start') {
                        reply.raw.write(`data: ${JSON.stringify(chunk)}\n\n`);
                    }
                }

                clearInterval(heartbeatInterval);
            } catch (error) {
                clearInterval(heartbeatInterval);
                const errorMessage = error instanceof Error ? error.message : 'Unknown error';
                reply.raw.write(`data: ${JSON.stringify({ type: 'error', error: errorMessage })}\n\n`);
            } finally {
                // FIX: Save partial response if client disconnected mid-stream during edit
                if (fullResponse.trim()) {
                    try {
                        const partialTurn: ChatTurn = {
                            id: `turn-partial-${Date.now()}`,
                            role: 'assistant',
                            content: fullResponse,
                            timestamp: new Date().toISOString(),
                            isPartial: true,
                        };
                        await sessionManager.addTurn(id, partialTurn);
                        console.log(`[SSE-Edit] Saved partial response (${fullResponse.length} chars) for session ${id}`);
                    } catch (e) {
                        console.error(`[SSE-Edit] Failed to save partial response for session ${id}:`, e);
                    }
                }
                reply.raw.write('data: [DONE]\n\n');
                reply.raw.end();
            }
        }
    );

    /**
     * POST /api/chat/sessions/:id/retry/:turnIndex - Retry una query
     * 1. Legge il contenuto della query user al turnIndex
     * 2. Tronca tutto dal turnIndex in poi
     * 3. Re-invii la query come SSE stream
     */
    app.post<{ Params: TurnParams }>(
        '/api/chat/sessions/:id/retry/:turnIndex',
        async (
            request: FastifyRequest<{ Params: TurnParams }>,
            reply: FastifyReply
        ) => {
            const { id, turnIndex } = request.params;
            const idx = parseInt(turnIndex, 10);

            console.log(`[ChatRoute] Retry requested - Session: ${id}, Turn: ${idx}`);

            if (isNaN(idx) || idx < 0) {
                console.warn(`[ChatRoute] Invalid turn index: ${turnIndex}`);
                return reply.status(400).send({ error: 'Invalid turn index' });
            }

            // 1. Read the original query
            const queryContent = await sessionManager.getTurnContent(id, idx);
            if (!queryContent) {
                console.error(`[ChatRoute] Turn content not found for index ${idx} in session ${id}`);
                return reply.status(404).send({ error: 'Turn not found' });
            }

            console.log(`[ChatRoute] Found content for retry: "${queryContent.slice(0, 50)}..."`);

            // 2. Truncate from this turn onward (removes old Q&A)
            await sessionManager.truncateAfter(id, idx);

            // 3. Re-execute via SSE stream (this will re-add user + assistant turns)
            await streamQueryToResponse(me4brain, id, queryContent, reply);
        }
    );
}

// ── Exports for WebSocket handler ────────────────────────────────────

export async function getSession(sessionId: string) {
    return sessionManager.getSession(sessionId);
}

