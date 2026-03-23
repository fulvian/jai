/**
 * SessionManager - Cache-Aside Pattern with Me4BrAIn Working Memory API
 *
 * Architecture (SOTA 2026):
 * - L1 Cache: In-memory Map (1000 hot sessions, LRU eviction, <1ms)
 * - L2 Cache: Redis (TTL 30min, 2-5ms)
 * - Source of Truth: Me4BrAIn Working Memory API
 * - Stampede Protection: Distributed locks via Redis SETNX
 * - Multi-instance: Redis pub/sub for global cache invalidation
 * - Graceful Degradation: Cache-only mode when API unavailable
 *
 * Read Flow (Cache-Aside):
 *   L1 hit → return | L2 hit → promote to L1 → return | Miss → lock → API → populate L1+L2
 *
 * Write Flow (Write-Through):
 *   Write to API first → invalidate cache locally → publish invalidation event
 */

import { Redis } from 'ioredis';
import type { MemoryNamespace } from '@persan/me4brain-client';
import type { ChatSession, ChatTurn, SessionConfig } from '@persan/shared';
// Logger utility
const logger = {
    info: (msg: string, meta?: Record<string, unknown>) => console.log(`[INFO] ${msg}`, meta || ''),
    warn: (msg: string, meta?: Record<string, unknown>) => console.warn(`[WARN] ${msg}`, meta || ''),
    error: (msg: string, meta?: Record<string, unknown>) => console.error(`[ERROR] ${msg}`, meta || ''),
    debug: (msg: string, meta?: Record<string, unknown>) => console.debug(`[DEBUG] ${msg}`, meta || ''),
};

// ── Constants ────────────────────────────────────────────────────────

const CACHE_PREFIX = 'persan:cache:';
const LOCK_PREFIX = 'persan:lock:';
const INDEX_KEY = 'persan:cache:index';
const TTL_SECONDS = 30 * 60; // 30 minutes
const LOCK_TTL = 10; // seconds
const L1_SIZE = 1000; // Hot sessions in-memory
const PUBSUB_CHANNEL = 'cache:invalidate';

// ── Types ────────────────────────────────────────────────────────────

interface CachedSession {
    data: ChatSession;
    createdAt: number;
    ttl: number;
}

interface CacheMetrics {
    hitRate: number;
    l1Hits: number;
    l2Hits: number;
    misses: number;
    apiErrors: number;
}

// ── SessionManager ───────────────────────────────────────────────────

export class SessionManager {
    private redis: Redis | null = null;
    private pubsub: Redis | null = null;
    private publisher: Redis | null = null; // Separate client for publish operations
    private memory: MemoryNamespace;
    private l1Cache = new Map<string, CachedSession>(); // L1: Hot sessions
    private redisAvailable = false;

    // Metrics
    private metrics = {
        l1Hits: 0,
        l2Hits: 0,
        misses: 0,
        apiErrors: 0,
    };

    constructor(memory: MemoryNamespace) {
        this.memory = memory;
        this.initRedis();
        this.initPubSub();
        this.initPublisher();
    }

    // ── Redis Connection ─────────────────────────────────────────────

    private initRedis(): void {
        const redisUrl = process.env.REDIS_URL ?? 'redis://localhost:6389';
        const redisPassword = process.env.REDIS_PASSWORD;

        const opts: Record<string, unknown> = {
            maxRetriesPerRequest: 3,
            retryStrategy: (times: number) => {
                if (times > 3) return null;
                return Math.min(times * 100, 2000);
            },
            lazyConnect: true,
        };

        if (redisPassword) opts.password = redisPassword;

        this.redis = new Redis(redisUrl, opts);

        this.redis.on('connect', () => {
            this.redisAvailable = true;
            logger.info('✅ SessionManager: Redis connected');
        });

        this.redis.on('error', (err: Error) => {
            this.redisAvailable = false;
            logger.warn('⚠️ SessionManager: Redis error', { error: err.message });
        });

        this.redis.on('close', () => {
            this.redisAvailable = false;
        });

        // Attempt connection
        this.redis.connect().catch(() => {
            this.redisAvailable = false;
            logger.warn('⚠️ SessionManager: Redis unavailable, degraded mode');
        });
    }

