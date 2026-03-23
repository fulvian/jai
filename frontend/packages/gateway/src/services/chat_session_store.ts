/**
 * ChatSessionStore - Persistenza sessioni chat su Redis
 *
 * Schema Redis:
 *   persan:chat:{id}         → JSON { title, created_at, updated_at }
 *   persan:chat:{id}:turns   → Redis List di JSON ChatTurn
 *   persan:chat:index        → Sorted Set (score = updated_at epoch)
 *
 * Fallback: Map in-memory se Redis non è disponibile.
 */

import { Redis } from 'ioredis';
import type { SessionConfig } from '@persan/shared';

import { generateSessionTitleWithFallback } from './title_generator.js';

// ── Types ────────────────────────────────────────────────────────────

export interface ChatTurn {
    id: string;
    role: 'user' | 'assistant';
    content: string;
    timestamp: string;
    toolsUsed?: string[]; // FIX F2: Track which tools were used
    feedback?: {
        score: 1 | -1;
        comment?: string;
        timestamp: string;
    };
}

export interface ChatSession {
    session_id: string;
    title: string;
    created_at: string;
    updated_at: string;
    turns: ChatTurn[];
    config?: SessionConfig;
}

interface SessionMeta {
    title: string;
    created_at: string;
    updated_at: string;
    config?: SessionConfig;
}

// ── Store ────────────────────────────────────────────────────────────

const PREFIX = 'persan:chat:';
const INDEX_KEY = 'persan:chat:index';

export class ChatSessionStore {
    private redis: Redis | null = null;
    private redisAvailable = false;
    private memoryStore = new Map<string, ChatSession>();

    constructor() {
        this.initRedis();
    }

    // ── Redis connection ─────────────────────────────────────────────

    private initRedis(): void {
        const redisUrl = process.env.REDIS_URL ?? 'redis://localhost:6389';
        const redisPassword = process.env.REDIS_PASSWORD;

        const opts: Record<string, unknown> = {
            maxRetriesPerRequest: 2,
            retryStrategy: (times: number) => {
                if (times > 3) return null; // stop retrying
                return Math.min(times * 200, 2000);
            },
            lazyConnect: true,
        };

        if (redisPassword) opts.password = redisPassword;

        this.redis = new Redis(redisUrl, opts);

        this.redis.on('connect', () => {
            this.redisAvailable = true;
            console.log('✅ ChatSessionStore: Redis connected');
        });

        this.redis.on('error', (err: Error) => {
            if (err.message.includes('NOAUTH') || err.message.includes('WRONGPASS')) {
                this.redisAvailable = false;
                console.warn('⚠️ ChatSessionStore: Redis auth error, using memory fallback');
            }
        });

        this.redis.on('close', () => {
            this.redisAvailable = false;
        });

        // Attempt connection
        this.redis.connect().catch(() => {
            this.redisAvailable = false;
            console.warn('⚠️ ChatSessionStore: Redis unavailable, using memory fallback');
        });
    }

    // ── Session CRUD ─────────────────────────────────────────────────

    async createSession(id: string, title: string, config?: SessionConfig): Promise<ChatSession> {
        const now = new Date().toISOString();
        const session: ChatSession = {
            session_id: id,
            title,
            created_at: now,
            updated_at: now,
            turns: [],
            config,
        };

        if (this.redisAvailable && this.redis) {
            try {
                const meta: SessionMeta = { title, created_at: now, updated_at: now, config };
                await this.redis
                    .pipeline()
                    .set(`${PREFIX}${id}`, JSON.stringify(meta))
                    .zadd(INDEX_KEY, Date.now(), id)
                    .exec();
            } catch {
                this.memoryStore.set(id, session);
            }
        } else {
            this.memoryStore.set(id, session);
        }

        return session;
    }

    async getSession(id: string): Promise<ChatSession | null> {
        if (this.redisAvailable && this.redis) {
            try {
                const [metaJson, turnsJson] = await Promise.all([
                    this.redis.get(`${PREFIX}${id}`),
                    this.redis.lrange(`${PREFIX}${id}:turns`, 0, -1),
                ]);
                if (!metaJson) return null;

                const meta: SessionMeta = JSON.parse(metaJson);
                const turns: ChatTurn[] = turnsJson.map((t) => JSON.parse(t));

                return {
                    session_id: id,
                    title: meta.title,
                    created_at: meta.created_at,
                    updated_at: meta.updated_at,
                    turns,
                    config: meta.config,
                };
            } catch {
                // fallthrough to memory
            }
        }

        return this.memoryStore.get(id) ?? null;
    }

