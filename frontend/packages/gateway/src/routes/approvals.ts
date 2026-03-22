/**
 * Approval Routes
 * 
 * API endpoints per gestione approvazioni HITL.
 */

import { FastifyInstance, FastifyRequest, FastifyReply } from 'fastify';
import { getApprovalQueue } from '../services/approval_queue.js';

interface ApprovalParams {
    requestId: string;
}

interface ApprovalBody {
    approved: boolean;
}

export async function approvalRoutes(app: FastifyInstance): Promise<void> {
    const queue = getApprovalQueue();

    /**
     * GET /api/approvals
     * Lista richieste pendenti per l'utente corrente
     */
    app.get('/api/approvals', async (_request: FastifyRequest, reply: FastifyReply) => {
        const userId = 'default'; // TODO: Get from auth

        const pending = queue.getPending(userId);

        return reply.send({
            pending: pending.map((r) => ({
                id: r.id,
                tool: r.tool,
                message: r.message,
                urgency: r.urgency,
                createdAt: r.createdAt.toISOString(),
                expiresAt: r.expiresAt.toISOString(),
            })),
            stats: queue.getStats(),
        });
    });

    /**
     * GET /api/approvals/:requestId
     * Dettagli di una richiesta
     */
    app.get<{ Params: ApprovalParams }>(
        '/api/approvals/:requestId',
        async (request: FastifyRequest<{ Params: ApprovalParams }>, reply: FastifyReply) => {
            const { requestId } = request.params;
            const approval = queue.get(requestId);

            if (!approval) {
                return reply.status(404).send({ error: 'Approval request not found' });
            }

            return reply.send({
                id: approval.id,
                tool: approval.tool,
                args: approval.args,
                message: approval.message,
                urgency: approval.urgency,
                status: approval.status,
                createdAt: approval.createdAt.toISOString(),
                expiresAt: approval.expiresAt.toISOString(),
                resolvedAt: approval.resolvedAt?.toISOString(),
            });
        }
    );

    /**
     * POST /api/approvals/:requestId/approve
     * Approva una richiesta
     */
    app.post<{ Params: ApprovalParams }>(
        '/api/approvals/:requestId/approve',
        async (request: FastifyRequest<{ Params: ApprovalParams }>, reply: FastifyReply) => {
            const { requestId } = request.params;
            const userId = 'default'; // TODO: Get from auth

            const success = await queue.approve(requestId, userId);

            if (!success) {
                return reply.status(400).send({
                    error: 'Could not approve request',
                    reason: 'Request not found, already resolved, or user mismatch',
                });
            }

            app.log.info({ requestId, userId }, 'Approval request approved');

            return reply.send({ success: true, approved: true });
        }
    );

    /**
     * POST /api/approvals/:requestId/deny
     * Nega una richiesta
     */
    app.post<{ Params: ApprovalParams }>(
        '/api/approvals/:requestId/deny',
        async (request: FastifyRequest<{ Params: ApprovalParams }>, reply: FastifyReply) => {
            const { requestId } = request.params;
            const userId = 'default'; // TODO: Get from auth

            const success = await queue.deny(requestId, userId);

            if (!success) {
                return reply.status(400).send({
                    error: 'Could not deny request',
                    reason: 'Request not found, already resolved, or user mismatch',
                });
            }

            app.log.info({ requestId, userId }, 'Approval request denied');

            return reply.send({ success: true, approved: false });
        }
    );

    /**
     * POST /api/approvals/:requestId/resolve
     * Risolve con body { approved: boolean }
     */
    app.post<{ Params: ApprovalParams; Body: ApprovalBody }>(
        '/api/approvals/:requestId/resolve',
        async (
            request: FastifyRequest<{ Params: ApprovalParams; Body: ApprovalBody }>,
            reply: FastifyReply
        ) => {
            const { requestId } = request.params;
            const { approved } = request.body;
            const userId = 'default'; // TODO: Get from auth

            const success = approved
                ? await queue.approve(requestId, userId)
                : await queue.deny(requestId, userId);

            if (!success) {
                return reply.status(400).send({ error: 'Could not resolve request' });
            }

            return reply.send({ success: true, approved });
        }
    );
}
