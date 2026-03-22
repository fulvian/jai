/**
 * WebSocket Handler
 * 
 * Gestisce connessioni WebSocket e routing messaggi.
 */

import { FastifyInstance } from 'fastify';
import { WebSocket } from 'ws';
import { SessionManager } from '../services/session.js';
import { MessageRouter } from './router.js';
import { connectionRegistry } from './registry.js';
import type { WSMessage } from '@persan/shared';

const sessions = new SessionManager();
const router = new MessageRouter();

export async function registerWebSocket(app: FastifyInstance): Promise<void> {
    app.get('/ws', { websocket: true }, (socket: WebSocket, req) => {
        app.log.info({
            headers: req.headers,
            query: req.query,
            ip: req.ip
        }, 'Incoming WebSocket connection request');

        // Estrai sessionId facoltativo dalla query per riconnessione
        const query = req.query as { sessionId?: string };
        const sessionId = query.sessionId || crypto.randomUUID();
        const userId = 'default'; // TODO: Get from auth header/token

        app.log.info({ sessionId, userId, isReconnect: !!query.sessionId }, 'WebSocket connection established');

        // Register in connection registry
        connectionRegistry.register(sessionId, socket, userId);

        // Se è una riconnessione, reinvia tutti i messaggi bufferizzati in Redis
        if (query.sessionId) {
            (async () => {
                try {
                    const { queryExecutor } = await import('../services/query_executor.js');
                    const buffer = await queryExecutor.getBuffer(sessionId);
                    if (buffer.length > 0) {
                        app.log.info({ sessionId, bufferSize: buffer.length }, 'Replaying session buffer');
                        for (const msg of buffer) {
                            socket.send(JSON.stringify(msg));
                        }
                    }
                } catch (err) {
                    app.log.error({ err, sessionId }, 'Failed to replay session buffer');
                }
            })();
        }

        // Replay missed notifications for this user
        (async () => {
            try {
                const { getNotificationService } = await import('../services/scheduler/notification-service.instance.js');
                const notificationService = getNotificationService();
                await notificationService.replayNotifications(userId);
                app.log.info({ userId, sessionId }, 'Notification replay completed');
            } catch (err) {
                app.log.error({ err, userId, sessionId }, 'Failed to replay notifications');
            }
        })();

        socket.on('message', async (data) => {
            try {
                const message = JSON.parse(data.toString()) as WSMessage;
                app.log.info({ type: message.type, sessionId }, 'Received WebSocket message');
                await router.handle(socket, sessionId, message);
            } catch (error) {
                const errorMsg: WSMessage = {
                    type: 'error',
                    data: {
                        message: error instanceof Error ? error.message : 'Invalid JSON',
                        code: 'PARSE_ERROR',
                    },
                    timestamp: Date.now(),
                };
                socket.send(JSON.stringify(errorMsg));
            }
        });

        socket.on('close', (code, reason) => {
            app.log.info({ sessionId, code, reason: reason.toString() }, 'WebSocket connection closed');
            connectionRegistry.unregister(sessionId);
        });

        socket.on('error', (error) => {
            app.log.error({ sessionId, error }, 'WebSocket error');
        });

        // Send session init with a small delay to avoid race condition in browser handshake
        setTimeout(() => {
            if (socket.readyState !== WebSocket.OPEN) {
                app.log.warn({ sessionId, state: socket.readyState }, 'Socket closed before session:init could be sent');
                return;
            }

            const initMsg: WSMessage = {
                type: 'session:init',
                data: { sessionId },
                timestamp: Date.now(),
            };

            try {
                socket.send(JSON.stringify(initMsg), (err) => {
                    if (err) {
                        app.log.error({ err, sessionId }, 'Failed to send session:init via callback');
                    } else {
                        app.log.info({ sessionId }, 'Successfully sent session:init');
                    }
                });
            } catch (err) {
                app.log.error({ err, sessionId }, 'Exception while sending session:init');
            }
        }, 100);

        // Create or refresh session
        sessions.create('webchat', sessionId).catch((err) => {
            app.log.error({ err, sessionId }, 'Failed to create/refresh session');
        });
    });
}

// Export registry for use in routes
export { connectionRegistry };

