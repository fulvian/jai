/**
 * Query Executor
 * 
 * Gestisce l'elaborazione delle query Me4BrAIn in background.
 * Consuma lo stream e persiste i risultati in Redis per consentire la riconnessione.
 */

import { Me4BrAInClient } from '@persan/me4brain-client';
import { Redis } from 'ioredis';
import * as crypto from 'crypto';
import { connectionRegistry } from '../websocket/registry.js';
import { pushService } from './push_notifications.js';
import { sessionManager } from '../services/session_manager_instance.js';
import type { WSMessage } from '@persan/shared';

export class QueryExecutor {
    private me4brain: Me4BrAInClient;
    private redis: Redis | null = null;
    private redisAvailable = false;
    private bufferPrefix = 'persan:buffer:';
    private ttl = 3600; // 1 ora di persistenza per il buffer
    // FIX Issue #7: Track active sessions to prevent double-streaming
    private activeSessionRequests: Map<string, string> = new Map(); // sessionId → requestId
    // FIX Critical: Detect anomalous thinking/content patterns (backtick loops, etc.)
    private anomalyDetector = {
        thinkingPatterns: new Map<string, string[]>(), // sessionId → last N thinking chunks
        contentPatterns: new Map<string, string[]>(), // sessionId → last N content chunks
        windowSize: 10, // Track last 10 chunks
        anomalyThreshold: 8, // 8/10 similar = anomaly
    };

    constructor() {
        this.me4brain = new Me4BrAInClient({
            baseUrl: process.env.ME4BRAIN_URL ?? 'http://localhost:8000/v1',
        });
        this.initRedis();
    }

    private initRedis(): void {
        try {
            const url = process.env.REDIS_URL ?? 'redis://localhost:6379';
            const password = process.env.REDIS_PASSWORD || undefined;
            this.redis = new Redis(url, {
                password,
                maxRetriesPerRequest: 2,
                retryStrategy: (times: number) => {
                    if (times > 3) return null;
                    return Math.min(times * 200, 2000);
                },
                lazyConnect: true,
            });

            this.redis.on('connect', () => {
                this.redisAvailable = true;
                console.log('✅ [QueryExecutor] Redis connected');
            });

            this.redis.on('error', (err: Error) => {
                this.redisAvailable = false;
                console.warn('[QueryExecutor] Redis error:', err.message);
            });

            this.redis.on('close', () => {
                this.redisAvailable = false;
            });

            this.redis.connect().catch(() => {
                this.redisAvailable = false;
                console.warn('⚠️ [QueryExecutor] Redis unavailable, buffer/replay disabled');
            });
        } catch (error) {
            this.redisAvailable = false;
            console.warn('⚠️ [QueryExecutor] Redis init failed, buffer/replay disabled');
        }
    }

    /**
     * Avvia una query in background per una sessione.
     */
    async execute(sessionId: string, query: string, requestId: string, userId: string = 'default'): Promise<void> {
        // FIX Issue #5: Buffer key includes requestId to prevent overwrite on concurrent queries
        const bufferKey = `${this.bufferPrefix}${sessionId}:${requestId}`;

        // FIX Issue #7: Check if session already has an active request
        const existingRequestId = this.activeSessionRequests.get(sessionId);
        if (existingRequestId) {
            console.warn(`[QueryExecutor] ⚠️ Session ${sessionId} already processing request ${existingRequestId}. New request ${requestId} will proceed, old buffer preserved.`);
        }
        this.activeSessionRequests.set(sessionId, requestId);

        // Avvia il consumo dello stream in modo asincrono (background)
        this.runBackgroundTask(sessionId, query, requestId, userId, bufferKey).catch((err) => {
            console.error(`[QueryExecutor] Error in background task for session ${sessionId}:`, err);
        });
    }

