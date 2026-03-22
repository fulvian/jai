/**
 * HITL Approval Queue
 * 
 * Gestisce richieste di approvazione Human-in-the-Loop per azioni
 * che richiedono conferma utente prima dell'esecuzione.
 * 
 * Questo è il cuore del sistema di sicurezza che differenzia PersAn
 * da OpenClaw, aggiungendo controllo umano sulle azioni autonome.
 */

import { connectionRegistry } from '../websocket/registry.js';
import type { WSMessage } from '@persan/shared';

// =============================================================================
// Types
// =============================================================================

export type ApprovalStatus = 'pending' | 'approved' | 'denied' | 'expired' | 'timeout';

export interface ApprovalRequest {
    /** Unique request ID */
    id: string;
    /** User ID */
    userId: string;
    /** Session ID (WebSocket) */
    sessionId: string;
    /** Tool/action name */
    tool: string;
    /** Tool arguments */
    args: Record<string, unknown>;
    /** Human-readable description */
    message: string;
    /** Urgency level */
    urgency: 'low' | 'medium' | 'high';
    /** Current status */
    status: ApprovalStatus;
    /** Creation timestamp */
    createdAt: Date;
    /** Expiration timestamp */
    expiresAt: Date;
    /** Resolution timestamp */
    resolvedAt?: Date;
    /** Callback on resolution */
    onResolve?: (approved: boolean) => void | Promise<void>;
}

export interface ApprovalResponse {
    requestId: string;
    approved: boolean;
    userId: string;
    resolvedAt: Date;
}

// =============================================================================
// Configuration
// =============================================================================

const DEFAULT_TIMEOUT_MS = 5 * 60 * 1000; // 5 minuti
const CLEANUP_INTERVAL_MS = 60 * 1000; // 1 minuto

// =============================================================================
// Approval Queue
// =============================================================================

/**
 * Gestisce la coda delle richieste di approvazione.
 * 
 * Flusso:
 * 1. Agent vuole eseguire azione CONFIRM
 * 2. ApprovalQueue.request() crea richiesta e notifica user
 * 3. User approva/nega via WebSocket
 * 4. Callback viene invocato con risultato
 */
export class ApprovalQueue {
    private pending = new Map<string, ApprovalRequest>();
    private cleanupInterval: NodeJS.Timeout | null = null;

    constructor(private timeoutMs = DEFAULT_TIMEOUT_MS) {
        this.startCleanup();
    }

    /**
     * Crea una richiesta di approvazione.
     * 
     * @param userId - ID utente
     * @param sessionId - Session WebSocket
     * @param tool - Nome tool/azione
     * @param args - Argomenti tool
     * @param message - Messaggio human-readable
     * @param urgency - Urgenza
     * @returns Promise che si risolve con true/false
     */
    async request(
        userId: string,
        sessionId: string,
        tool: string,
        args: Record<string, unknown>,
        message: string,
        urgency: 'low' | 'medium' | 'high' = 'medium',
    ): Promise<boolean> {
        const id = crypto.randomUUID();
        const now = new Date();

        return new Promise<boolean>((resolve) => {
            const request: ApprovalRequest = {
                id,
                userId,
                sessionId,
                tool,
                args,
                message,
                urgency,
                status: 'pending',
                createdAt: now,
                expiresAt: new Date(now.getTime() + this.timeoutMs),
                onResolve: (approved) => {
                    resolve(approved);
                },
            };

            this.pending.set(id, request);

            // Notifica user via WebSocket
            this.notifyUser(request).catch((err) => {
                console.error('Failed to notify user for approval', { id, error: err });
            });

            console.log('Approval request created', { id, tool, userId });
        });
    }

    /**
     * Approva una richiesta.
     */
    async approve(requestId: string, userId: string): Promise<boolean> {
        return this.resolve(requestId, userId, true);
    }

    /**
     * Nega una richiesta.
     */
    async deny(requestId: string, userId: string): Promise<boolean> {
        return this.resolve(requestId, userId, false);
    }

