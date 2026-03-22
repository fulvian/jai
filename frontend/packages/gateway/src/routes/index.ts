/**
 * HTTP Routes
 */

import { FastifyInstance } from 'fastify';
import { voiceRoutes } from './voice.js';
import { pushRoutes } from './push.js';
import { approvalRoutes } from './approvals.js';
import { monitorRoutes } from './monitors.js';
import { chatRoutes } from './chat.js';
import { skillsRoutes } from './skills.js';
import { graphRoutes } from './graph.js';
import { uploadRoutes } from './upload.js';
import { configRoutes } from './config.js';
import { providersRoutes } from './providers.js';

export async function registerRoutes(app: FastifyInstance): Promise<void> {
    // Health check
    app.get('/health', async () => {
        return {
            status: 'healthy',
            timestamp: new Date().toISOString(),
            version: '0.1.0',
            uptime: process.uptime(),
        };
    });

    // Health check that also verifies Me4BrAIn connection
    app.get('/health/full', async () => {
        const gatewayHealth = {
            status: 'healthy',
            timestamp: new Date().toISOString(),
            uptime: process.uptime(),
        };

        let me4brainHealth: any = { status: 'unknown' };
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 2000);

            const response = await fetch(`${process.env.ME4BRAIN_URL || 'http://localhost:8000'}/health`, {
                signal: controller.signal
            });
            clearTimeout(timeoutId);

            if (response.ok) {
                const data = await response.json();
                // Ensure data is an object before spreading
                if (data && typeof data === 'object' && !Array.isArray(data)) {
                    me4brainHealth = { status: 'healthy', ...data };
                } else {
                    me4brainHealth = { status: 'healthy', data };
                }
            } else {
                me4brainHealth = { status: 'unhealthy', error: `HTTP ${response.status}` };
            }
        } catch (error) {
            me4brainHealth = { status: 'unhealthy', error: String(error) };
        }

        const overall = me4brainHealth.status === 'healthy' ? 'healthy' : 'degraded';

        return {
            gateway: gatewayHealth,
            me4brain: me4brainHealth,
            overall: overall,
        };
    });

    // Ready check (per k8s)
    app.get('/ready', async () => {
        // TODO: check Me4BrAIn connection, Redis, etc.
        return { ready: true };
    });

    // Voice routes
    await app.register(voiceRoutes);

    // Upload routes (file upload with OCR)
    await app.register(uploadRoutes);

    // Push notification routes (Phase 5)
    await app.register(pushRoutes);

    // HITL Approval routes
    await approvalRoutes(app);

    // Monitor/Proactive routes (NL-to-Monitor)
    await monitorRoutes(app);

    // Chat session routes (Web Dashboard)
    await chatRoutes(app);

    // Skills proxy routes (Me4BrAIn /v1/skills)
    await skillsRoutes(app);

    // Graph Session Knowledge routes (proxy to Me4BrAIn)
    await graphRoutes(app);

    // LLM Config routes (proxy to Me4BrAIn)
    await configRoutes(app);

    // Providers routes (proxy to Me4BrAIn)
    await providersRoutes(app);

    // API routes placeholder
    app.get('/api/status', async () => {
        return {
            gateway: 'persan',
            version: '2.0.0-alpha',
            channels: ['webchat', 'telegram', 'whatsapp'],
            features: {
                websocket: true,
                streaming: true,
                voice: true, // Fase 2 ✅
                canvas: false, // Fase 3
                proactive: true, // Fase 5 ✅
                hitl: true, // HITL Approval ✅
            },
        };
    });
}

