import { FastifyInstance } from 'fastify';
import fetch from 'node-fetch';

const ME4BRAIN_URL = process.env.ME4BRAIN_URL || 'http://localhost:8089';

export async function providersRoutes(fastify: FastifyInstance) {
  // List providers
  fastify.get('/api/providers', async (req, reply) => {
    const response = await fetch(`${ME4BRAIN_URL}/v1/providers`);
    return response.json();
  });

  // Create provider
  fastify.post('/api/providers', async (req, reply) => {
    const response = await fetch(`${ME4BRAIN_URL}/v1/providers`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body),
    });
    return response.json();
  });

  // Update provider
  fastify.put('/api/providers/:id', async (req, reply) => {
    const response = await fetch(`${ME4BRAIN_URL}/v1/providers/${req.params.id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body),
    });
    return response.json();
  });

  // Delete provider
  fastify.delete('/api/providers/:id', async (req, reply) => {
    const response = await fetch(`${ME4BRAIN_URL}/v1/providers/${req.params.id}`, {
      method: 'DELETE',
    });
    return response.json();
  });

  // Test provider
  fastify.post('/api/providers/:id/test', async (req, reply) => {
    const response = await fetch(`${ME4BRAIN_URL}/v1/providers/${req.params.id}/test`, {
      method: 'POST',
    });
    return response.json();
  });

  // Discover models
  fastify.get('/api/providers/:id/discover', async (req, reply) => {
    const response = await fetch(`${ME4BRAIN_URL}/v1/providers/${req.params.id}/discover`);
    return response.json();
  });

  // Get subscription info
  fastify.get('/api/providers/:id/subscription', async (req, reply) => {
    const response = await fetch(`${ME4BRAIN_URL}/v1/providers/${req.params.id}/subscription`);
    return response.json();
  });

  // Reset subscription
  fastify.post('/api/providers/:id/subscription/reset', async (req, reply) => {
    const response = await fetch(`${ME4BRAIN_URL}/v1/providers/${req.params.id}/subscription/reset`, {
      method: 'POST',
    });
    return response.json();
  });

  // Get subscription models
  fastify.get('/api/providers/subscription/models', async (req, reply) => {
    const response = await fetch(`${ME4BRAIN_URL}/v1/providers/subscription/models`);
    return response.json();
  });
}
