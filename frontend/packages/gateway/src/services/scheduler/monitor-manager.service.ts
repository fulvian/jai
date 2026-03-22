/**
 * Monitor Manager Service - CRUD operations with Redis persistence
 * 
 * Gestisce la persistenza e le operazioni CRUD sui monitor proattivi.
 * Pattern SOTA 2026: Redis persistence, Zod validation, type safety.
 */

import { Monitor, CreateMonitorRequest, MonitorSchema } from '@persan/shared';
import { Redis } from 'ioredis';
import { v4 as uuidv4 } from 'uuid';
import { ConfigService } from '../../config/config.service.js';
import { schedulerService } from './scheduler.service.js';
import pino from 'pino';

const logger = pino({ name: 'monitor-manager' });

export class MonitorManager {
    private redis: Redis;

    constructor() {
        const redisUrl = ConfigService.getInstance().get('REDIS_URL');
        this.redis = new Redis(redisUrl);

        logger.info('MonitorManager initialized');
    }

    /**
     * Create a new monitor
     */
    async createMonitor(userId: string, request: CreateMonitorRequest): Promise<Monitor> {
        const monitor: Monitor = {
            id: uuidv4(),
            user_id: userId,
            type: request.type,
            name: request.name,
            description: request.description,
            config: request.config,
            state: 'ACTIVE',
            interval_minutes: request.interval_minutes,
            notify_channels: request.notify_channels,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            checks_count: 0,
            triggers_count: 0,
            history: [],
        };

        // Validate with Zod
        const validated = MonitorSchema.parse(monitor);

        // Store in Redis
        await this.redis.hset('monitors', monitor.id, JSON.stringify(validated));
        await this.redis.sadd(`monitors:user:${userId}`, monitor.id);

        // Schedule with BullMQ
        await schedulerService.scheduleMonitor(validated);

        logger.info(
            { monitorId: monitor.id, userId, type: monitor.type },
            'Monitor created'
        );

        return validated;
    }

    /**
     * Get a monitor by ID
     */
    async getMonitor(monitorId: string): Promise<Monitor | null> {
        const data = await this.redis.hget('monitors', monitorId);
        if (!data) {
            return null;
        }

        try {
            const parsed = JSON.parse(data);
            return MonitorSchema.parse(parsed);
        } catch (error) {
            logger.error({ monitorId, error }, 'Failed to parse monitor');
            return null;
        }
    }

    /**
     * List all monitors for a user
     */
    async listMonitors(userId: string): Promise<Monitor[]> {
        const monitorIds = await this.redis.smembers(`monitors:user:${userId}`);

        const monitors = await Promise.all(
            monitorIds.map((id: string) => this.getMonitor(id))
        );

        return monitors.filter((m: Monitor | null): m is Monitor => m !== null);
    }

    /**
     * Update a monitor
     */
    async updateMonitor(monitorId: string, updates: Partial<Monitor>): Promise<Monitor> {
        const monitor = await this.getMonitor(monitorId);
        if (!monitor) {
            throw new Error(`Monitor ${monitorId} not found`);
        }

        const updated = {
            ...monitor,
            ...updates,
            updated_at: new Date().toISOString(),
        };

        // Validate with Zod
        const validated = MonitorSchema.parse(updated);

        // Store in Redis
        await this.redis.hset('monitors', monitorId, JSON.stringify(validated));

        // Update in scheduler memory
        schedulerService.updateMonitor(validated);

        logger.info({ monitorId, updates: Object.keys(updates) }, 'Monitor updated');

        return validated;
    }

    /**
     * Delete a monitor
     */
    async deleteMonitor(monitorId: string): Promise<void> {
        const monitor = await this.getMonitor(monitorId);
        if (!monitor) {
            return;
        }

        // Remove from scheduler
        await schedulerService.deleteMonitor(monitorId);

        // Remove from Redis
        await this.redis.hdel('monitors', monitorId);
        await this.redis.srem(`monitors:user:${monitor.user_id}`, monitorId);

        logger.info({ monitorId, userId: monitor.user_id }, 'Monitor deleted');
    }