    /**
     * Detect anomalous patterns in LLM thinking/content generation.
     * Returns true if an anomaly is detected (e.g., backtick loops, repetitive thinking).
     */
    private detectAnomaly(sessionId: string, type: 'thinking' | 'content', currentContent: string): boolean {
        const map = type === 'thinking' ? this.anomalyDetector.thinkingPatterns : this.anomalyDetector.contentPatterns;
        
        if (!map.has(sessionId)) {
            map.set(sessionId, []);
        }
        
        const history = map.get(sessionId)!;
        history.push(currentContent);
        
        // Keep only last N chunks
        if (history.length > this.anomalyDetector.windowSize) {
            history.shift();
        }
        
        // Check for anomalies
        if (history.length >= this.anomalyDetector.windowSize) {
            // Detect backtick loops (alternating ` and `)
            const backtickCount = history.filter(c => c.includes('`')).length;
            if (backtickCount >= this.anomalyDetector.anomalyThreshold) {
                console.warn(`[QueryExecutor] 🚨 ANOMALY DETECTED: Backtick loop in ${type} for session ${sessionId}`);
                return true;
            }
            
            // Detect repetitive content (same thing repeated)
            const uniqueChunks = new Set(history);
            if (uniqueChunks.size <= 2 && history.length >= this.anomalyDetector.windowSize) {
                console.warn(`[QueryExecutor] 🚨 ANOMALY DETECTED: Repetitive ${type} for session ${sessionId}`);
                return true;
            }
        }
        
        return false;
    }

