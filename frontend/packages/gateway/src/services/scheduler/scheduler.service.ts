/**
 * Scheduler Service - BullMQ-based job scheduling
 * 
 * Gestisce lo scheduling distribuito dei monitor proattivi usando BullMQ e Redis.
 * Pattern SOTA 2026: Redis-native, TypeScript-first, retry/concurrency controls.
 */

import { Queue, Worker, QueueEvents, Job } from 'bullmq';
import { Redis } from 'ioredis';
import { Monitor } from '@persan/shared';
import { ConfigService } from '../../config/config.service.js';
import pino from 'pino';

const logger = pino({ name: 'scheduler-service' });

interface MonitorJobData {
    monitorId: string;
    userId: string;
}

export class SchedulerService {
    private queue: Queue<MonitorJobData>;
    private worker: Worker<MonitorJobData>;
    private queueEvents: QueueEvents;
    private connection: Redis;
    private monitors: Map<string, Monitor> = new Map();
    private isShuttingDown = false;

    constructor() {
        const redisUrl = ConfigService.getInstance().get('REDIS_URL');
        this.connection = new Redis(redisUrl, {
            maxRetriesPerRequest: null, // Required for BullMQ
            enableReadyCheck: false,
        });

        // Create queue with default job options
        this.queue = new Queue<MonitorJobData>('monitors', {
            connection: this.connection,
            defaultJobOptions: {
                removeOnComplete: 100, // Keep last 100 completed jobs
                removeOnFail: 500, // Keep last 500 failed jobs
                attempts: 3, // Retry up to 3 times
                backoff: {
                    type: 'exponential',
                    delay: 2000, // Start with 2s delay
                },
            },
        });

        // Create worker with concurrency control
        this.worker = new Worker<MonitorJobData>(
            'monitors',
            async (job: Job<MonitorJobData>) => {
                return await this.evaluateMonitor(job.data.monitorId);
            },
            {
                connection: this.connection,
                concurrency: 10, // Process up to 10 jobs concurrently
                limiter: {
                    max: 100, // Max 100 jobs
                    duration: 60000, // per minute
                },
            }
        );

        // Queue events for monitoring
        this.queueEvents = new QueueEvents('monitors', {
            connection: this.connection,
        });

        this.setupEventListeners();

        logger.info('SchedulerService initialized');
    }

    private setupEventListeners(): void {
        // Worker events
        this.worker.on('completed', (job: Job<MonitorJobData>) => {
            logger.info(
                {
                    jobId: job.id,
                    monitorId: job.data.monitorId,
                    duration: Date.now() - job.processedOn!,
                },
                'Monitor evaluation completed'
            );
        });

        this.worker.on('failed', (job: Job<MonitorJobData> | undefined, err: Error) => {
            logger.error(
                {
                    jobId: job?.id,
                    monitorId: job?.data.monitorId,
                    error: err.message,
                    attempts: job?.attemptsMade,
                },
                'Monitor evaluation failed'
            );
        });

        this.worker.on('stalled', (jobId: string) => {
            logger.warn({ jobId }, 'Job stalled');
        });

        // Queue events
        this.queueEvents.on('waiting', ({ jobId }) => {
            logger.debug({ jobId }, 'Job waiting');
        });

        this.queueEvents.on('active', ({ jobId }) => {
            logger.debug({ jobId }, 'Job active');
        });
    }

    /**
     * Schedule a monitor for periodic evaluation
     */
    async scheduleMonitor(monitor: Monitor): Promise<void> {
        if (this.isShuttingDown) {
            throw new Error('Scheduler is shutting down');
        }

        // Store monitor in memory
        this.monitors.set(monitor.id, monitor);

        // Determine schedule type
        if (monitor.type === 'SCHEDULED') {
            // Use cron expression from config
            const cronExpr = (monitor.config as any).cron_expression || '*/5 * * * *';
            await this.queue.add(
                'evaluate',
                {
                    monitorId: monitor.id,
                    userId: monitor.user_id,
                },
                {
                    repeat: {
                        pattern: cronExpr,
                    },
                    jobId: monitor.id, // Use monitor ID as job ID for idempotency
                }
            );

            logger.info(
                { monitorId: monitor.id, type: monitor.type, cron: cronExpr },
                'Monitor scheduled with cron'
            );
        } else {
            // Interval-based for all other types
            const intervalMs = monitor.interval_minutes * 60 * 1000;
            await this.queue.add(
                'evaluate',
                {
                    monitorId: monitor.id,
                    userId: monitor.user_id,
                },
                {
                    repeat: {
                        every: intervalMs,
                    },
                    jobId: monitor.id,
                }
            );

            logger.info(
                {
                    monitorId: monitor.id,
                    type: monitor.type,
                    intervalMinutes: monitor.interval_minutes,
                },
                'Monitor scheduled with interval'
            );
        }
    }