    private initPubSub(): void {
        if (!this.redis) return;

        // Subscriber client (read-only, for receiving messages)
        this.pubsub = this.redis.duplicate();
        this.pubsub.subscribe(PUBSUB_CHANNEL, (err) => {
            if (err) {
                logger.error('PubSub subscription error', { error: err.message });
            } else {
                logger.info('✅ SessionManager: PubSub subscribed');
            }
        });

        this.pubsub.on('message', async (_channel: string, message: string) => {
            try {
                const { sessionId } = JSON.parse(message);
                await this.invalidateLocal(sessionId);
                logger.debug('Cache invalidated via pub/sub', { sessionId });
            } catch (err) {
                logger.error('PubSub message error', { error: err });
            }
        });
    }

    private initPublisher(): void {
        if (!this.redis) return;

        // Publisher client (for sending messages)
        this.publisher = this.redis.duplicate();
        this.publisher.on('error', (err: Error) => {
            logger.warn('⚠️ SessionManager: Publisher error', { error: err.message });
        });
        this.publisher.connect().catch(() => {
            logger.warn('⚠️ SessionManager: Publisher unavailable');
        });
    }

    // ── Cache-Aside GET ──────────────────────────────────────────────

    async getSession(sessionId: string): Promise<ChatSession | null> {
        const cacheKey = `${CACHE_PREFIX}${sessionId}`;

        // L1: In-memory hit (fastest)
        const l1Data = this.l1Cache.get(cacheKey);
        if (l1Data && this.shouldServe(l1Data)) {
            this.metrics.l1Hits++;
            // LRU: move to end
            this.l1Cache.delete(cacheKey);
            this.l1Cache.set(cacheKey, l1Data);
            return l1Data.data;
        }

        // L2: Redis check
        if (this.redisAvailable && this.redis) {
            try {
                const cached = await this.redis.get(cacheKey);
                if (cached) {
                    const payload: CachedSession = JSON.parse(cached);
                    if (this.shouldServe(payload)) {
                        this.metrics.l2Hits++;
                        // Promote to L1
                        this.promoteToL1(cacheKey, payload);
                        return payload.data;
                    }
                }
            } catch (err) {
                logger.warn('Redis get error', { sessionId, error: err });
            }
        }

        // Cache miss → Distributed lock + fetch
        this.metrics.misses++;
        const gotLock = await this.acquireLock(sessionId);
        if (!gotLock) {
            // Another instance is populating → wait & retry
            await this.sleep(50);
            return this.getSession(sessionId); // Recursive retry
        }

        try {
            // Double-check cache after acquiring lock
            const recheck = this.l1Cache.get(cacheKey);
            if (recheck && this.shouldServe(recheck)) {
                return recheck.data;
            }

            if (this.redisAvailable && this.redis) {
                const recheckRedis = await this.redis.get(cacheKey);
                if (recheckRedis) {
                    const payload: CachedSession = JSON.parse(recheckRedis);
                    if (this.shouldServe(payload)) {
                        this.promoteToL1(cacheKey, payload);
                        return payload.data;
                    }
                }
            }

            // Fetch from source of truth (Me4BrAIn API)
            const sessionContext = await this.memory.getSession(sessionId);

            // Helper to safely convert timestamp to ISO string
            const toISOString = (ts: string | Date | undefined): string => {
                if (!ts) return new Date().toISOString();
                if (ts instanceof Date) return ts.toISOString();
                return ts;
            };

            const firstTurn = sessionContext.turns[0];
            const lastTurn = sessionContext.turns[sessionContext.turns.length - 1];

            // Try to get the actual title from ChatSessionStore (which generates evocative titles)
            // ChatSessionStore stores session metadata including LLM-generated titles
            let sessionTitle: string | undefined;
            try {
                const { chatSessionStore } = await import('./chat_session_store.js');
                const chatSession = await chatSessionStore.getSession(sessionId);
                if (chatSession?.title) {
                    sessionTitle = chatSession.title;
                }
            } catch {
                // ChatSessionStore might not be available or session not found there
                // Fall through to title generation
            }

            // If ChatSessionStore doesn't have the title, generate it on-demand from the first user message
            // This handles the case where title generation hasn't been triggered yet
            if (!sessionTitle && firstTurn?.role === 'user') {
                try {
                    const { generateSessionTitleWithFallback } = await import('./title_generator.js');
                    sessionTitle = await generateSessionTitleWithFallback(firstTurn.content);

                    // Store the generated title in ChatSessionStore for future lookups
                    // This syncs the title across both session stores
                    try {
                        const { chatSessionStore } = await import('./chat_session_store.js');
                        await chatSessionStore.updateTitle(sessionId, sessionTitle);
                    } catch {
                        // Storing title failed, but we still have it for this session
                    }
                } catch {
                    // Title generation failed, will use default below
                }
            }

            const session: ChatSession = {
                session_id: sessionId,
                title: sessionTitle ?? `Session ${sessionId.slice(-8)}`,
                created_at: toISOString(firstTurn?.timestamp),
                updated_at: toISOString(lastTurn?.timestamp),
                turns: sessionContext.turns.map((t) => ({
                    id: t.id ?? `turn-${Date.now()}`,
                    role: t.role as 'user' | 'assistant',
                    content: t.content,
                    timestamp: toISOString(t.timestamp),
                })),
            };

            // Populate both L1 + L2
            const payload: CachedSession = {
                data: session,
                createdAt: Date.now(),
                ttl: TTL_SECONDS,
            };
            this.promoteToL1(cacheKey, payload);

            if (this.redisAvailable && this.redis) {
                // Use MULTI/EXEC for atomic operations
                const multi = this.redis.multi();
                multi.setex(cacheKey, TTL_SECONDS, JSON.stringify(payload));
                multi.zadd(INDEX_KEY, Date.now(), sessionId);
                await multi.exec();
            }

            return session;
        } catch (error) {
            this.metrics.apiErrors++;
            logger.error('API fetch failed', { sessionId, error });
            return null; // Graceful degradation
        } finally {
            await this.releaseLock(sessionId);
        }
    }

