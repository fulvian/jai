/**
 * Push Notification Service
 * 
 * Gestisce l'invio di notifiche push ai browser registrati.
 */

import webpush from 'web-push';
import { Redis } from 'ioredis';

interface NotificationPayload {
    title: string;
    body: string;
    icon?: string;
    data?: any;
}

export class PushService {
    private redis: Redis;
    private subPrefix = 'persan:push:sub:';

    constructor() {
        this.redis = new Redis(process.env.REDIS_URL ?? 'redis://localhost:6389', {
            password: process.env.REDIS_PASSWORD,
        });

        const publicKey = process.env.VAPID_PUBLIC_KEY;
        const privateKey = process.env.VAPID_PRIVATE_KEY;
        const subject = process.env.VAPID_SUBJECT ?? 'mailto:admin@persan.ai';

        if (publicKey && privateKey) {
            webpush.setVapidDetails(subject, publicKey, privateKey);
            console.log('✅ Push Notification Service initialized with VAPID');
        } else {
            console.warn('⚠️ VAPID keys missing. Push notifications disabled.');
        }
    }

    /**
     * Salva una sottoscrizione per un utente.
     */
    async subscribe(userId: string, subscription: webpush.PushSubscription): Promise<void> {
        const key = `${this.subPrefix}${userId}`;
        // Supportiamo più browser/dispositivi per lo stesso utente (Set)
        await this.redis.sadd(key, JSON.stringify(subscription));
        await this.redis.expire(key, 86400 * 30); // 30 giorni
    }

    /**
     * Rimuove una sottoscrizione.
     */
    async unsubscribe(userId: string, subscription: webpush.PushSubscription): Promise<void> {
        const key = `${this.subPrefix}${userId}`;
        await this.redis.srem(key, JSON.stringify(subscription));
    }

    /**
     * Invia una notifica a tutte le sottoscrizioni dell'utente.
     */
    async sendNotification(userId: string, payload: NotificationPayload): Promise<void> {
        const key = `${this.subPrefix}${userId}`;
        const subscriptions = await this.redis.smembers(key);

        if (subscriptions.length === 0) {
            console.log(`[PushService] No subscriptions found for user ${userId}`);
            return;
        }

        console.log(`[PushService] Sending notification to ${subscriptions.length} devices for user ${userId}`);

        const notificationJson = JSON.stringify(payload);

        const tasks = subscriptions.map(async (subJson) => {
            try {
                const subscription = JSON.parse(subJson);
                await webpush.sendNotification(subscription, notificationJson);
            } catch (error: any) {
                if (error.statusCode === 410 || error.statusCode === 404) {
                    console.log(`[PushService] Subscription expired for user ${userId}, removing`);
                    await this.redis.srem(key, subJson);
                } else {
                    console.error(`[PushService] Failed to send notification:`, error);
                }
            }
        });

        await Promise.all(tasks);
    }
}

export const pushService = new PushService();