    /**
     * Risolve una richiesta.
     */
    private async resolve(
        requestId: string,
        userId: string,
        approved: boolean,
    ): Promise<boolean> {
        const request = this.pending.get(requestId);

        if (!request) {
            console.warn('Approval request not found', { requestId });
            return false;
        }

        if (request.userId !== userId) {
            console.warn('User mismatch for approval', { requestId, expectedUser: request.userId, actualUser: userId });
            return false;
        }

        if (request.status !== 'pending') {
            console.warn('Approval request already resolved', { requestId, status: request.status });
            return false;
        }

        // Aggiorna stato
        request.status = approved ? 'approved' : 'denied';
        request.resolvedAt = new Date();

        // Invoca callback
        if (request.onResolve) {
            try {
                await request.onResolve(approved);
            } catch (error) {
                console.error('Error in approval callback', { requestId, error });
            }
        }

        // Rimuovi dalla coda
        this.pending.delete(requestId);

        // Notifica risoluzione
        this.notifyResolution(request, approved).catch(() => { });

        console.log('Approval request resolved', { requestId, approved, tool: request.tool });

        return true;
    }

    /**
     * Ottiene richieste pendenti per un utente.
     */
    getPending(userId: string): ApprovalRequest[] {
        return Array.from(this.pending.values())
            .filter((r) => r.userId === userId && r.status === 'pending');
    }

    /**
     * Ottiene una richiesta specifica.
     */
    get(requestId: string): ApprovalRequest | undefined {
        return this.pending.get(requestId);
    }

    /**
     * Notifica user via WebSocket.
     */
    private async notifyUser(request: ApprovalRequest): Promise<void> {
        const clients = connectionRegistry.getByUserId(request.userId);

        if (!clients || clients.length === 0) {
            console.warn('No WebSocket connection for user', { userId: request.userId });
            return;
        }

        const message: WSMessage = {
            type: 'approval:request',
            data: {
                id: request.id,
                tool: request.tool,
                args: request.args,
                message: request.message,
                urgency: request.urgency,
                expiresAt: request.expiresAt.toISOString(),
            },
            timestamp: Date.now(),
        };

        // Invia a tutte le connessioni dell'utente
        for (const client of clients) {
            client.socket.send(JSON.stringify(message));
        }
    }

    /**
     * Notifica risoluzione.
     */
    private async notifyResolution(request: ApprovalRequest, approved: boolean): Promise<void> {
        const clients = connectionRegistry.getByUserId(request.userId);

        if (!clients || clients.length === 0) return;

        const message: WSMessage = {
            type: 'approval:resolved',
            data: {
                id: request.id,
                approved,
                tool: request.tool,
            },
            timestamp: Date.now(),
        };

        for (const client of clients) {
            client.socket.send(JSON.stringify(message));
        }
    }

    /**
     * Avvia cleanup periodico delle richieste scadute.
     */
    private startCleanup(): void {
        this.cleanupInterval = setInterval(() => {
            const now = new Date();
            let expired = 0;

            for (const [id, request] of this.pending) {
                if (request.status === 'pending' && request.expiresAt < now) {
                    request.status = 'expired';

                    // Risolvi come negato
                    if (request.onResolve) {
                        request.onResolve(false);
                    }

                    this.pending.delete(id);
                    expired++;
                }
            }

            if (expired > 0) {
                console.log('Approval requests expired', { count: expired });
            }
        }, CLEANUP_INTERVAL_MS);
    }

    /**
     * Ferma il cleanup.
     */
    stop(): void {
        if (this.cleanupInterval) {
            clearInterval(this.cleanupInterval);
        }
    }

    /**
     * Statistiche.
     */
    getStats(): { pending: number; total: number } {
        const pending = Array.from(this.pending.values())
            .filter((r) => r.status === 'pending').length;
        return { pending, total: this.pending.size };
    }
}

// =============================================================================
// Singleton
// =============================================================================

let _approvalQueue: ApprovalQueue | null = null;

export function getApprovalQueue(): ApprovalQueue {
    if (!_approvalQueue) {
        _approvalQueue = new ApprovalQueue();
    }
    return _approvalQueue;
}