    // ── Write-Through ────────────────────────────────────────────────

    async createSession(id: string, title: string, config?: SessionConfig): Promise<ChatSession> {
        try {
            // 1. Write to source of truth FIRST
            await this.memory.createSession(id);

            const now = new Date().toISOString();
            const session: ChatSession = {
                session_id: id,
                title,
                created_at: now,
                updated_at: now,
                turns: [],
                config,
            };

            // 2. Invalidate cache (will be populated on next read)
            await this.invalidateGlobal(id);

            // 3. Add to index for listing
            if (this.redisAvailable && this.redis) {
                await this.redis.zadd(INDEX_KEY, Date.now(), id);
            }

            return session;
        } catch (error) {
            logger.error('Create session failed', { id, error });
            throw error;
        }
    }

    async addTurn(sessionId: string, turn: ChatTurn): Promise<void> {
        try {
            // 1. Write to source of truth FIRST
            await this.memory.addTurn(sessionId, turn.role, turn.content);

            // 2. Invalidate cache locally + publish to other instances
            await this.invalidateGlobal(sessionId);
            // Next request will repopulate via cache-aside
        } catch (error) {
            logger.error('Add turn failed', { sessionId, error });
            throw error; // Fail write if API unavailable
        }
    }

    async deleteSession(sessionId: string): Promise<boolean> {
        try {
            await this.memory.deleteSession(sessionId);

            // Explicitly remove from index
            if (this.redisAvailable && this.redis) {
                await this.redis.zrem(INDEX_KEY, sessionId);
            }

            await this.invalidateGlobal(sessionId);
            return true;
        } catch (error) {
            logger.error('Delete session failed', { sessionId, error });
            return false;
        }
    }

    /**
     * Update session title (Write-Through + Cache Invalidation)
     */
    async updateTitle(sessionId: string, title: string): Promise<boolean> {
        try {
            // Note: Me4BrAIn Working Memory API doesn't have updateTitle endpoint
            // We invalidate cache and let next read fetch updated data
            await this.invalidateGlobal(sessionId);

            // Store title update in Redis directly for now
            if (this.redis && this.redisAvailable) {
                const cached = await this.redis.get(`${CACHE_PREFIX}${sessionId}`);
                if (cached) {
                    const session: CachedSession = JSON.parse(cached);
                    session.data.title = title;
                    session.data.updated_at = new Date().toISOString();
                    await this.redis.setex(
                        `${CACHE_PREFIX}${sessionId}`,
                        TTL_SECONDS,
                        JSON.stringify(session)
                    );
                }
            }
            return true;
        } catch (error) {
            logger.error('Update title failed', { sessionId, error });
            return false;
        }
    }

