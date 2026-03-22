/**
 * WhatsApp Channel Adapter
 * 
 * Integrates with WhatsApp using baileys library.
 * Uses multi-device web client protocol.
 */

import makeWASocket, {
    DisconnectReason,
    useMultiFileAuthState,
    fetchLatestBaileysVersion,
    WASocket,
    proto,
    ConnectionState,
    BaileysEventMap,
} from '@whiskeysockets/baileys';
import { Boom } from '@hapi/boom';
import * as fs from 'fs';
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const qrcode = require('qrcode-terminal');
import type { ChannelAdapter, IncomingMessage } from '../manager.js';
import type { Channel } from '@persan/shared';

export interface WhatsAppConfig {
    authDir: string; // Directory for auth state
    allowedNumbers?: string[]; // Optional: whitelist of phone numbers
    onMessage: (message: IncomingMessage) => Promise<string>;
    onQRCode?: (qr: string) => void; // Callback when QR needs scanning
}

export class WhatsAppAdapter implements ChannelAdapter {
    readonly name: Channel = 'whatsapp';
    private socket: WASocket | null = null;
    private config: WhatsAppConfig;
    private connected = false;
    private saveCreds: (() => Promise<void>) | null = null;

    constructor(config: WhatsAppConfig) {
        this.config = config;

        // Ensure auth directory exists
        if (!fs.existsSync(config.authDir)) {
            fs.mkdirSync(config.authDir, { recursive: true });
        }
    }

    async connect(): Promise<void> {
        if (this.connected) return;

        const { state, saveCreds } = await useMultiFileAuthState(this.config.authDir);
        this.saveCreds = saveCreds;

        // Fetch latest WhatsApp version to avoid 405 errors
        let version: [number, number, number] | undefined;
        try {
            const latestVersion = await fetchLatestBaileysVersion();
            version = latestVersion.version;
            console.log(`📱 WhatsApp: using version ${version.join('.')}`);
        } catch (err) {
            // Fallback to known working version (Feb 2026)
            version = [2, 3000, 1027934701];
            console.log(`📱 WhatsApp: using fallback version ${version.join('.')}`);
        }

        this.socket = makeWASocket({
            auth: state,
            version,
            browser: ['PersAn', 'Chrome', '121.0.0'],
            syncFullHistory: false,
        });

        this.setupEventHandlers();
    }

    private setupEventHandlers(): void {
        if (!this.socket) return;

        // Connection updates with proper typing
        this.socket.ev.on('connection.update', async (update: Partial<ConnectionState>) => {
            const { connection, lastDisconnect, qr } = update;

            if (qr) {
                console.log('\\n📱 WhatsApp QR Code - Scansiona con il tuo telefono:\\n');
                qrcode.generate(qr, { small: true });
                console.log('\\n👆 Apri WhatsApp > Impostazioni > Dispositivi collegati > Collega dispositivo\\n');
                this.config.onQRCode?.(qr);
            }

            if (connection === 'close') {
                const error = lastDisconnect?.error as Boom | undefined;
                const statusCode = error?.output?.statusCode;
                const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

                console.log('WhatsApp disconnected, reason:', statusCode);

                if (shouldReconnect) {
                    console.log('Attempting to reconnect...');
                    await this.connect();
                } else {
                    console.log('Logged out. Delete auth folder and scan QR again.');
                    this.connected = false;
                }
            }

            if (connection === 'open') {
                console.log('✅ WhatsApp connected successfully');
                this.connected = true;
            }
        });

        // Save credentials on update
        this.socket.ev.on('creds.update', async () => {
            await this.saveCreds?.();
        });

        // Handle incoming messages with proper typing
        type MessagesUpsertEvent = BaileysEventMap['messages.upsert'];
        this.socket.ev.on('messages.upsert', async (event: MessagesUpsertEvent) => {
            const { messages, type } = event;
            if (type !== 'notify') return;

            for (const msg of messages) {
                await this.handleMessage(msg);
            }
        });
    }

    private async handleMessage(msg: proto.IWebMessageInfo): Promise<void> {
        // Ignore non-text messages for now
        const text = msg.message?.conversation ||
            msg.message?.extendedTextMessage?.text;

        if (!text || !msg.key?.remoteJid || msg.key?.fromMe) return;

        const userId = msg.key.remoteJid;
        const phoneNumber = userId.replace('@s.whatsapp.net', '');

        // Optional: check whitelist
        if (this.config.allowedNumbers && this.config.allowedNumbers.length > 0) {
            if (!this.config.allowedNumbers.includes(phoneNumber)) {
                await this.sendMessage(userId, '⛔ Non sei autorizzato a usare questo servizio.');
                return;
            }
        }

        // Show typing indicator
        await this.socket?.sendPresenceUpdate('composing', userId);

        try {
            const response = await this.config.onMessage({
                channel: 'whatsapp',
                userId: phoneNumber,
                content: text,
            });

            await this.sendMessage(userId, response);
        } catch (error) {
            console.error('WhatsApp message handler error:', error);
            await this.sendMessage(userId, '❌ Si è verificato un errore. Riprova più tardi.');
        } finally {
            await this.socket?.sendPresenceUpdate('available', userId);
        }
    }

    async disconnect(): Promise<void> {
        if (!this.connected || !this.socket) return;
        this.socket.end(undefined);
        this.socket = null;
        this.connected = false;
    }

    async sendMessage(userId: string, content: string): Promise<void> {
        if (!this.socket || !this.connected) {
            console.error('WhatsApp not connected');
            return;
        }

        // Format JID if needed
        const jid = userId.includes('@') ? userId : `${userId}@s.whatsapp.net`;

        await this.socket.sendMessage(jid, { text: content });
    }

    isConnected(): boolean {
        return this.connected;
    }
}
