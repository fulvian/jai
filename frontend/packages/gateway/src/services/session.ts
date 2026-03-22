/**
 * Session Manager
 * 
 * Gestisce sessioni utente con Redis per persistenza.
 */

import { Redis } from 'ioredis';
import { z } from 'zod';

const SessionSchema = z.object({
    id: z.string(),
    userId: z.string().optional(),
    channel: z.enum(['webchat', 'telegram', 'whatsapp']),
    state: z.enum(['idle', 'processing', 'error']),
    context: z.record(z.unknown()),
    createdAt: z.number(),
    lastActivity: z.number(),
});

export type Session = z.infer<typeof SessionSchema>;
export type Channel = Session['channel'];
export type SessionState = Session['state'];

export class SessionManager {
    private redis: Redis | null = null;
    private redisDisabled = false;
    private memoryStore = new Map<string, string>();
    private prefix = 'persan:session:';
    private ttl = 86400; // 24 hours

    private async getRedis(): Promise<Redis | null> {
        if (this.redisDisabled) return null;
        if (!this.redis) {
            const redisUrl = process.env.REDIS_URL ?? 'redis://localhost:6379';
            const redisPassword = process.env.REDIS_PASSWORD;

            // Build Redis options with password support
            const redisOptions: Record<string, unknown> = {
                maxRetriesPerRequest: 1,
                retryStrategy: (times: number) => {
                    if (times > 1) {
                        this.redisDisabled = true;
                        return null;
                    }
                    return 100;
                },
            };

            // Add password if provided via env var
            if (redisPassword) {
                redisOptions.password = redisPassword;
            }

            this.redis = new Redis(redisUrl, redisOptions);

            this.redis.on('error', (err: Error) => {
                if (err.message.includes('NOAUTH')) {
                    this.redisDisabled = true;
                    console.warn('⚠️ Redis Auth Error (NOAUTH). Set REDIS_PASSWORD env var. Using memory fallback.');
                } else if (err.message.includes('WRONGPASS')) {
                    this.redisDisabled = true;
                    console.warn('⚠️ Redis Wrong Password. Check REDIS_PASSWORD env var. Using memory fallback.');
                } else {
                    console.error('Redis connection error:', err.message);
                }
            });

            this.redis.on('connect', () => {
                console.log('✅ Redis connected successfully');
            });
        }
        return this.redis;
    }

    async create(channel: Channel, id?: string): Promise<Session> {
        const session: Session = {
            id: id ?? crypto.randomUUID(),
            channel,
            state: 'idle',
            context: {},
            createdAt: Date.now(),
            lastActivity: Date.now(),
        };

        try {
            const redis = await this.getRedis();
            if (redis && !this.redisDisabled) {
                await redis.setex(
                    `${this.prefix}${session.id}`,
                    this.ttl,
                    JSON.stringify(session)
                );
            } else {
                this.memoryStore.set(`${this.prefix}${session.id}`, JSON.stringify(session));
            }
        } catch (error) {
            this.memoryStore.set(`${this.prefix}${session.id}`, JSON.stringify(session));
            console.warn('Redis unavailable, session not persisted:', error instanceof Error ? error.message : error);
        }

        return session;
    }

    async get(id: string): Promise<Session | null> {
        try {
            let data: string | null = null;
            const redis = await this.getRedis();
            if (redis && !this.redisDisabled) {
                data = await redis.get(`${this.prefix}${id}`);
            } else {
                data = this.memoryStore.get(`${this.prefix}${id}`) ?? null;
            }

            if (!data) return null;
            return SessionSchema.parse(JSON.parse(data));
        } catch {
            return this.memoryStore.has(`${this.prefix}${id}`)
                ? SessionSchema.parse(JSON.parse(this.memoryStore.get(`${this.prefix}${id}`)!))
                : null;
        }
    }

    async update(id: string, patch: Partial<Session>): Promise<void> {
        try {
            const session = await this.get(id);
            if (!session) return;

            const updated: Session = {
                ...session,
                ...patch,
                lastActivity: Date.now(),
            };

            const redis = await this.getRedis();
            if (redis && !this.redisDisabled) {
                await redis.setex(
                    `${this.prefix}${id}`,
                    this.ttl,
                    JSON.stringify(updated)
                );
            } else {
                this.memoryStore.set(`${this.prefix}${id}`, JSON.stringify(updated));
            }
        } catch (error) {
            console.warn('Failed to update session:', error);
        }
    }

    async remove(id: string): Promise<void> {
        try {
            const redis = await this.getRedis();
            if (redis && !this.redisDisabled) {
                await redis.del(`${this.prefix}${id}`);
            } else {
                this.memoryStore.delete(`${this.prefix}${id}`);
            }
        } catch {
            // Ignore errors
        }
    }

    async close(): Promise<void> {
        if (this.redis) {
            await this.redis.quit();
            this.redis = null;
        }
    }
}
