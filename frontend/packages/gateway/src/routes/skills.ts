import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { Me4BrAInClient } from '@persan/me4brain-client';

export async function skillsRoutes(app: FastifyInstance): Promise<void> {

    // Initialize Me4BrAIn client
    const me4brain = new Me4BrAInClient({
        baseUrl: process.env.ME4BRAIN_URL ?? 'http://me4brain-api:8000/v1',
        apiKey: process.env.ME4BRAIN_API_KEY,
    });

    /**
     * GET /api/skills - Lista all skills (proxy to Me4BrAIn)
     */
    app.get('/api/skills', async (req: FastifyRequest, reply: FastifyReply) => {
        try {
            const { type, enabled } = req.query as { type?: 'explicit' | 'crystallized', enabled?: string };
            const enabledOnly = enabled !== 'false';

            const response = await me4brain.skills.list(type, enabledOnly);
            return reply.send(response);
        } catch (error) {
            app.log.error(error as any, 'skills_list_proxy_error');
            return reply.status(502).send({ error: 'Failed to fetch skills from Me4BrAIn' });
        }
    });

    /**
     * GET /api/skills/stats - Statistiche skills
     */
    app.get('/api/skills/stats', async (_req: FastifyRequest, reply: FastifyReply) => {
        try {
            const stats = await me4brain.skills.approvalStats();
            return reply.send(stats);
        } catch (error) {
            app.log.error(error as any, 'skills_stats_proxy_error');
            return reply.send({
                total_explicit: 0,
                total_crystallized: 0,
                total_usage: 0,
                avg_success_rate: 0,
                crystallization_rate: 0,
            });
        }
    });

    /**
     * GET /api/skills/search/clawhub - Search via ClawHub (using me4brain client)
     */
    app.get('/api/skills/search/clawhub', async (req: FastifyRequest, reply: FastifyReply) => {
        try {
            const { q } = req.query as { q: string };
            if (!q) return reply.send({ results: [] });

            // Note: Should use a semantic search if available, for now proxying roughly
            return reply.send({ results: [] });
        } catch (error) {
            return reply.send({ results: [] });
        }
    });

    /**
     * GET /api/skills/pending - Skills pending approval
     */
    app.get('/api/skills/pending', async (_req: FastifyRequest, reply: FastifyReply) => {
        try {
            const pending = await me4brain.skills.listPending();
            return reply.send(pending);
        } catch (error) {
            return reply.send([]);
        }
    });

    /**
     * GET /api/skills/:id - Dettaglio skill
     */
    app.get<{ Params: { id: string } }>('/api/skills/:id', async (req, reply) => {
        try {
            const skill = await me4brain.skills.get(req.params.id);
            return reply.send(skill);
        } catch (error) {
            return reply.status(404).send({ error: 'Skill not found' });
        }
    });

    /**
     * PATCH /api/skills/:id - Toggle enabled
     */
    app.patch<{ Params: { id: string }; Body: { enabled: boolean } }>('/api/skills/:id', async (req, reply) => {
        try {
            const skill = await me4brain.skills.toggle(req.params.id, req.body.enabled);
            return reply.send(skill);
        } catch (error) {
            return reply.status(404).send({ error: 'Failed to toggle skill' });
        }
    });

    /**
     * DELETE /api/skills/:id - Elimina skill
     */
    app.delete<{ Params: { id: string } }>('/api/skills/:id', async (req, reply) => {
        try {
            await me4brain.skills.delete(req.params.id);
            return reply.status(204).send();
        } catch (error) {
            return reply.status(404).send({ error: 'Failed to delete skill' });
        }
    });

    /**
     * POST /api/skills/pending/:id/approve
     */
    app.post<{ Params: { id: string }; Body: { note?: string } }>('/api/skills/pending/:id/approve', async (req, reply) => {
        try {
            const result = await me4brain.skills.approve(req.params.id, { note: req.body.note });
            return reply.send(result);
        } catch (error) {
            return reply.status(500).send({ error: 'Failed to approve skill' });
        }
    });
}
