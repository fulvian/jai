/**
 * Notification Service Instance
 * 
 * Singleton instance initialized with Redis connection.
 */

import { Redis } from 'ioredis';
import { ConfigService } from '../../config/config.service.js';
import { NotificationService } from './notification.service.js';

let notificationServiceInstance: NotificationService | null = null;

export function initializeNotificationService(): NotificationService {
    if (!notificationServiceInstance) {
        const redisUrl = ConfigService.getInstance().get('REDIS_URL');
        const redis = new Redis(redisUrl);
        notificationServiceInstance = new NotificationService(redis);
    }
    return notificationServiceInstance;
}

export function getNotificationService(): NotificationService {
    if (!notificationServiceInstance) {
        // Auto-initialize on first access
        return initializeNotificationService();
    }
    return notificationServiceInstance;
}

// Auto-initialize on module load
initializeNotificationService();
