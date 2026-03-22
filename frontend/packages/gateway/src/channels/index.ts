/**
 * Channel Exports
 */

export { ChannelManager, channelManager, type ChannelAdapter, type IncomingMessage } from './manager.js';
export { TelegramAdapter, type TelegramConfig } from './telegram/index.js';
export { WhatsAppAdapter, type WhatsAppConfig } from './whatsapp/index.js';
