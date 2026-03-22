/**
 * Telegram Channel Adapter
 * 
 * Integrates with Telegram Bot API using grammy library.
 * Receives messages and routes them through ChannelManager.
 */

import { Bot, Context, BotError, GrammyError, HttpError } from 'grammy';
import type { ChannelAdapter, IncomingMessage } from '../manager.js';
import type { Channel } from '@persan/shared';

export interface TelegramConfig {
    botToken: string;
    allowedUsers?: string[]; // Optional: whitelist of usernames
    onMessage: (message: IncomingMessage) => Promise<string>;
}

export class TelegramAdapter implements ChannelAdapter {
    readonly name: Channel = 'telegram';
    private bot: Bot;
    private config: TelegramConfig;
    private connected = false;

    constructor(config: TelegramConfig) {
        this.config = config;
        this.bot = new Bot(config.botToken);
        this.setupHandlers();
    }

    private setupHandlers(): void {
        // Global middleware to log ALL incoming updates
        this.bot.use(async (ctx, next) => {
            const updateType = Object.keys(ctx.update).filter(k => k !== 'update_id')[0];
            console.log(`📥 Telegram update received: type=${updateType}, from=${ctx.from?.username}`);
            await next();
        });

        // Start command
        this.bot.command('start', async (ctx: Context) => {
            const username = ctx.from?.username || ctx.from?.first_name || 'Utente';
            await ctx.reply(
                `👋 Ciao ${username}!\n\n` +
                `Sono PersAn, il tuo assistente AI powered by Me4BrAIn.\n\n` +
                `Puoi chiedermi qualsiasi cosa: meteo, finanza, ricerche, calendario, email...\n\n` +
                `Scrivi semplicemente il tuo messaggio! 🚀`
            );
        });

        // Help command
        this.bot.command('help', async (ctx: Context) => {
            await ctx.reply(
                `📖 **Comandi disponibili:**\n\n` +
                `/start - Inizia la conversazione\n` +
                `/help - Mostra questo messaggio\n` +
                `/status - Verifica lo stato del servizio\n\n` +
                `💡 **Esempi di domande:**\n` +
                `• "Che tempo fa a Roma?"\n` +
                `• "Analizza AAPL"\n` +
                `• "Leggimi le email di oggi"\n` +
                `• "Cerca paper su machine learning"`,
                { parse_mode: 'Markdown' }
            );
        });

        // Status command
        this.bot.command('status', async (ctx: Context) => {
            await ctx.reply(`✅ PersAn è online e funzionante!\n⏱️ ${new Date().toLocaleString('it-IT')}`);
        });

        // Text messages
        this.bot.on('message:text', async (ctx: Context) => {
            const userId = ctx.from?.id?.toString();
            const username = ctx.from?.username;
            const text = ctx.message?.text;

            console.log(`📨 Telegram message received: user=${username} (${userId}), text="${text?.substring(0, 50)}..."`);

            if (!userId || !text) return;

            // Optional: check whitelist
            if (this.config.allowedUsers && this.config.allowedUsers.length > 0) {
                if (username && !this.config.allowedUsers.includes(username)) {
                    await ctx.reply('⛔ Non sei autorizzato a usare questo bot.');
                    return;
                }
            }

            // Show typing indicator with keepalive for long queries
            await ctx.replyWithChatAction('typing');
            // Refresh typing every 4s (Telegram clears it after 5s)
            const typingInterval = setInterval(async () => {
                try { await ctx.replyWithChatAction('typing'); } catch { /* ignore */ }
            }, 4000);

            try {
                const response = await this.config.onMessage({
                    channel: 'telegram',
                    userId,
                    content: text,
                });

                clearInterval(typingInterval);

                // Send response with robust Markdown handling
                console.log(`[TelegramAdapter] Sending response to user ${userId}...`);
                await this.sendSafeReply(ctx, response);
                console.log(`[TelegramAdapter] Response sent successfully.`);
            } catch (error) {
                clearInterval(typingInterval);
                console.error('Telegram message handler error:', error);
                await ctx.reply('❌ Si è verificato un errore. Riprova più tardi.');
            }
        });

        // Error handler with proper typing
        this.bot.catch((err: BotError) => {
            const ctx = err.ctx;
            const e = err.error;

            console.error(`Error while handling update ${ctx.update.update_id}:`);

            if (e instanceof GrammyError) {
                console.error('Error in request:', e.description);
            } else if (e instanceof HttpError) {
                console.error('Could not contact Telegram:', e);
            } else {
                console.error('Unknown error:', e);
            }
        });
    }