    /**
     * Pause a monitor (remove from queue but keep in memory)
     */
    async pauseMonitor(monitorId: string): Promise<void> {
        const job = await this.queue.getJob(monitorId);
        if (job) {
            await job.remove();
            logger.info({ monitorId }, 'Monitor paused');
        }

        const monitor = this.monitors.get(monitorId);
        if (monitor) {
            monitor.state = 'PAUSED';
        }
    }

    /**
     * Resume a paused monitor
     */
    async resumeMonitor(monitorId: string): Promise<void> {
        const monitor = this.monitors.get(monitorId);
        if (!monitor) {
            throw new Error(`Monitor ${monitorId} not found`);
        }

        monitor.state = 'ACTIVE';
        await this.scheduleMonitor(monitor);

        logger.info({ monitorId }, 'Monitor resumed');
    }

    /**
     * Delete a monitor (remove from queue and memory)
     */
    async deleteMonitor(monitorId: string): Promise<void> {
        const job = await this.queue.getJob(monitorId);
        if (job) {
            await job.remove();
        }

        this.monitors.delete(monitorId);

        logger.info({ monitorId }, 'Monitor deleted');
    }

    /**
     * Trigger immediate evaluation of a monitor
     */
    async triggerImmediate(monitorId: string): Promise<void> {
        const monitor = this.monitors.get(monitorId);
        if (!monitor) {
            throw new Error(`Monitor ${monitorId} not found`);
        }

        await this.queue.add(
            'evaluate',
            {
                monitorId: monitor.id,
                userId: monitor.user_id,
            },
            {
                priority: 1, // High priority for immediate execution
            }
        );

        logger.info({ monitorId }, 'Monitor triggered immediately');
    }

    /**
     * Get monitor from memory
     */
    getMonitor(monitorId: string): Monitor | undefined {
        return this.monitors.get(monitorId);
    }

    /**
     * Update monitor in memory
     */
    updateMonitor(monitor: Monitor): void {
        this.monitors.set(monitor.id, monitor);
    }

    /**
     * Get queue statistics
     */
    async getStats(): Promise<{
        waiting: number;
        active: number;
        completed: number;
        failed: number;
        delayed: number;
    }> {
        const [waiting, active, completed, failed, delayed] = await Promise.all([
            this.queue.getWaitingCount(),
            this.queue.getActiveCount(),
            this.queue.getCompletedCount(),
            this.queue.getFailedCount(),
            this.queue.getDelayedCount(),
        ]);

        return { waiting, active, completed, failed, delayed };
    }

    /**
     * Evaluate a monitor (delegated to EvaluatorService)
     */
    private async evaluateMonitor(monitorId: string): Promise<any> {
        // Import dynamically to avoid circular dependency
        const { evaluatorService } = await import('./evaluator.service.js');
        return await evaluatorService.evaluate(monitorId);
    }

    /**
     * Graceful shutdown
     */
    async close(): Promise<void> {
        this.isShuttingDown = true;

        logger.info('Shutting down SchedulerService...');

        await this.worker.close();
        await this.queue.close();
        await this.queueEvents.close();
        await this.connection.quit();

        logger.info('SchedulerService shut down');
    }
}

// Singleton instance
let schedulerServiceInstance: SchedulerService | null = null;

export function getSchedulerService(): SchedulerService {
    if (!schedulerServiceInstance) {
        schedulerServiceInstance = new SchedulerService();
    }
    return schedulerServiceInstance;
}

export const schedulerService = getSchedulerService();
