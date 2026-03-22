/**
 * Push Notification Routes
 *
 * Endpoint HTTP per permettere al backend Python di inviare
 * notifiche push via WebSocket.
 */

import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { connectionRegistry } from '../websocket/handler.js';
import type { MonitorAlertData, MonitorUpdateData } from '@persan/shared';

// Request body types
interface MonitorAlertRequest {
    userId: string;
    alert: MonitorAlertData;
}

interface MonitorUpdateRequest {
    userId: string;
    update: MonitorUpdateData;
}

interface BroadcastRequest {
    message: {
        type: string;
        data: unknown;
    };
}

export async function pushRoutes(app: FastifyInstance): Promise<void> {
    /**
     * POST /api/push/monitor/alert
     * Invia alert monitor a un utente specifico
     */
    app.post('/api/push/monitor/alert', async (
        request: FastifyRequest<{ Body: MonitorAlertRequest }>,
        reply: FastifyReply
    ) => {
        const { userId, alert } = request.body;

        if (!userId || !alert) {
            return reply.status(400).send({
                error: 'Missing userId or alert data',
            });
        }

        const sent = connectionRegistry.sendMonitorAlert(userId, alert);

        app.log.info({
            userId,
            monitorId: alert.monitorId,
            sent,
        }, 'Monitor alert pushed');

        return {
            success: true,
            sent,
            userId,
            monitorId: alert.monitorId,
        };
    });

    /**
     * POST /api/push/monitor/update
     * Invia aggiornamento stato monitor a un utente
     */
    app.post('/api/push/monitor/update', async (
        request: FastifyRequest<{ Body: MonitorUpdateRequest }>,
        reply: FastifyReply
    ) => {
        const { userId, update } = request.body;

        if (!userId || !update) {
            return reply.status(400).send({
                error: 'Missing userId or update data',
            });
        }

        const sent = connectionRegistry.sendMonitorUpdate(userId, update);

        return {
            success: true,
            sent,
            userId,
            monitorId: update.monitorId,
        };
    });

    /**
     * POST /api/push/broadcast
     * Broadcast messaggio a tutte le connessioni
     */
    app.post('/api/push/broadcast', async (
        request: FastifyRequest<{ Body: BroadcastRequest }>,
        reply: FastifyReply
    ) => {
        const { message } = request.body;

        if (!message || !message.type) {
            return reply.status(400).send({
                error: 'Missing message or message.type',
            });
        }

        const sent = connectionRegistry.broadcast({
            type: message.type as any,
            data: message.data,
            timestamp: Date.now(),
        });

        return {
            success: true,
            sent,
        };
    });

    /**
     * POST /api/push/subscribe
     * Registra una sottoscrizione push per un utente
     */
    app.post('/api/push/subscribe', async (
        request: FastifyRequest<{ Body: { userId: string; subscription: any } }>,
        reply: FastifyReply
    ) => {
        const { userId, subscription } = request.body;

        if (!userId || !subscription) {
            return reply.status(400).send({
                error: 'Missing userId or subscription data',
            });
        }

        const { pushService } = await import('../services/push_notifications.js');
        await pushService.subscribe(userId, subscription);

        app.log.info({ userId }, 'Push subscription registered');

        return { success: true };
    });

    /**
     * GET /api/push/stats
     * Statistiche connessioni WebSocket
     */
    app.get('/api/push/stats', async () => {
        return connectionRegistry.getStats();
    });
}
