/**
 * Monitors API Routes (Fastify)
 * 
 * API per creazione e gestione monitor proattivi.
 * Phase 4.4: Direct integration with Gateway services (no backend proxy).
 */

import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { z } from 'zod';
import { monitorManager } from '../services/scheduler/monitor-manager.service.js';
import { getEvaluatorService } from '../services/scheduler/evaluator.service.js';
import { MonitorTypeSchema } from '@persan/shared';

// =============================================================================
// Validation Schemas
// =============================================================================

const CreateMonitorBodySchema = z.object({
    name: z.string().min(3, 'Name must be at least 3 characters').max(100, 'Name too long'),
    type: MonitorTypeSchema,
    description: z.string().optional(),
    config: z.record(z.unknown()),
    interval_minutes: z.number().int().min(1, 'Interval must be at least 1 minute').max(1440, 'Interval cannot exceed 24 hours'),
    notify_channels: z.array(z.enum(['telegram', 'slack', 'email', 'push'])).optional().default(['push']),
});

const MonitorIdParamsSchema = z.object({
    id: z.string().min(1, 'Monitor ID is required'),
});

const ParseQueryBodySchema = z.object({
    query: z.string().min(5, 'Query too short'),
});

// =============================================================================
// Types
// =============================================================================

type CreateMonitorBody = z.infer<typeof CreateMonitorBodySchema>;
type MonitorIdParams = z.infer<typeof MonitorIdParamsSchema>;
type ParseQueryBody = z.infer<typeof ParseQueryBodySchema>;

// =============================================================================
// Proactive Intent Detection (for Phase 4.5)
// =============================================================================

const PROACTIVE_TRIGGERS = [
    /crea\s+(un\s+)?agente/i,
    /crea\s+(un\s+)?sistema\s+automatic/i,
    /crea\s+(un\s+)?monitor/i,
    /ogni\s+(mattina|sera|giorno|ora|minuto)/i,
    /alle\s+\d{1,2}(:\d{2})?/i,
    /avvisami\s+(quando|se)/i,
    /notificami\s+(quando|se)/i,
    /ricordami\s+(di|che)/i,
    /monitorami/i,
    /controlla\s+(periodicamente|ogni)/i,
    /verifica\s+(periodicamente|ogni)/i,
    /tieni\s+d'occhio/i,
];

function isProactiveQuery(query: string): boolean {
    return PROACTIVE_TRIGGERS.some(pattern => pattern.test(query));
}

// =============================================================================
// Routes
// =============================================================================