    async listSessions(limit = 50): Promise<Omit<ChatSession, 'turns'>[]> {
        if (this.redisAvailable && this.redis) {
            try {
                // Get most recent session IDs from sorted set
                const ids = await this.redis.zrevrange(INDEX_KEY, 0, limit - 1);
                if (ids.length === 0) return [];

                // Batch-fetch metadata
                const pipeline = this.redis.pipeline();
                for (const id of ids) {
                    pipeline.get(`${PREFIX}${id}`);
                    pipeline.llen(`${PREFIX}${id}:turns`);
                }
                const results = await pipeline.exec();
                if (!results) return [];

                const sessions: (Omit<ChatSession, 'turns'> & { message_count: number })[] = [];
                for (let i = 0; i < ids.length; i++) {
                    const metaJson = results[i * 2]?.[1] as string | null;
                    const turnCount = results[i * 2 + 1]?.[1] as number;
                    if (!metaJson) continue;

                    const meta: SessionMeta = JSON.parse(metaJson);
                    sessions.push({
                        session_id: ids[i],
                        title: meta.title,
                        created_at: meta.created_at,
                        updated_at: meta.updated_at,
                        message_count: turnCount ?? 0,
                        config: meta.config,
                    });
                }
                return sessions;
            } catch {
                // fallthrough to memory
            }
        }

        // Memory fallback
        return Array.from(this.memoryStore.values())
            .map(({ turns, ...rest }) => ({ ...rest, message_count: turns.length }))
            .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
            .slice(0, limit);
    }

    async deleteSession(id: string): Promise<boolean> {
        if (this.redisAvailable && this.redis) {
            try {
                await this.redis
                    .pipeline()
                    .del(`${PREFIX}${id}`)
                    .del(`${PREFIX}${id}:turns`)
                    .zrem(INDEX_KEY, id)
                    .exec();
                return true;
            } catch {
                // fallthrough
            }
        }

        return this.memoryStore.delete(id);
    }

    async updateTitle(id: string, title: string): Promise<boolean> {
        if (this.redisAvailable && this.redis) {
            try {
                const metaJson = await this.redis.get(`${PREFIX}${id}`);
                if (!metaJson) return false;

                const meta: SessionMeta = JSON.parse(metaJson);
                meta.title = title;
                meta.updated_at = new Date().toISOString();

                await this.redis
                    .pipeline()
                    .set(`${PREFIX}${id}`, JSON.stringify(meta))
                    .zadd(INDEX_KEY, Date.now(), id)
                    .exec();
                return true;
            } catch {
                // fallthrough
            }
        }

        const session = this.memoryStore.get(id);
        if (!session) return false;
        session.title = title;
        session.updated_at = new Date().toISOString();
        return true;
    }

    async updateSessionConfig(id: string, config: Partial<SessionConfig>): Promise<boolean> {
        if (this.redisAvailable && this.redis) {
            try {
                const metaJson = await this.redis.get(`${PREFIX}${id}`);
                if (!metaJson) return false;

                const meta: SessionMeta = JSON.parse(metaJson);
                meta.config = { ...(meta.config ?? { type: 'free' }), ...config } as SessionConfig;
                meta.updated_at = new Date().toISOString();

                await this.redis
                    .pipeline()
                    .set(`${PREFIX}${id}`, JSON.stringify(meta))
                    .zadd(INDEX_KEY, Date.now(), id)
                    .exec();
                return true;
            } catch {
                // fallthrough
            }
        }

        const session = this.memoryStore.get(id);
        if (!session) return false;
        session.config = { ...(session.config ?? { type: 'free' }), ...config } as SessionConfig;
        session.updated_at = new Date().toISOString();
        return true;
    }


