/**
 * WebSocket Connection Registry
 *
 * Gestisce connessioni WebSocket attive per permettere
 * notifiche push a utenti specifici.
 */

import { WebSocket } from 'ws';
import type { WSMessage, MonitorAlertData, MonitorUpdateData } from '@persan/shared';

// Connessione con metadata utente
interface ConnectedClient {
    socket: WebSocket;
    sessionIds: Set<string>; // SOTA 2026: supporta multiplexing 1:N
    userId: string; // Default "default" fino a implementazione auth
    connectedAt: number;
}

class ConnectionRegistry {
    // Mappa socket fisico -> client connesso
    private socketToClient: Map<WebSocket, ConnectedClient> = new Map();
    // Mappa sessionId logic -> socket fisico (per lookup veloce)
    private sessionToSocket: Map<string, WebSocket> = new Map();
    private sessionToUser: Map<string, string> = new Map();

    /**
     * Registra una nuova connessione WebSocket
     */
    register(sessionId: string, socket: WebSocket, userId: string = 'default'): void {
        const client: ConnectedClient = {
            socket,
            sessionIds: new Set([sessionId]),
            userId,
            connectedAt: Date.now(),
        };
        this.socketToClient.set(socket, client);
        this.sessionToSocket.set(sessionId, socket);
        this.sessionToUser.set(sessionId, userId);
    }

    /**
     * Aggiunge un alias (nuova sessione) a un socket esistente
     * Fondamentale per il multiplexing senza riconnessione.
     */
    addAlias(socket: WebSocket, sessionId: string): void {
        const client = this.socketToClient.get(socket);
        if (client) {
            client.sessionIds.add(sessionId);
            this.sessionToSocket.set(sessionId, socket);
            this.sessionToUser.set(sessionId, client.userId);
            console.log(`[ConnectionRegistry] Alias registered: session ${sessionId} added to existing socket.`);
        }
    }

    /**
     * Rimuove una connessione o una singola sessione
     */
    unregister(sessionId: string): void {
        const socket = this.sessionToSocket.get(sessionId);
        if (socket) {
            const client = this.socketToClient.get(socket);
            if (client) {
                client.sessionIds.delete(sessionId);
                // Se non ci sono più sessioni attive su questo socket, pulisci tutto
                if (client.sessionIds.size === 0) {
                    this.socketToClient.delete(socket);
                }
            }
            this.sessionToSocket.delete(sessionId);
        }
        this.sessionToUser.delete(sessionId);
    }

    /**
     * Ottiene una connessione per sessionId
     */
    get(sessionId: string): ConnectedClient | undefined {
        const socket = this.sessionToSocket.get(sessionId);
        return socket ? this.socketToClient.get(socket) : undefined;
    }

    /**
     * Trova tutte le connessioni fisiche uniche per un userId
     */
    getByUserId(userId: string): ConnectedClient[] {
        return Array.from(this.socketToClient.values()).filter(
            (c) => c.userId === userId && c.socket.readyState === WebSocket.OPEN
        );
    }

    /**
     * Invia messaggio a tutte le connessioni di un utente
     */
    sendToUser(userId: string, message: WSMessage): number {
        const clients = this.getByUserId(userId);
        let sent = 0;
        for (const client of clients) {
            try {
                client.socket.send(JSON.stringify(message));
                sent++;
            } catch (error) {
                console.error(`Failed to send to user ${userId}:`, error);
            }
        }
        return sent;
    }

    /**
     * Invia messaggio a una specifica sessione logica
     */
    sendToSession(sessionId: string, message: WSMessage): boolean {
        const socket = this.sessionToSocket.get(sessionId);

        console.log(`[Registry] 📨 sendToSession:`, {
            sessionId,
            messageType: message.type,
            hasSocket: !!socket,
            socketState: socket?.readyState,
            timestamp: new Date().toISOString()
        });

        if (!socket) {
            console.warn(`[Registry] ⚠️ No socket mapping for session ${sessionId}`);
            return false;
        }

        if (socket.readyState !== WebSocket.OPEN) {
            console.warn(`[Registry] ⚠️ Socket not OPEN (readyState: ${socket.readyState})`);
            return false;
        }

        try {
            // DEBUG: Log thinking message size to debug 524-char limit
            const msgStr = JSON.stringify(message);
            const isThinking = message.type === 'chat:response' && (message.data as any)?.type === 'thinking';
            const content = (message.data as any)?.content || '';
            if (isThinking) {
                console.log(`[Registry] 🧠 Thinking message: ${content.length} chars, preview: ${content.substring(0, 50)}...`);
            }
            socket.send(msgStr);
            console.log(`[Registry] ✅ Delivered ${message.type} to session ${sessionId}`);
            return true;
        } catch (error) {
            console.error(`[Registry] ❌ Send failed for session ${sessionId}:`, error);
            return false;
        }
    }

    /**
     * Broadcast a tutte le connessioni fisiche
     */
    broadcast(message: WSMessage): number {
        let sent = 0;
        for (const client of this.socketToClient.values()) {
            if (client.socket.readyState === WebSocket.OPEN) {
                try {
                    client.socket.send(JSON.stringify(message));
                    sent++;
                } catch (error) {
                    console.error(`Broadcast failed:`, error);
                }
            }
        }
        return sent;
    }

    /**
     * Statistiche connessioni
     */
    getStats(): { totalConnections: number; totalSessions: number; byUser: Record<string, number> } {
        const byUser: Record<string, number> = {};
        for (const client of this.socketToClient.values()) {
            if (client.socket.readyState === WebSocket.OPEN) {
                byUser[client.userId] = (byUser[client.userId] || 0) + 1;
            }
        }
        return {
            totalConnections: this.socketToClient.size,
            totalSessions: this.sessionToSocket.size,
            byUser,
        };
    }

    /**
     * Invia alert monitor a un utente
     */
    sendMonitorAlert(userId: string, alert: MonitorAlertData): number {
        const message: WSMessage<MonitorAlertData> = {
            type: 'monitor:alert',
            data: alert,
            timestamp: Date.now(),
        };
        return this.sendToUser(userId, message);
    }

    /**
     * Invia aggiornamento stato monitor a un utente
     */
    sendMonitorUpdate(userId: string, update: MonitorUpdateData): number {
        const message: WSMessage<MonitorUpdateData> = {
            type: 'monitor:update',
            data: update,
            timestamp: Date.now(),
        };
        return this.sendToUser(userId, message);
    }
}

// Singleton export
export const connectionRegistry = new ConnectionRegistry();
