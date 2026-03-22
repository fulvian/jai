/**
 * CRITICAL: Override undici's default headersTimeout (300s = 5 min) BEFORE any fetch calls.
 * Without this, Node.js kills ALL fetch connections after 5 min if response headers
 * haven't arrived. Me4BrAIn queries can take 7-10 min for complex analysis.
 */
import 'dotenv/config';
import { Agent, setGlobalDispatcher } from 'undici';
setGlobalDispatcher(new Agent({
    headersTimeout: 0,         // No timeout waiting for response headers
    bodyTimeout: 0,            // No timeout waiting for response body
    keepAliveTimeout: 1_800_000, // 30 min — aligned with engine client max timeout
}));

import { buildApp } from './app.js';
import { config } from './config/config.service.js';

// Validate and load configuration at startup (fail-fast)
const env = config.getAll();
console.log(`🚀 Starting PersAn Gateway`);
console.log(`📋 Environment: ${env.NODE_ENV}`);
console.log(`🔌 Port: ${env.PORT}`);
console.log(`📡 Me4BrAIn URL: ${env.ME4BRAIN_URL}`);
console.log(`💾 Redis URL: ${env.REDIS_URL.replace(/:\/\/.*@/, '://***@')}`);
console.log(`📊 Log Level: ${env.LOG_LEVEL}`);

const PORT = env.PORT;
const HOST = process.env.HOST ?? '0.0.0.0';

async function main() {
    const app = await buildApp();

    try {
        await app.listen({ port: PORT, host: HOST });
        app.log.info(`🚀 PersAn Gateway running on http://${HOST}:${PORT}`);
        app.log.info(`📡 WebSocket available at ws://${HOST}:${PORT}/ws`);
    } catch (err) {
        app.log.error(err);
        process.exit(1);
    }
}

// Graceful shutdown
async function shutdown(signal: string) {
    console.log(`👋 Received ${signal}, shutting down gracefully...`);

    // Import channelManager dynamically to avoid circular deps
    const { channelManager } = await import('./channels/index.js');

    // Disconnect all channels
    await channelManager.disconnectAll();

    console.log('✅ All channels disconnected');
    process.exit(0);
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

main();
