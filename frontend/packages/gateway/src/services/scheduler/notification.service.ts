/**
 * Notification Service
 * 
 * Sends monitor alerts to users via WebSocket and maintains notification history in Redis.
 * Integrates with existing ConnectionRegistry for WebSocket delivery.
 */

import { Redis } from 'ioredis';
import { connectionRegistry } from '../../websocket/registry.js';
import type { MonitorAlertData } from '@persan/shared';
import pino from 'pino';

const logger = pino({ name: 'notification-service' });

export interface MonitorAlert {
    monitorId: string;
    monitorName: string;
    monitorType: string;
    trigger: boolean;
    decision: {
        recommendation: string;
        confidence: number;
        reasoning: string;
        key_factors?: string[];
    };
    data: Record<string, unknown>;
    timestamp: string;
}

export class NotificationService {
    private redis: Redis;

    constructor(redis: Redis) {
        this.redis = redis;
    }

    /**
     * Send monitor alert to user via WebSocket
     */
    async sendMonitorAlert(userId: string, alert: MonitorAlert): Promise<void> {
        logger.info({ userId, monitorId: alert.monitorId, monitorType: alert.monitorType }, 'Sending monitor alert');

        // Convert to WebSocket message format
        const alertData: MonitorAlertData = {
            monitorId: alert.monitorId,
            monitorName: alert.monitorName,
            monitorType: alert.monitorType,
            message: alert.decision.reasoning,
            severity: this.getSeverity(alert.decision.confidence),
            timestamp: alert.timestamp,
            data: alert.data,
        };

        // Send via WebSocket
        const sent = connectionRegistry.sendMonitorAlert(userId, alertData);

        if (sent === 0) {
            logger.warn({ userId, monitorId: alert.monitorId }, 'No active WebSocket connections for user');
        } else {
            logger.info({ userId, monitorId: alert.monitorId, connectionsSent: sent }, 'Alert sent via WebSocket');
        }

        // Store in Redis history
        await this.storeNotification(userId, alert);
    }

    /**
     * Store notification in Redis history (last 50 per user)
     */
    private async storeNotification(userId: string, alert: MonitorAlert): Promise<void> {
        const key = `notifications:user:${userId}`;
        const alertJson = JSON.stringify(alert);

        try {
            // Add to list (newest first)
            await this.redis.lpush(key, alertJson);
            // Keep only last 50
            await this.redis.ltrim(key, 0, 49);

            logger.debug({ userId, monitorId: alert.monitorId }, 'Notification stored in Redis');
        } catch (error) {
            logger.error({ userId, monitorId: alert.monitorId, error }, 'Failed to store notification in Redis');
        }
    }

    /**
     * Get notification history for user (last N notifications)
     */
    async getNotificationHistory(userId: string, limit: number = 50): Promise<MonitorAlert[]> {
        const key = `notifications:user:${userId}`;

        try {
            const notifications = await this.redis.lrange(key, 0, limit - 1);
            return notifications.map(json => JSON.parse(json) as MonitorAlert);
        } catch (error) {
            logger.error({ userId, error }, 'Failed to get notification history from Redis');
            return [];
        }
    }

    /**
     * Replay missed notifications on reconnect
     */
    async replayNotifications(userId: string, since?: Date): Promise<void> {
        logger.info({ userId, since }, 'Replaying notifications');

        const history = await this.getNotificationHistory(userId, 50);

        // Filter by timestamp if provided
        const notifications = since
            ? history.filter(alert => new Date(alert.timestamp) > since)
            : history;

        if (notifications.length === 0) {
            logger.debug({ userId }, 'No notifications to replay');
            return;
        }

        // Send each notification via WebSocket
        for (const alert of notifications) {
            const alertData: MonitorAlertData = {
                monitorId: alert.monitorId,
                monitorName: alert.monitorName,
                monitorType: alert.monitorType,
                message: alert.decision.reasoning,
                severity: this.getSeverity(alert.decision.confidence),
                timestamp: alert.timestamp,
                data: alert.data,
            };

            connectionRegistry.sendMonitorAlert(userId, alertData);
        }

        logger.info({ userId, count: notifications.length }, 'Notifications replayed');
    }

    /**
     * Determine severity based on confidence level
     */
    private getSeverity(confidence: number): 'info' | 'warning' | 'critical' {
        if (confidence >= 80) return 'critical';
        if (confidence >= 60) return 'warning';
        return 'info';
    }
}