    /**
     * Safely send a reply with robust Markdown handling.
     * Uses a 3-tier fallback strategy:
     * 1. Try original Markdown
     * 2. Try sanitized Markdown (escape problematic chars)
     * 3. Fall back to plain text
     */
    private async sendSafeReply(ctx: Context, response: string): Promise<void> {
        const maxLength = 4096;
        const chunks = response.length <= maxLength
            ? [response]
            : this.splitMessage(response, maxLength);

        for (const chunk of chunks) {
            // Strategy 1: Try original with Markdown
            try {
                await ctx.reply(chunk, { parse_mode: 'Markdown' });
                continue;
            } catch (error) {
                console.log('⚠️ Markdown parse failed, trying sanitized version...');
            }

            // Strategy 2: Try sanitized Markdown
            try {
                const sanitized = this.sanitizeMarkdown(chunk);
                await ctx.reply(sanitized, { parse_mode: 'Markdown' });
                continue;
            } catch (error) {
                console.log('⚠️ Sanitized Markdown failed, falling back to plain text...');
            }

            // Strategy 3: Plain text fallback (strip all Markdown)
            try {
                const plainText = this.stripMarkdown(chunk);
                await ctx.reply(plainText);
            } catch (error) {
                console.error('❌ Failed to send message even as plain text:', error);
                // Last resort: send error message
                await ctx.reply('❌ Errore nell\'invio del messaggio. Il contenuto potrebbe essere troppo lungo o contenere caratteri non supportati.');
            }
        }
    }

    /**
     * Sanitize Markdown for Telegram's strict parser.
     * Escapes problematic characters while preserving basic formatting.
     */
    private sanitizeMarkdown(text: string): string {
        // Fix common Markdown issues that cause Telegram parse errors:

        // 1. Balance asterisks (bold/italic)
        let result = this.balanceMarkdownDelimiters(text, '*');

        // 2. Balance underscores (italic/bold)
        result = this.balanceMarkdownDelimiters(result, '_');

        // 3. Balance backticks (code)
        result = this.balanceMarkdownDelimiters(result, '`');

        // 4. Fix unmatched brackets in links [text](url)
        result = this.fixBrokenLinks(result);

        // 5. Escape special characters that aren't part of formatting
        // Only escape if they appear to be problematic (mid-word)
        result = result.replace(/(\w)_(\w)/g, '$1\\_$2');

        return result;
    }

    /**
     * Balance Markdown delimiters (*, _, `) by removing orphans.
     */
    private balanceMarkdownDelimiters(text: string, delimiter: string): string {
        const escapedDelimiter = delimiter.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(escapedDelimiter, 'g');
        const matches = text.match(regex);

        if (!matches) return text;

        // If odd number of delimiters, remove/escape the last one
        if (matches.length % 2 !== 0) {
            const lastIndex = text.lastIndexOf(delimiter);
            return text.substring(0, lastIndex) + '\\' + delimiter + text.substring(lastIndex + 1);
        }

        return text;
    }