    private async runBackgroundTask(
        sessionId: string,
        query: string,
        requestId: string,
        userId: string,
        bufferKey: string
    ): Promise<void> {
        console.log(`[QueryExecutor] Starting background query for session ${sessionId}`);
        let fullResponse = '';
        let toolsUsed: string[] = []; // FIX F2: Accumulate tool names
        let attempts = 0;
        const maxAttempts = 2; // Riprova una volta in caso di fallimento immediato

        // 0. Invia thinking indicator immediato
        const thinkingMsg: WSMessage = {
            type: 'chat:response',
            data: { type: 'thinking', content: 'Sto pensando...', session_id: sessionId },
            timestamp: Date.now(),
            requestId: requestId,
        };
        if (this.redisAvailable && this.redis) {
            try {
                await this.redis.rpush(bufferKey, JSON.stringify(thinkingMsg));
            } catch { /* non-critical */ }
        }
        connectionRegistry.sendToSession(sessionId, thinkingMsg);

        while (attempts < maxAttempts) {
            try {
                attempts++;
                if (attempts > 1) {
                    console.log(`[QueryExecutor] Retrying query (attempt ${attempts}/${maxAttempts}) for session ${sessionId}`);
                }

                const stream = this.me4brain.engine.queryStream(query, {
                    sessionId,
                    includeRawResults: true
                });

                for await (const chunk of stream) {
                    // 🔵 DIAGNOSTIC: Log received chunk
                    console.log(`[QueryExecutor] 🔵 Received chunk from Me4Brain:`, {
                        type: chunk.type,
                        hasContent: !!chunk.content,
                        hasTool: !!chunk.tool,
                        sessionId,
                        timestamp: new Date().toISOString()
                    });

                    // 🚨 CRITICAL FIX: Detect anomalous patterns (backtick loops, infinite thinking)
                    if (chunk.type === 'thinking' && chunk.content) {
                        if (this.detectAnomaly(sessionId, 'thinking', chunk.content)) {
                            console.error(`[QueryExecutor] 🔴 Aborting stream due to anomalous thinking pattern`);
                            throw new Error('LLM thinking process detected infinite loop - aborting');
                        }
                    }
                    if (chunk.type === 'content' && chunk.content) {
                        if (this.detectAnomaly(sessionId, 'content', chunk.content)) {
                            console.error(`[QueryExecutor] 🔴 Aborting stream due to anomalous content pattern`);
                            throw new Error('LLM content generation detected infinite loop - aborting');
                        }
                    }

                    const message: WSMessage = {
                        type: this.mapChunkType(chunk.type),
                        data: this.mapChunkData(chunk, sessionId, requestId),
                        timestamp: Date.now(),
                        requestId: requestId,
                    };

                    // 🔵 DIAGNOSTIC: Log mapped message
                    console.log(`[QueryExecutor] 🔄 Mapped to WSMessage:`, {
                        type: message.type,
                        dataKeys: Object.keys(message.data || {}),
                        sessionId
                    });

                    // 1. Salva nel buffer Redis (graceful degradation)
                    if (this.redisAvailable && this.redis) {
                        try {
                            await this.redis.rpush(bufferKey, JSON.stringify(message));
                            await this.redis.expire(bufferKey, this.ttl);
                        } catch { /* non-critical */ }
                    }

                    // 2. Invia al WebSocket specifico della SESSIONE
                    // DEBUG: Log message size to debug 524-character limit
                    const msgString = JSON.stringify(message);
                    const messageData = (message.data as any) || {};
                    console.log(`[QueryExecutor] 📤 Sending ${message.type} to session ${sessionId}`, {
                        msgSize: msgString.length,
                        contentSize: (messageData.content?.length || 0),
                        contentPreview: (messageData.content || '').substring(0, 50)
                    });
                    const sent = connectionRegistry.sendToSession(sessionId, message);
                    console.log(`[QueryExecutor] ${sent ? '✅ Delivered' : '❌ FAILED to deliver'} (type: ${message.type})`);

                    // Accumulate content
                    if (chunk.type === 'content' && chunk.content) {
                        fullResponse += chunk.content;
                    }

                    // FIX F2: Accumulate tool names from tool events
                    if ((chunk.type === 'step_complete' || chunk.type === 'tool' || (chunk as any).type === 'tool_complete')) {
                        const toolName = chunk.tool || chunk.tool_call?.tool;
                        if (toolName && !toolsUsed.includes(toolName)) {
                            toolsUsed.push(toolName);
                        }
                    }
                    // Also handle tools_called array from done event
                    if (chunk.type === 'done' && chunk.tools_called) {
                        for (const tool of chunk.tools_called) {
                            if (!toolsUsed.includes(tool)) {
                                toolsUsed.push(tool);
                            }
                        }
                    }

                    // 3. Se completato, salva turno e invia notifica push
                    if (chunk.type === 'done') {
                        // Persist Assistant Response
                        if (fullResponse) {
                            try {
                                await sessionManager.addTurn(sessionId, {
                                    id: crypto.randomUUID(),
                                    role: 'assistant',
                                    content: fullResponse,
                                    timestamp: new Date().toISOString(),
                                    toolsUsed: toolsUsed.length > 0 ? toolsUsed : undefined, // FIX F2: Include tools used
                                });
                            } catch (e) {
                                console.error(`[QueryExecutor] Failed to persist assistant turn:`, e);
                            }
                        }

                        await pushService.sendNotification(userId, {
                            title: 'Risposta jAI pronta!',
                            body: 'L\'elaborazione della tua richiesta è stata completata.',
                            data: { sessionId }
                        });

                        // Uscita con successo
                        // FIX Issue #7: Clean up active session tracking
                        this.activeSessionRequests.delete(sessionId);
                        // Clean up anomaly detector
                        this.anomalyDetector.thinkingPatterns.delete(sessionId);
                        this.anomalyDetector.contentPatterns.delete(sessionId);
                        return;
                    }

                    // Se riceviamo un errore esplicito dallo stream, non riprovare, gestiscilo
                    if (chunk.type === 'error') {
                        throw new Error(chunk.error || chunk.message || 'Errore restituito dal motore di ragionamento');
                    }
                }

                // Se lo stream finisce senza 'done', consideralo un errore o un break
                break;

            } catch (error: any) {
                console.error(`[QueryExecutor] Attempt ${attempts} failed:`, error);

                // Se abbiamo superato i tentativi, gestisci l'errore finale
                if (attempts >= maxAttempts) {
                    const errorMessage = error instanceof Error ? error.message : String(error);
                    const errorMsg: WSMessage = {
                        type: 'error',
                        data: {
                            message: `Errore persistente dopo ${attempts} tentativi: ${errorMessage}`,
                            code: 'BACKGROUND_ERROR',
                            session_id: sessionId
                        },
                        timestamp: Date.now(),
                        requestId: requestId,
                    };
                    if (this.redisAvailable && this.redis) {
                        try {
                            await this.redis.rpush(bufferKey, JSON.stringify(errorMsg));
                        } catch { /* non-critical */ }
                    }
                    connectionRegistry.sendToSession(sessionId, errorMsg);
                    // Clean up anomaly detector
                    this.anomalyDetector.thinkingPatterns.delete(sessionId);
                    this.anomalyDetector.contentPatterns.delete(sessionId);
                } else {
                    // Attendi un momento prima del prossimo tentativo
                    await new Promise(resolve => setTimeout(resolve, 1000));
                }
            }
        }
        // FIX Issue #7: Clean up on all-attempts-failed
        this.activeSessionRequests.delete(sessionId);
        // Clean up anomaly detector
        this.anomalyDetector.thinkingPatterns.delete(sessionId);
        this.anomalyDetector.contentPatterns.delete(sessionId);
    }

