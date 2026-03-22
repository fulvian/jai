/**
 * Graph Session Routes
 *
 * Proxy routes per il Session Knowledge Graph di Me4Brain.
 * Il frontend chiama /api/graph/* e il gateway proxy-a a Me4Brain /v1/sessions/graph/*
 */

import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { graphSessionService } from '../services/graph_session_service.js';

export async function graphRoutes(app: FastifyInstance): Promise<void> {
    // ── Clusters ─────────────────────────────────────────────────────
    app.get('/api/graph/clusters', async (_req: FastifyRequest, reply: FastifyReply) => {
        const clusters = await graphSessionService.getClusters();
        return reply.send(clusters);
    });

    // ── Related Sessions ─────────────────────────────────────────────
    app.get('/api/graph/related/:sessionId', async (req: FastifyRequest<{
        Params: { sessionId: string };
        Querystring: { limit?: string };
    }>, reply: FastifyReply) => {
        const { sessionId } = req.params;
        const limit = parseInt(req.query.limit ?? '5', 10);
        const related = await graphSessionService.getRelatedSessions(sessionId, limit);
        return reply.send(related);
    });

    // ── Semantic Search ──────────────────────────────────────────────
    app.post('/api/graph/search', async (req: FastifyRequest<{
        Body: { query: string; top_k?: number; use_reranking?: boolean };
    }>, reply: FastifyReply) => {
        const { query, top_k = 10, use_reranking = true } = req.body;
        const results = await graphSessionService.searchSessions(query, top_k, use_reranking);
        return reply.send(results);
    });

    // ── Topics ───────────────────────────────────────────────────────
    app.get('/api/graph/topics', async (req: FastifyRequest<{
        Querystring: { limit?: string };
    }>, reply: FastifyReply) => {
        const limit = parseInt(req.query.limit ?? '50', 10);
        const topics = await graphSessionService.getTopics(limit);
        return reply.send(topics);
    });

    // ── Detect Communities ───────────────────────────────────────────
    app.post('/api/graph/detect-communities', async (req: FastifyRequest<{
        Querystring: { min_cluster_size?: string };
    }>, reply: FastifyReply) => {
        const minSize = parseInt(req.query.min_cluster_size ?? '2', 10);
        const clusters = await graphSessionService.detectCommunities(minSize);
        return reply.send(clusters);
    });
    // ── Connected Nodes (Exploration) ──────────────────────────────────
    app.get('/api/graph/connected-nodes/:sessionId', async (req: FastifyRequest<{
        Params: { sessionId: string };
        Querystring: { top_k?: string };
    }>, reply: FastifyReply) => {
        const { sessionId } = req.params;
        const topK = parseInt(req.query.top_k ?? '3', 10);
        const nodes = await graphSessionService.getConnectedNodes(sessionId, topK);
        return reply.send(nodes);
    });

    // ── Prompt Library ───────────────────────────────────────────────
    app.get('/api/graph/prompts', async (req: FastifyRequest<{
        Querystring: { category?: string };
    }>, reply: FastifyReply) => {
        const prompts = await graphSessionService.getPromptLibrary(req.query.category);
        return reply.send(prompts);
    });

    app.post('/api/graph/prompts', async (req: FastifyRequest<{
        Body: {
            id?: string;
            label: string;
            content: string;
            category?: string;
            variables?: string[];
            topics?: string[];
        };
    }>, reply: FastifyReply) => {
        const result = await graphSessionService.savePromptTemplate(req.body);
        return reply.send(result);
    });

    app.post('/api/graph/prompts/search', async (req: FastifyRequest<{
        Body: { query: string; top_k?: number };
    }>, reply: FastifyReply) => {
        const { query, top_k = 5 } = req.body;
        const results = await graphSessionService.searchPrompts(query, top_k);
        return reply.send(results);
    });

    app.get('/api/graph/prompts/suggest/:sessionId', async (req: FastifyRequest<{
        Params: { sessionId: string };
        Querystring: { top_k?: string };
    }>, reply: FastifyReply) => {
        const { sessionId } = req.params;
        const topK = parseInt(req.query.top_k ?? '3', 10);
        const suggestions = await graphSessionService.suggestPrompts(sessionId, topK);
        return reply.send(suggestions);
    });
}
