/**
 * useApproval Hook
 * 
 * Gestisce la coda delle approvazioni HITL via WebSocket.
 * Uses GatewayClient directly for typed send/receive of approval messages.
 */

'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { GatewayClient } from '@/lib/gateway-client';
import { API_CONFIG } from '@/lib/config';
import type { WSMessage } from '@persan/shared';

interface ApprovalRequest {
    id: string;
    tool: string;
    message: string;
    urgency: 'low' | 'medium' | 'high';
    expiresAt: string;
    args?: Record<string, unknown>;
}

interface UseApprovalReturn {
    /** Lista delle richieste pendenti */
    requests: ApprovalRequest[];
    /** Richiesta corrente (prima in coda) */
    currentRequest: ApprovalRequest | null;
    /** Approva una richiesta */
    approve: (requestId: string) => void;
    /** Nega una richiesta */
    deny: (requestId: string) => void;
    /** Numero di richieste pendenti */
    pendingCount: number;
}

export function useApproval(): UseApprovalReturn {
    const [requests, setRequests] = useState<ApprovalRequest[]>([]);
    const clientRef = useRef<GatewayClient | null>(null);

    // Initialize WebSocket client and register approval handlers
    useEffect(() => {
        const client = new GatewayClient({ url: API_CONFIG.websocketUrl });
        clientRef.current = client;
        client.connect();

        // Listen for approval:request events
        const unsubRequest = client.on<ApprovalRequest>('approval:request', (data) => {
            setRequests((prev) => {
                if (prev.some((r) => r.id === data.id)) return prev;
                return [...prev, data];
            });
        });

        // Listen for approval:resolved events (from other device/tab)
        const unsubResolved = client.on<{ id: string }>('approval:resolved', (data) => {
            setRequests((prev) => prev.filter((r) => r.id !== data.id));
        });

        // Listen for approval:ack events (confirmation of our response)
        const unsubAck = client.on<{ requestId: string }>('approval:ack', (data) => {
            setRequests((prev) => prev.filter((r) => r.id !== data.requestId));
        });

        return () => {
            unsubRequest();
            unsubResolved();
            unsubAck();
            client.disconnect();
        };
    }, []);

    // Pulisci richieste scadute
    useEffect(() => {
        const interval = setInterval(() => {
            const now = Date.now();
            setRequests((prev) =>
                prev.filter((r) => new Date(r.expiresAt).getTime() > now)
            );
        }, 5000);

        return () => clearInterval(interval);
    }, []);

    const approve = useCallback((requestId: string) => {
        clientRef.current?.send('approval:response', {
            requestId,
            approved: true,
        });
    }, []);

    const deny = useCallback((requestId: string) => {
        clientRef.current?.send('approval:response', {
            requestId,
            approved: false,
        });
    }, []);

    return {
        requests,
        currentRequest: requests[0] ?? null,
        approve,
        deny,
        pendingCount: requests.length,
    };
}

export default useApproval;