    /**
     * Recupera i messaggi bufferizzati per una sessione (replay dopo riconnessione).
     */
    async getBuffer(sessionId: string, requestId?: string): Promise<WSMessage[]> {
        if (!this.redisAvailable || !this.redis) {
            return [];
        }
        try {
            // FIX Issue #5: If requestId provided, use specific key; otherwise scan for latest
            const bufferKey = requestId
                ? `${this.bufferPrefix}${sessionId}:${requestId}`
                : `${this.bufferPrefix}${sessionId}:*`;

            if (requestId) {
                const rawItems = await this.redis.lrange(bufferKey, 0, -1);
                return rawItems.map(item => JSON.parse(item));
            } else {
                // Scan for all buffers of this session and return the most recent one
                const keys = await this.redis.keys(`${this.bufferPrefix}${sessionId}:*`);
                if (keys.length === 0) return [];
                // Use the last key (most recent by convention)
                const lastKey = keys.sort().pop()!;
                const rawItems = await this.redis.lrange(lastKey, 0, -1);
                return rawItems.map(item => JSON.parse(item));
            }
        } catch (error) {
            console.warn('[QueryExecutor] Failed to get buffer:', (error as Error).message);
            return [];
        }
    }

    private mapChunkType(type: string): any {
        // Mappiamo quasi tutto a chat:response per unificare il parsing lato client
        // mantenendo il field 'type' all'interno dei dati del chunk.
        switch (type) {
            case 'content':
            case 'thinking':
            case 'plan':
            case 'step_start':
            case 'step_thinking':
            case 'step_complete':
            case 'step_error':
            case 'synthesizing':
            case 'sources':
            case 'done':
                return 'chat:response';
            case 'status':
                return 'chat:status';
            case 'tool':
                return 'chat:tool';
            case 'error':
                return 'error';
            default:
                return 'chat:response';
        }
    }

    private mapChunkData(chunk: any, sessionId: string, requestId: string): any {
        // Assicuriamoci che il requestId e sessionId siano sempre presenti per il client
        // FIX: Usare session_id (snake_case) per coerenza con backend Python e Frontend
        const base = { ...chunk, requestId, session_id: sessionId };

        if (chunk.type === 'content') {
            return { ...base, isStreaming: true };
        }
        if (chunk.type === 'done') {
            // FIX F2: Include tools_called in done message
            return {
                ...base,
                isStreaming: false,
                done: true,
                latencyMs: chunk.latency_ms || chunk.total_latency_ms || (chunk as any).latencyMs,
                toolsCalled: chunk.tools_called || [],
            };
        }

        return base;
    }

    /**
     * Verifica se una sessione ha un task attivo in background.
     */
    isSessionActive(sessionId: string): boolean {
        return this.activeSessionRequests.has(sessionId);
    }

    /**
     * Restituisce lo stato di attività per una lista di sessioni.
     */
    getSessionStatuses(sessionIds: string[]): Record<string, boolean> {
        const statuses: Record<string, boolean> = {};
        for (const id of sessionIds) {
            statuses[id] = this.activeSessionRequests.has(id);
        }
        return statuses;
    }

}

export const queryExecutor = new QueryExecutor();