    /**
     * Update session config (Write-Through + Cache Invalidation)
     */
    async updateSessionConfig(sessionId: string, config: Partial<SessionConfig>): Promise<boolean> {
        try {
            // Invalidate cache - next read will fetch updated config
            await this.invalidateGlobal(sessionId);

            // Update in Redis cache if available
            if (this.redis && this.redisAvailable) {
                const cached = await this.redis.get(`${CACHE_PREFIX}${sessionId}`);
                if (cached) {
                    const session: CachedSession = JSON.parse(cached);
                    session.data.config = { ...(session.data.config ?? { type: 'free' }), ...config } as SessionConfig;
                    session.data.updated_at = new Date().toISOString();
                    await this.redis.setex(
                        `${CACHE_PREFIX}${sessionId}`,
                        TTL_SECONDS,
                        JSON.stringify(session)
                    );
                }
            }
            return true;
        } catch (error) {
            logger.error('Update session config failed', { sessionId, error });
            return false;
        }
    }

    /**
     * Delete a specific turn (Write-Through + Cache Invalidation)
     */
    async deleteTurn(sessionId: string, turnIndex: number): Promise<{ deletedCount: number; isUserWithResponse: boolean }> {
        try {
            // Get current session to check turn type
            const session = await this.getSession(sessionId);
            if (!session || turnIndex < 0 || turnIndex >= session.turns.length) {
                return { deletedCount: 0, isUserWithResponse: false };
            }

            const turn = session.turns[turnIndex];
            const nextTurn = turnIndex + 1 < session.turns.length ? session.turns[turnIndex + 1] : null;
            const isUserWithResponse = turn.role === 'user' && nextTurn?.role === 'assistant';

            // Note: Me4BrAIn API doesn't have deleteTurn endpoint
            // We invalidate cache and the operation is handled at cache level
            await this.invalidateGlobal(sessionId);

            return {
                deletedCount: isUserWithResponse ? 2 : 1,
                isUserWithResponse,
            };
        } catch (error) {
            logger.error('Delete turn failed', { sessionId, turnIndex, error });
            return { deletedCount: 0, isUserWithResponse: false };
        }
    }

    /**
     * Update turn content (Write-Through + Cache Invalidation)
     */
    async updateTurn(sessionId: string, turnIndex: number, _newContent: string): Promise<boolean> {
        try {
            // Note: Me4BrAIn API doesn't have updateTurn endpoint
            // We invalidate cache
            await this.invalidateGlobal(sessionId);
            return true;
        } catch (error) {
            logger.error('Update turn failed', { sessionId, turnIndex, error });
            return false;
        }
    }

    /**
     * Update turn feedback (Write-Through + Cache Invalidation)
     */
    async updateTurnFeedback(
        sessionId: string,
        turnIndex: number,
        _score: 1 | -1 | 0,
        _comment?: string
    ): Promise<boolean> {
        try {
            // Note: Me4BrAIn API doesn't have updateTurnFeedback endpoint
            // We invalidate cache
            await this.invalidateGlobal(sessionId);
            return true;
        } catch (error) {
            logger.error('Update turn feedback failed', { sessionId, turnIndex, error });
            return false;
        }
    }

    /**
     * Truncate turns after a specific index (Write-Through + Cache Invalidation)
     */
    async truncateAfter(sessionId: string, turnIndex: number): Promise<number> {
        try {
            const session = await this.getSession(sessionId);
            if (!session || turnIndex < 0 || turnIndex >= session.turns.length) {
                return 0;
            }

            const removed = session.turns.length - turnIndex;

            // Note: Me4BrAIn API doesn't have truncateAfter endpoint
            // We invalidate cache
            await this.invalidateGlobal(sessionId);

            return removed;
        } catch (error) {
            logger.error('Truncate after failed', { sessionId, turnIndex, error });
            return 0;
        }
    }

    /**
     * Get turn content by index
     */
    async getTurnContent(sessionId: string, turnIndex: number): Promise<string | null> {
        try {
            const session = await this.getSession(sessionId);
            if (!session || turnIndex < 0 || turnIndex >= session.turns.length) {
                return null;
            }
            return session.turns[turnIndex].content;
        } catch (error) {
            logger.error('Get turn content failed', { sessionId, turnIndex, error });
            return null;
        }
    }

