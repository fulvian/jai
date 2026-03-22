/**
 * Fastify App Factory
 * 
 * Configura Fastify con plugins, routes e WebSocket.
 */

import Fastify, { FastifyInstance } from 'fastify';
import cors from '@fastify/cors';
import websocket from '@fastify/websocket';
import { registerRoutes } from './routes/index.js';
import { registerWebSocket } from './websocket/handler.js';
import { channelManager, TelegramAdapter, WhatsAppAdapter } from './channels/index.js';
import { errorHandler, correlationIdMiddleware } from './middleware/error-handler.js';

export async function buildApp(): Promise<FastifyInstance> {
    const app = Fastify({
        logger: {
            level: process.env.LOG_LEVEL ?? 'info',
            transport: process.env.NODE_ENV !== 'production'
                ? { target: 'pino-pretty', options: { colorize: true } }
                : undefined,
        },
        requestIdHeader: 'x-request-id',
        connectionTimeout: 0,       // No connection timeout for long queries
        requestTimeout: 0,          // No request timeout (Me4BrAIn queries can take 10+ min)
        keepAliveTimeout: 1_800_000, // 30 min — aligned with engine client max timeout
    });

    // Global error handler
    app.setErrorHandler(errorHandler);

    // Correlation ID middleware (for distributed tracing)
    app.addHook('onRequest', correlationIdMiddleware);

    // CORS - allow frontend (Tailscale IP, localhost, and internal docker)
    await app.register(cors, {
        origin: (origin, cb) => {
            const allowedOrigins = [
                'http://localhost:3020',
                'http://localhost:3030',
                'http://127.0.0.1:3020',
                'http://127.0.0.1:3030',
                process.env.FRONTEND_URL,
            ].filter(Boolean) as string[];

            // Per richieste senza origin (es. mobile apps, Postman, server-to-server)
            if (!origin) return cb(null, true);

            // Check exact match
            if (allowedOrigins.includes(origin)) {
                return cb(null, true);
            }

            // Check Tailscale domains (*.ts.net)
            if (origin.endsWith('.ts.net')) {
                return cb(null, true);
            }

            // Check Tailscale IP range (100.x.x.x)
            try {
                const url = new URL(origin);
                if (url.hostname.startsWith('100.')) {
                    return cb(null, true);
                }
            } catch {
                // Invalid URL, continue to reject
            }

            // Check internal Docker network (172.x.x.x, 10.x.x.x)
            try {
                const url = new URL(origin);
                if (url.hostname.startsWith('172.') || url.hostname.startsWith('10.')) {
                    return cb(null, true);
                }
            } catch {
                // Invalid URL, continue to reject
            }

            // Reject other origins
            cb(new Error('Origin not allowed by CORS policy'), false);
        },
        credentials: true,
        methods: ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'OPTIONS'],
        allowedHeaders: ['Content-Type', 'Authorization', 'X-Tenant-ID', 'X-User-ID', 'Accept'],
    });

    // WebSocket plugin
    await app.register(websocket, {
        options: {
            maxPayload: 1024 * 1024, // 1MB max message size
        },
    });

    // Multipart plugin for file uploads
    await app.register(import('@fastify/multipart'), {
        limits: {
            fileSize: 10 * 1024 * 1024, // 10MB max file size
        },
    });

    // HTTP Routes
    await registerRoutes(app);

    // WebSocket Handler
    await registerWebSocket(app);

    // Initialize Channel Adapters (background)
    initializeChannels(app).catch(err => app.log.error(err));

    return app;
}

async function initializeChannels(app: FastifyInstance): Promise<void> {
    channelManager.setApp(app);

    // Telegram - requires TELEGRAM_BOT_TOKEN
    const telegramToken = process.env.TELEGRAM_BOT_TOKEN;
    if (telegramToken) {
        const allowedUsers = process.env.TELEGRAM_ALLOWED_USERS?.split(',').filter(Boolean);

        const telegramAdapter = new TelegramAdapter({
            botToken: telegramToken,
            allowedUsers,
            onMessage: (msg) => channelManager.handleIncoming(msg),
        });

        channelManager.register(telegramAdapter);
        app.log.info('📱 Telegram adapter registered');
    } else {
        app.log.info('📱 Telegram: TELEGRAM_BOT_TOKEN not set, skipping');
    }

    // WhatsApp - requires WHATSAPP_ENABLED=true
    const whatsappEnabled = process.env.WHATSAPP_ENABLED === 'true';
    if (whatsappEnabled) {
        const authDir = process.env.WHATSAPP_AUTH_DIR ?? './whatsapp-auth';
        const allowedNumbers = process.env.WHATSAPP_ALLOWED_NUMBERS?.split(',').filter(Boolean);

        const whatsappAdapter = new WhatsAppAdapter({
            authDir,
            allowedNumbers,
            onMessage: (msg) => channelManager.handleIncoming(msg),
            onQRCode: (qr: string) => {
                app.log.info(`📱 WhatsApp QR Code ready (${qr.length} chars) - check terminal`);
            },
        });

        channelManager.register(whatsappAdapter);
        app.log.info('📱 WhatsApp adapter registered');
    } else {
        app.log.info('📱 WhatsApp: WHATSAPP_ENABLED not set, skipping');
    }

    // Connect all registered channels
    await channelManager.connectAll();
}