export async function monitorRoutes(app: FastifyInstance): Promise<void> {

    // POST /api/monitors - Create monitor
    app.post('/api/monitors', async (
        request: FastifyRequest<{ Body: CreateMonitorBody }>,
        reply: FastifyReply
    ) => {
        try {
            const userId = request.headers['x-user-id'] as string || 'default';

            // Validate request body
            const validated = CreateMonitorBodySchema.parse(request.body);

            // Create monitor via MonitorManager
            const monitor = await monitorManager.createMonitor(userId, {
                type: validated.type,
                name: validated.name,
                description: validated.description || '',
                config: validated.config,
                interval_minutes: validated.interval_minutes,
                notify_channels: validated.notify_channels,
            });

            app.log.info({ monitorId: monitor.id, userId, type: monitor.type }, 'Monitor created');

            return reply.status(201).send({
                success: true,
                monitor,
                message: `Monitor "${monitor.name}" created successfully`,
            });
        } catch (error) {
            if (error instanceof z.ZodError) {
                return reply.status(400).send({
                    error: 'Validation failed',
                    details: error.errors,
                });
            }

            app.log.error({ error }, 'Failed to create monitor');
            return reply.status(500).send({
                error: 'Internal server error',
                message: error instanceof Error ? error.message : 'Unknown error',
            });
        }
    });

    // GET /api/monitors - List monitors
    app.get('/api/monitors', async (
        request: FastifyRequest,
        reply: FastifyReply
    ) => {
        try {
            const userId = request.headers['x-user-id'] as string || 'default';

            const monitors = await monitorManager.listMonitors(userId);

            return reply.send({
                success: true,
                monitors,
                total: monitors.length,
            });
        } catch (error) {
            app.log.error({ error }, 'Failed to list monitors');
            return reply.status(500).send({
                error: 'Internal server error',
                message: error instanceof Error ? error.message : 'Unknown error',
            });
        }
    });

    // GET /api/monitors/:id - Get monitor details
    app.get('/api/monitors/:id', async (
        request: FastifyRequest<{ Params: MonitorIdParams }>,
        reply: FastifyReply
    ) => {
        try {
            const { id } = MonitorIdParamsSchema.parse(request.params);

            const monitor = await monitorManager.getMonitor(id);

            if (!monitor) {
                return reply.status(404).send({
                    error: 'Monitor not found',
                    monitorId: id,
                });
            }

            return reply.send({
                success: true,
                monitor,
            });
        } catch (error) {
            if (error instanceof z.ZodError) {
                return reply.status(400).send({
                    error: 'Validation failed',
                    details: error.errors,
                });
            }

            app.log.error({ error }, 'Failed to get monitor');
            return reply.status(500).send({
                error: 'Internal server error',
                message: error instanceof Error ? error.message : 'Unknown error',
            });
        }
    });

    // DELETE /api/monitors/:id - Delete monitor
    app.delete('/api/monitors/:id', async (
        request: FastifyRequest<{ Params: MonitorIdParams }>,
        reply: FastifyReply
    ) => {
        try {
            const { id } = MonitorIdParamsSchema.parse(request.params);

            await monitorManager.deleteMonitor(id);

            app.log.info({ monitorId: id }, 'Monitor deleted');

            return reply.status(204).send();
        } catch (error) {
            if (error instanceof z.ZodError) {
                return reply.status(400).send({
                    error: 'Validation failed',
                    details: error.errors,
                });
            }

            app.log.error({ error }, 'Failed to delete monitor');
            return reply.status(500).send({
                error: 'Internal server error',
                message: error instanceof Error ? error.message : 'Unknown error',
            });
        }
    });

    // POST /api/monitors/:id/pause - Pause monitor
    app.post('/api/monitors/:id/pause', async (
        request: FastifyRequest<{ Params: MonitorIdParams }>,
        reply: FastifyReply
    ) => {
        try {
            const { id } = MonitorIdParamsSchema.parse(request.params);

            const monitor = await monitorManager.pauseMonitor(id);

            if (!monitor) {
                return reply.status(404).send({
                    error: 'Monitor not found',
                    monitorId: id,
                });
            }

            app.log.info({ monitorId: id }, 'Monitor paused');

            return reply.send({
                success: true,
                monitor,
                message: 'Monitor paused',
            });
        } catch (error) {
            if (error instanceof z.ZodError) {
                return reply.status(400).send({
                    error: 'Validation failed',
                    details: error.errors,
                });
            }

            app.log.error({ error }, 'Failed to pause monitor');
            return reply.status(500).send({
                error: 'Internal server error',
                message: error instanceof Error ? error.message : 'Unknown error',
            });
        }
    });

    // POST /api/monitors/:id/resume - Resume monitor
    app.post('/api/monitors/:id/resume', async (
        request: FastifyRequest<{ Params: MonitorIdParams }>,
        reply: FastifyReply
    ) => {
        try {
            const { id } = MonitorIdParamsSchema.parse(request.params);

            const monitor = await monitorManager.resumeMonitor(id);

            if (!monitor) {
                return reply.status(404).send({
                    error: 'Monitor not found',
                    monitorId: id,
                });
            }

            app.log.info({ monitorId: id }, 'Monitor resumed');

            return reply.send({
                success: true,
                monitor,
                message: 'Monitor resumed',
            });
        } catch (error) {
            if (error instanceof z.ZodError) {
                return reply.status(400).send({
                    error: 'Validation failed',
                    details: error.errors,
                });
            }

            app.log.error({ error }, 'Failed to resume monitor');
            return reply.status(500).send({
                error: 'Internal server error',
                message: error instanceof Error ? error.message : 'Unknown error',
            });
        }
    });

    // POST /api/monitors/:id/trigger - Force immediate evaluation
    app.post('/api/monitors/:id/trigger', async (
        request: FastifyRequest<{ Params: MonitorIdParams }>,
        reply: FastifyReply
    ) => {
        try {
            const { id } = MonitorIdParamsSchema.parse(request.params);

            // Get monitor to verify it exists
            const monitor = await monitorManager.getMonitor(id);
            if (!monitor) {
                return reply.status(404).send({
                    error: 'Monitor not found',
                    monitorId: id,
                });
            }

            // Trigger immediate evaluation
            const evaluatorService = getEvaluatorService();
            const result = await evaluatorService.evaluate(id);

            app.log.info({ monitorId: id, trigger: result.trigger }, 'Monitor evaluation triggered');

            return reply.send({
                success: true,
                result,
                message: 'Monitor evaluated successfully',
            });
        } catch (error) {
            if (error instanceof z.ZodError) {
                return reply.status(400).send({
                    error: 'Validation failed',
                    details: error.errors,
                });
            }

            app.log.error({ error }, 'Failed to trigger monitor evaluation');
            return reply.status(500).send({
                error: 'Internal server error',
                message: error instanceof Error ? error.message : 'Unknown error',
            });
        }
    });

    // POST /api/monitors/parse - Parse natural language query (Phase 4.5)
    // TODO: Replace with Me4BrAIn integration in Phase 4.5
    app.post('/api/monitors/parse', async (
        request: FastifyRequest<{ Body: ParseQueryBody }>,
        reply: FastifyReply
    ) => {
        try {
            const { query } = ParseQueryBodySchema.parse(request.body);

            if (!isProactiveQuery(query)) {
                return reply.send({
                    success: false,
                    is_proactive: false,
                    message: 'Query does not appear to be a proactive intent',
                });
            }

            // TODO Phase 4.5: Integrate with Me4BrAIn for NL parsing
            // For now, return basic fallback response
            return reply.send({
                success: true,
                is_proactive: true,
                parsed: {
                    type: 'SCHEDULED',
                    name: 'Custom Monitor',
                    description: query,
                    config: { raw_query: query },
                    interval_minutes: 5,
                    notify_channels: ['web'],
                    confidence: 0.5,
                },
                message: 'Parsed with fallback (Phase 4.5 will add Me4BrAIn integration)',
            });
        } catch (error) {
            if (error instanceof z.ZodError) {
                return reply.status(400).send({
                    error: 'Validation failed',
                    details: error.errors,
                });
            }

            app.log.error({ error }, 'Failed to parse query');
            return reply.status(500).send({
                error: 'Internal server error',
                message: error instanceof Error ? error.message : 'Unknown error',
            });
        }
    });
}

export { isProactiveQuery };