    /**
     * Pause a monitor
     */
    async pauseMonitor(monitorId: string): Promise<Monitor> {
        await schedulerService.pauseMonitor(monitorId);
        return await this.updateMonitor(monitorId, { state: 'PAUSED' });
    }

    /**
     * Resume a monitor
     */
    async resumeMonitor(monitorId: string): Promise<Monitor> {
        const monitor = await this.getMonitor(monitorId);
        if (!monitor) {
            throw new Error(`Monitor ${monitorId} not found`);
        }

        await schedulerService.resumeMonitor(monitorId);
        return await this.updateMonitor(monitorId, { state: 'ACTIVE' });
    }

    /**
     * Add evaluation result to monitor history
     */
    async addEvaluationResult(
        monitorId: string,
        result: {
            timestamp: string;
            trigger: boolean;
            decision?: any;
            data?: any;
            error?: string;
        }
    ): Promise<void> {
        const monitor = await this.getMonitor(monitorId);
        if (!monitor) {
            return;
        }

        // Add to history (keep last 50)
        monitor.history.unshift(result);
        if (monitor.history.length > 50) {
            monitor.history = monitor.history.slice(0, 50);
        }

        // Update counters
        monitor.checks_count += 1;
        if (result.trigger) {
            monitor.triggers_count += 1;
            monitor.state = 'TRIGGERED';
        }
        monitor.last_check = result.timestamp;

        // Calculate next check time
        const nextCheckDate = new Date(Date.now() + monitor.interval_minutes * 60 * 1000);
        monitor.next_check = nextCheckDate.toISOString();

        await this.updateMonitor(monitorId, {
            history: monitor.history,
            checks_count: monitor.checks_count,
            triggers_count: monitor.triggers_count,
            state: monitor.state,
            last_check: monitor.last_check,
            next_check: monitor.next_check,
        });

        logger.info(
            {
                monitorId,
                trigger: result.trigger,
                checksCount: monitor.checks_count,
                triggersCount: monitor.triggers_count,
            },
            'Evaluation result added'
        );
    }

    /**
     * Get statistics for all monitors
     */
    async getStats(userId?: string): Promise<{
        total: number;
        active: number;
        paused: number;
        triggered: number;
        byType: Record<string, number>;
    }> {
        const monitors = userId
            ? await this.listMonitors(userId)
            : await this.getAllMonitors();

        const stats = {
            total: monitors.length,
            active: monitors.filter((m) => m.state === 'ACTIVE').length,
            paused: monitors.filter((m) => m.state === 'PAUSED').length,
            triggered: monitors.filter((m) => m.state === 'TRIGGERED').length,
            byType: {} as Record<string, number>,
        };

        for (const monitor of monitors) {
            stats.byType[monitor.type] = (stats.byType[monitor.type] || 0) + 1;
        }

        return stats;
    }

    /**
     * Get all monitors (admin only)
     */
    private async getAllMonitors(): Promise<Monitor[]> {
        const allData = await this.redis.hgetall('monitors');
        const monitors: Monitor[] = [];

        for (const data of Object.values(allData) as string[]) {
            try {
                const parsed = JSON.parse(data);
                monitors.push(MonitorSchema.parse(parsed));
            } catch (error) {
                logger.error({ error }, 'Failed to parse monitor');
            }
        }

        return monitors;
    }

    /**
     * Close Redis connection
     */
    async close(): Promise<void> {
        await this.redis.quit();
        logger.info('MonitorManager closed');
    }
}

// Singleton instance
let monitorManagerInstance: MonitorManager | null = null;

export function getMonitorManager(): MonitorManager {
    if (!monitorManagerInstance) {
        monitorManagerInstance = new MonitorManager();
    }
    return monitorManagerInstance;
}

export const monitorManager = getMonitorManager();
