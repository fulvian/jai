import { FastifyInstance } from 'fastify';

const ME4BRAIN_URL = process.env.ME4BRAIN_URL || 'http://localhost:8000';

export async function providersRoutes(app: FastifyInstance): Promise<void> {
    app.get('/api/providers', async (_req, _reply) => {
        const response = await fetch(`${ME4BRAIN_URL}/v1/providers`);
        return response.json();
    });

    app.post('/api/providers', async (req, _reply) => {
        const response = await fetch(`${ME4BRAIN_URL}/v1/providers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(req.body),
        });
        return response.json();
    });

    app.put('/api/providers/:id', async (req: any, _reply) => {
        const response = await fetch(`${ME4BRAIN_URL}/v1/providers/${req.params.id}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(req.body),
        });
        return response.json();
    });

    app.delete('/api/providers/:id', async (req: any, _reply) => {
        const response = await fetch(`${ME4BRAIN_URL}/v1/providers/${req.params.id}`, {
            method: 'DELETE',
        });
        return response.json();
    });

    app.post('/api/providers/:id/test', async (req: any, _reply) => {
        const response = await fetch(`${ME4BRAIN_URL}/v1/providers/${req.params.id}/test`, {
            method: 'POST',
        });
        return response.json();
    });

    app.get('/api/providers/:id/discover', async (req: any, _reply) => {
        const response = await fetch(`${ME4BRAIN_URL}/v1/providers/${req.params.id}/discover`);
        return response.json();
    });

    // Get subscription info
    app.get('/api/providers/:id/subscription', async (req: any, _reply) => {
        const response = await fetch(`${ME4BRAIN_URL}/v1/providers/${req.params.id}/subscription`);
        return response.json();
    });

    // Reset subscription
    app.post('/api/providers/:id/subscription/reset', async (req: any, _reply) => {
        const response = await fetch(`${ME4BRAIN_URL}/v1/providers/${req.params.id}/subscription/reset`, {
            method: 'POST',
        });
        return response.json();
    });

    // Get subscription models
    app.get('/api/providers/subscription/models', async (_req, _reply) => {
        const response = await fetch(`${ME4BRAIN_URL}/v1/providers/subscription/models`);
        return response.json();
    });
}
