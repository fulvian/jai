/**
 * Channel Manager
 * 
 * Orchestrates multiple communication channels (Telegram, WhatsApp, etc.)
 * and routes messages through a unified interface.
 */

import { FastifyInstance } from 'fastify';
import type { Channel } from '@persan/shared';
import { SessionManager } from '../services/session.js';
import { Me4BrAInClient } from '@persan/me4brain-client';

export interface ChannelAdapter {
    name: Channel;
    connect(): Promise<void>;
    disconnect(): Promise<void>;
    sendMessage(userId: string, content: string): Promise<void>;
    isConnected(): boolean;
}

export interface IncomingMessage {
    channel: Channel;
    userId: string;
    content: string;
    attachments?: Buffer[];
    replyTo?: string;
}

export class ChannelManager {
    private adapters = new Map<Channel, ChannelAdapter>();
    private sessions: SessionManager;
    private me4brain: Me4BrAInClient;
    private fastifyApp: FastifyInstance | null = null;

    constructor() {
        this.sessions = new SessionManager();
        this.me4brain = new Me4BrAInClient({
            baseUrl: process.env.ME4BRAIN_URL ?? 'http://localhost:8000/v1',
        });
    }

    register(adapter: ChannelAdapter): void {
        this.adapters.set(adapter.name, adapter);
        this.log('info', `📡 Registered channel: ${adapter.name}`);
    }

    async connectAll(): Promise<void> {
        const promises: Promise<void>[] = [];

        for (const [name, adapter] of this.adapters) {
            this.log('info', `🔌 Connecting ${name}...`);
            promises.push(
                adapter.connect().then(() => {
                    this.log('info', `✅ ${name} connected`);
                }).catch((err: Error) => {
                    this.log('error', `❌ Failed to connect ${name}:`, err);
                })
            );
        }

        await Promise.allSettled(promises);
    }

    async disconnectAll(): Promise<void> {
        for (const [name, adapter] of this.adapters) {
            try {
                await adapter.disconnect();
                this.log('info', `👋 ${name} disconnected`);
            } catch (err) {
                this.log('error', `Failed to disconnect ${name}:`, err);
            }
        }
    }

    async handleIncoming(message: IncomingMessage): Promise<string> {
        // Get or create session
        const sessionKey = `${message.channel}:${message.userId}`;
        let session = await this.sessions.get(sessionKey);

        if (!session) {
            console.log(`[ChannelManager] Creating new session for ${sessionKey}`);
            session = await this.sessions.create(message.channel, sessionKey);
        } else {
            console.log(`[ChannelManager] Using existing session for ${sessionKey}`);
        }

        // Update session activity
        await this.sessions.update(session.id, { state: 'processing' });

        try {
            // Query Me4BrAIn
            console.log(`[ChannelManager] Querying Me4BrAIn for session ${session.id}: "${message.content.slice(0, 50)}..."`);
            const result = await this.me4brain.engine.query(message.content);
            console.log(`[ChannelManager] Me4BrAIn response received (latency: ${result.totalLatencyMs}ms)`);

            await this.sessions.update(session.id, { state: 'idle' });

            return result.answer;
        } catch (error) {
            await this.sessions.update(session.id, { state: 'error' });
            this.log('error', 'Me4BrAIn query failed:', error);
            return 'Mi dispiace, si è verificato un errore. Riprova più tardi.';
        }
    }

    async sendResponse(channel: Channel, userId: string, content: string): Promise<void> {
        const adapter = this.adapters.get(channel);

        if (!adapter) {
            this.log('error', `No adapter registered for channel: ${channel}`);
            return;
        }

        if (!adapter.isConnected()) {
            this.log('error', `Adapter ${channel} is not connected`);
            return;
        }

        await adapter.sendMessage(userId, content);
    }

    getStatus(): Record<Channel, boolean> {
        const status: Partial<Record<Channel, boolean>> = {};

        for (const [name, adapter] of this.adapters) {
            status[name] = adapter.isConnected();
        }

        return status as Record<Channel, boolean>;
    }

    setApp(app: FastifyInstance): void {
        this.fastifyApp = app;
    }

    private log(level: 'info' | 'error' | 'warn', message: string, data?: unknown): void {
        if (this.fastifyApp) {
            this.fastifyApp.log[level](data, message);
        } else {
            if (level === 'error') {
                console.error(message, data);
            } else {
                console.log(message, data ?? '');
            }
        }
    }
}

// Singleton instance
export const channelManager = new ChannelManager();