    async addTurn(sessionId: string, turn: ChatTurn): Promise<void> {
        const now = new Date().toISOString();

        if (this.redisAvailable && this.redis) {
            try {
                // Auto-create session if not exists
                const exists = await this.redis.exists(`${PREFIX}${sessionId}`);
                if (!exists) {
                    // Try LLM title generation, fallback to truncation
                    const title = turn.role === 'user'
                        ? await generateSessionTitleWithFallback(turn.content).catch(() =>
                              turn.content.slice(0, 50) + (turn.content.length > 50 ? '...' : ''),
                          )
                        : 'Nuova conversazione';
                    const meta: SessionMeta = { title, created_at: now, updated_at: now };
                    await this.redis.set(`${PREFIX}${sessionId}`, JSON.stringify(meta));
                }

                await this.redis
                    .pipeline()
                    .rpush(`${PREFIX}${sessionId}:turns`, JSON.stringify(turn))
                    .zadd(INDEX_KEY, Date.now(), sessionId)
                    .exec();

                // Update meta timestamp
                const metaJson = await this.redis.get(`${PREFIX}${sessionId}`);
                if (metaJson) {
                    const meta: SessionMeta = JSON.parse(metaJson);
                    meta.updated_at = now;
                    // Auto-title from first user message using LLM
                    if (turn.role === 'user') {
                        const turnCount = await this.redis.llen(`${PREFIX}${sessionId}:turns`);
                        if (turnCount === 1) {
                            meta.title = await generateSessionTitleWithFallback(turn.content).catch(() =>
                                turn.content.slice(0, 50) + (turn.content.length > 50 ? '...' : ''),
                            );
                        }
                    }
                    await this.redis.set(`${PREFIX}${sessionId}`, JSON.stringify(meta));
                }

                // Fire-and-forget: indicizza nel Session Knowledge Graph dopo turn assistant
                if (turn.role === 'assistant') {
                    this.triggerGraphIngestion(sessionId).catch(() => { });
                }

                return;
            } catch {
                // fallthrough
            }
        }

        // Memory fallback
        let session = this.memoryStore.get(sessionId);
        if (!session) {
            session = {
                session_id: sessionId,
                title: turn.role === 'user'
                    ? await generateSessionTitleWithFallback(turn.content).catch(() =>
                          turn.content.slice(0, 50) + (turn.content.length > 50 ? '...' : ''),
                      )
                    : 'Nuova conversazione',
                created_at: now,
                updated_at: now,
                turns: [],
            };
            this.memoryStore.set(sessionId, session);
        }
        session.turns.push(turn);
        session.updated_at = now;
        if (session.turns.length === 1 && turn.role === 'user') {
            session.title = await generateSessionTitleWithFallback(turn.content).catch(() =>
                turn.content.slice(0, 50) + (turn.content.length > 50 ? '...' : ''),
            );
        }

        // Fire-and-forget graph ingestion for memory fallback too
        if (turn.role === 'assistant') {
            this.triggerGraphIngestion(sessionId).catch(() => { });
        }
    }

    /**
     * Invia sessione al Session Knowledge Graph di Me4Brain.
     * Fire-and-forget: errori non bloccano il flusso principale.
     */
    private async triggerGraphIngestion(sessionId: string): Promise<void> {
        try {
            const { graphSessionService } = await import('./graph_session_service.js');
            const session = await this.getSession(sessionId);
            if (!session || !session.turns.length) return;

            await graphSessionService.ingestSession(
                sessionId,
                session.title,
                session.turns.map((t) => ({
                    role: t.role,
                    content: t.content,
                    timestamp: t.timestamp,
                })),
                session.created_at,
                session.updated_at,
            );
        } catch (error) {
            // Silenzioso: il grafo è opzionale, non deve impattare il flusso principale
            console.warn('[ChatSessionStore] Graph ingestion failed (non-critical):', (error as Error).message);
        }
    }

    async deleteTurn(sessionId: string, turnIndex: number): Promise<{ deletedCount: number; isUserWithResponse: boolean }> {
        if (this.redisAvailable && this.redis) {
            try {
                const turnsJson = await this.redis.lrange(`${PREFIX}${sessionId}:turns`, 0, -1);
                if (turnIndex < 0 || turnIndex >= turnsJson.length) {
                    return { deletedCount: 0, isUserWithResponse: false };
                }

                const turn: ChatTurn = JSON.parse(turnsJson[turnIndex]);
                const nextTurn: ChatTurn | null = turnIndex + 1 < turnsJson.length
                    ? JSON.parse(turnsJson[turnIndex + 1])
                    : null;
                const isUserWithResponse = turn.role === 'user' && nextTurn?.role === 'assistant';

                // Build new list without deleted turn(s)
                const newTurns = [...turnsJson];
                if (isUserWithResponse) {
                    // Delete user message + its assistant response
                    newTurns.splice(turnIndex, 2);
                } else {
                    newTurns.splice(turnIndex, 1);
                }

                // Replace the list atomically
                const pipeline = this.redis.pipeline();
                pipeline.del(`${PREFIX}${sessionId}:turns`);
                if (newTurns.length > 0) {
                    pipeline.rpush(`${PREFIX}${sessionId}:turns`, ...newTurns);
                }
                pipeline.zadd(INDEX_KEY, Date.now(), sessionId);
                await pipeline.exec();

                return {
                    deletedCount: isUserWithResponse ? 2 : 1,
                    isUserWithResponse,
                };
            } catch {
                // fallthrough
            }
        }

        // Memory fallback
        const session = this.memoryStore.get(sessionId);
        if (!session || turnIndex < 0 || turnIndex >= session.turns.length) {
            return { deletedCount: 0, isUserWithResponse: false };
        }

        const turn = session.turns[turnIndex];
        const nextTurn = turnIndex + 1 < session.turns.length ? session.turns[turnIndex + 1] : null;
        const isUserWithResponse = turn.role === 'user' && nextTurn?.role === 'assistant';

        if (isUserWithResponse) {
            session.turns.splice(turnIndex, 2);
        } else {
            session.turns.splice(turnIndex, 1);
        }
        session.updated_at = new Date().toISOString();

        return {
            deletedCount: isUserWithResponse ? 2 : 1,
            isUserWithResponse,
        };
    }