    /**
     * Fix broken Markdown links [text](url)
     */
    private fixBrokenLinks(text: string): string {
        // Find unmatched [ or ]
        let bracketCount = 0;
        let result = '';

        for (const char of text) {
            if (char === '[') bracketCount++;
            else if (char === ']') bracketCount--;

            // If we have unbalanced closing bracket, escape it
            if (bracketCount < 0) {
                result += '\\]';
                bracketCount = 0;
            } else {
                result += char;
            }
        }

        // If we have unbalanced opening brackets, escape them
        if (bracketCount > 0) {
            result = result.replace(/\[/g, (match, offset) => {
                // Only escape if not properly closed
                const remaining = result.substring(offset + 1);
                if (!remaining.includes(']')) {
                    return '\\[';
                }
                return match;
            });
        }

        return result;
    }

    /**
     * Strip all Markdown formatting for plain text fallback.
     */
    private stripMarkdown(text: string): string {
        return text
            // Remove headers
            .replace(/^#{1,6}\s+/gm, '')
            // Remove bold/italic (both * and _)
            .replace(/\*\*(.+?)\*\*/g, '$1')
            .replace(/\*(.+?)\*/g, '$1')
            .replace(/__(.+?)__/g, '$1')
            .replace(/_(.+?)_/g, '$1')
            // Remove inline code
            .replace(/`(.+?)`/g, '$1')
            // Remove code blocks
            .replace(/```[\s\S]*?```/g, '')
            // Convert links to text (url)
            .replace(/\[(.+?)\]\((.+?)\)/g, '$1 ($2)')
            // Remove any remaining Markdown special chars
            .replace(/[*_`\[\]]/g, '')
            .trim();
    }

    private splitMessage(text: string, maxLength: number): string[] {
        const chunks: string[] = [];
        let remaining = text;

        while (remaining.length > 0) {
            if (remaining.length <= maxLength) {
                chunks.push(remaining);
                break;
            }

            // Find a good split point (newline or space)
            let splitIndex = remaining.lastIndexOf('\n', maxLength);
            if (splitIndex === -1 || splitIndex < maxLength * 0.5) {
                splitIndex = remaining.lastIndexOf(' ', maxLength);
            }
            if (splitIndex === -1) {
                splitIndex = maxLength;
            }

            chunks.push(remaining.slice(0, splitIndex));
            remaining = remaining.slice(splitIndex).trim();
        }

        return chunks;
    }

    async connect(): Promise<void> {
        if (this.connected) return;

        try {
            console.log('🚀 Starting Telegram polling...');

            // 1. Verify bot token and get bot info
            const botInfo = await this.bot.api.getMe();
            console.log(`✅ Bot info: @${botInfo.username} (${botInfo.id})`);

            // 2. Delete any existing webhook (conflicts with polling)
            await this.bot.api.deleteWebhook({ drop_pending_updates: true });
            console.log('🧹 Cleared any existing webhook');

            // 3. Start polling (don't await - it runs forever)
            // Using a separate promise to properly handle the background polling
            const pollingPromise = this.bot.start({
                drop_pending_updates: false, // We already dropped via deleteWebhook
                onStart: (info) => {
                    console.log(`🤖 Telegram bot @${info.username} started successfully`);
                    this.connected = true;
                },
            });

            // Handle polling errors in background
            pollingPromise.catch((error) => {
                console.error('❌ Telegram polling error:', error);
                this.connected = false;
            });

            // Give polling a moment to establish
            await new Promise(resolve => setTimeout(resolve, 1000));

            if (this.connected) {
                console.log('✅ Telegram polling established');
            }
        } catch (error) {
            console.error('❌ Failed to start Telegram bot:', error);
            throw error;
        }
    }

    async disconnect(): Promise<void> {
        if (!this.connected) return;
        await this.bot.stop();
        this.connected = false;
    }

    async sendMessage(userId: string, content: string): Promise<void> {
        const chatId = parseInt(userId, 10);
        if (isNaN(chatId)) {
            console.error('Invalid Telegram user ID:', userId);
            return;
        }
        await this.bot.api.sendMessage(chatId, content, { parse_mode: 'Markdown' });
    }

    isConnected(): boolean {
        return this.connected;
    }
}