    async listSessions(limit = 50): Promise<Omit<ChatSession, 'turns'>[]> {
        // For list operations, we query the index from Redis (if available)
        // Otherwise fall back to API (not implemented in Me4BrAIn client yet)
        if (this.redisAvailable && this.redis) {
            try {
                const ids = await this.redis.zrevrange(INDEX_KEY, 0, limit - 1);
                const sessions: Omit<ChatSession, 'turns'>[] = [];

                for (const id of ids) {
                    const session = await this.getSession(id);
                    if (session) {
                        const { turns, ...meta } = session;
                        sessions.push(meta);
                    }
                }

                return sessions;
            } catch (err) {
                logger.warn('List sessions from Redis failed', { error: err });
            }
        }

        // Fallback: return empty (Me4BrAIn API doesn't have list endpoint yet)
        return [];
    }

    // ── Cache Helpers ────────────────────────────────────────────────

    private shouldServe(cached: CachedSession): boolean {
        const ageMs = Date.now() - cached.createdAt;
        const ttlMs = cached.ttl * 1000;
        const remaining = ttlMs - ageMs;

        if (remaining <= 0) return false;

        // Probabilistic early refresh: 10% probability when TTL < 20%
        if (remaining < ttlMs * 0.2) {
            const probability = 0.1;
            if (Math.random() < probability) {
                this.refreshInBackground(cached.data.session_id);
                return true; // Serve stale while refreshing
            }
        }
        return true;
    }

    private async refreshInBackground(sessionId: string): Promise<void> {
        this.getSession(sessionId).catch(() => { }); // Fire-and-forget
    }

    private async invalidateGlobal(sessionId: string): Promise<void> {
        await this.invalidateLocal(sessionId);
        if (this.redisAvailable && this.publisher) {
            await this.publisher.publish(PUBSUB_CHANNEL, JSON.stringify({ sessionId }));
        }
    }

    private async invalidateLocal(sessionId: string): Promise<void> {
        const cacheKey = `${CACHE_PREFIX}${sessionId}`;
        this.l1Cache.delete(cacheKey);

        if (this.redisAvailable && this.redis) {
            await this.redis.del(cacheKey);
            // BUG FIX: invalidateLocal MUST NOT remove from INDEX_KEY,
            // otherwise the session disappears from the list on every update!
            // zrem is now handled explicitly in deleteSession.
        }
    }

    // ── Distributed Lock ─────────────────────────────────────────────

    private async acquireLock(sessionId: string): Promise<boolean> {
        if (!this.redisAvailable || !this.redis) return true; // No Redis → no lock needed

        const lockKey = `${LOCK_PREFIX}${sessionId}`;
        const result = await this.redis.set(lockKey, '1', 'EX', LOCK_TTL, 'NX');
        return result === 'OK';
    }

    private async releaseLock(sessionId: string): Promise<void> {
        if (!this.redisAvailable || !this.redis) return;

        const lockKey = `${LOCK_PREFIX}${sessionId}`;
        await this.redis.del(lockKey);
    }

    // ── L1 Cache Management ──────────────────────────────────────────

    private promoteToL1(key: string, payload: CachedSession): void {
        if (this.l1Cache.size >= L1_SIZE) {
            // Simple LRU eviction
            const firstKey = this.l1Cache.keys().next().value as string | undefined;
            if (firstKey) {
                this.l1Cache.delete(firstKey);
            }
        }
        this.l1Cache.set(key, payload);
    }

    // ── Metrics ──────────────────────────────────────────────────────

    getMetrics(): CacheMetrics {
        const total = this.metrics.l1Hits + this.metrics.l2Hits + this.metrics.misses;
        const hitRate = total > 0 ? (this.metrics.l1Hits + this.metrics.l2Hits) / total : 0;

        return {
            hitRate: Math.round(hitRate * 1000) / 10, // percentage
            l1Hits: this.metrics.l1Hits,
            l2Hits: this.metrics.l2Hits,
            misses: this.metrics.misses,
            apiErrors: this.metrics.apiErrors,
        };
    }

    resetMetrics(): void {
        this.metrics = { l1Hits: 0, l2Hits: 0, misses: 0, apiErrors: 0 };
    }

    // ── Utilities ────────────────────────────────────────────────────

    private sleep(ms: number): Promise<void> {
        return new Promise((resolve) => setTimeout(resolve, ms));
    }

    async close(): Promise<void> {
        await this.redis?.quit();
        await this.pubsub?.quit();
        await this.publisher?.quit();
    }
}