    async updateTurn(sessionId: string, turnIndex: number, newContent: string): Promise<boolean> {
        if (this.redisAvailable && this.redis) {
            try {
                const turnsJson = await this.redis.lrange(`${PREFIX}${sessionId}:turns`, 0, -1);
                if (turnIndex < 0 || turnIndex >= turnsJson.length) return false;

                const turn: ChatTurn = JSON.parse(turnsJson[turnIndex]);
                turn.content = newContent;
                turn.timestamp = new Date().toISOString();

                await this.redis.lset(`${PREFIX}${sessionId}:turns`, turnIndex, JSON.stringify(turn));
                return true;
            } catch {
                // fallthrough
            }
        }

        const session = this.memoryStore.get(sessionId);
        if (!session || turnIndex < 0 || turnIndex >= session.turns.length) return false;

        session.turns[turnIndex].content = newContent;
        session.turns[turnIndex].timestamp = new Date().toISOString();
        return true;
    }

    async updateTurnFeedback(
        sessionId: string,
        turnIndex: number,
        score: 1 | -1 | 0,
        comment?: string,
    ): Promise<boolean> {
        if (this.redisAvailable && this.redis) {
            try {
                const turnJson = await this.redis.lindex(`${PREFIX}${sessionId}:turns`, turnIndex);
                if (!turnJson) return false;

                const turn: ChatTurn = JSON.parse(turnJson);

                if (score === 0) {
                    // Toggle off — remove feedback
                    delete turn.feedback;
                } else {
                    turn.feedback = {
                        score,
                        comment: comment || undefined,
                        timestamp: new Date().toISOString(),
                    };
                }

                await this.redis.lset(`${PREFIX}${sessionId}:turns`, turnIndex, JSON.stringify(turn));
                return true;
            } catch {
                // fallthrough
            }
        }

        const session = this.memoryStore.get(sessionId);
        if (!session || turnIndex < 0 || turnIndex >= session.turns.length) return false;

        if (score === 0) {
            delete session.turns[turnIndex].feedback;
        } else {
            session.turns[turnIndex].feedback = {
                score,
                comment: comment || undefined,
                timestamp: new Date().toISOString(),
            };
        }
        return true;
    }

    async truncateAfter(sessionId: string, turnIndex: number): Promise<number> {
        if (this.redisAvailable && this.redis) {
            try {
                const totalLen = await this.redis.llen(`${PREFIX}${sessionId}:turns`);
                if (turnIndex < 0 || turnIndex >= totalLen) return 0;

                const removed = totalLen - turnIndex;
                // LTRIM keeps elements from 0 to turnIndex-1
                await this.redis.ltrim(`${PREFIX}${sessionId}:turns`, 0, turnIndex - 1);
                return removed;
            } catch {
                // fallthrough
            }
        }

        const session = this.memoryStore.get(sessionId);
        if (!session || turnIndex < 0 || turnIndex >= session.turns.length) return 0;

        const removed = session.turns.length - turnIndex;
        session.turns.splice(turnIndex);
        session.updated_at = new Date().toISOString();
        return removed;
    }

    async getTurnContent(sessionId: string, turnIndex: number): Promise<string | null> {
        if (this.redisAvailable && this.redis) {
            try {
                const turnJson = await this.redis.lindex(`${PREFIX}${sessionId}:turns`, turnIndex);
                if (!turnJson) return null;
                const turn: ChatTurn = JSON.parse(turnJson);
                return turn.content;
            } catch {
                // fallthrough
            }
        }

        const session = this.memoryStore.get(sessionId);
        if (!session || turnIndex < 0 || turnIndex >= session.turns.length) return null;
        return session.turns[turnIndex].content;
    }

    // ── Lifecycle ────────────────────────────────────────────────────

    async close(): Promise<void> {
        if (this.redis) {
            await this.redis.quit();
            this.redis = null;
            this.redisAvailable = false;
        }
    }
}

// Singleton instance
export const chatSessionStore = new ChatSessionStore();
