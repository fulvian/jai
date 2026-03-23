/**
 * E2E Test Suite - PersAn Gateway
 * 
 * Test rigorosi per verificare:
 * 1. Health check HTTP
 * 2. WebSocket connection
 * 3. Session management
 * 4. Chat flow con Me4BrAIn
 * 5. Error handling
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import { spawn, ChildProcess } from 'child_process';
import WebSocket from 'ws';

const GATEWAY_URL = 'http://localhost:3000';
const WS_URL = 'ws://localhost:3000/ws';
const STARTUP_TIMEOUT = 10000;
const TEST_TIMEOUT = 30000;
const RUN_GATEWAY_E2E = process.env.RUN_GATEWAY_E2E === '1';

let gatewayProcess: ChildProcess | null = null;

// Helper: aspetta che il gateway sia pronto
async function waitForGateway(maxWaitMs = STARTUP_TIMEOUT): Promise<boolean> {
    const startTime = Date.now();

    while (Date.now() - startTime < maxWaitMs) {
        try {
            const response = await fetch(`${GATEWAY_URL}/health`);
            if (response.ok) {
                return true;
            }
        } catch {
            // Ignora errori di connessione durante startup
        }
        await new Promise(resolve => setTimeout(resolve, 500));
    }

    return false;
}

// Helper: crea WebSocket con timeout
function createWebSocket(url: string, timeoutMs = 5000): Promise<WebSocket> {
    return new Promise((resolve, reject) => {
        const ws = new WebSocket(url);
        const timeout = setTimeout(() => {
            ws.close();
            reject(new Error(`WebSocket connection timeout after ${timeoutMs}ms`));
        }, timeoutMs);

        ws.on('open', () => {
            clearTimeout(timeout);
            resolve(ws);
        });

        ws.on('error', (error) => {
            clearTimeout(timeout);
            reject(error);
        });
    });
}

// Helper: aspetta messaggio WebSocket
function waitForMessage<T>(ws: WebSocket, timeoutMs = 10000): Promise<T> {
    return new Promise((resolve, reject) => {
        const timeout = setTimeout(() => {
            reject(new Error(`No message received within ${timeoutMs}ms`));
        }, timeoutMs);

        const handler = (data: WebSocket.RawData) => {
            clearTimeout(timeout);
            ws.off('message', handler);
            try {
                const parsed = JSON.parse(data.toString()) as T;
                resolve(parsed);
            } catch (e) {
                reject(new Error(`Failed to parse message: ${data.toString()}`));
            }
        };

        ws.on('message', handler);
    });
}

// NOTE: waitForMessageType removed - use waitForMessage directly

describe.skipIf(!RUN_GATEWAY_E2E)('PersAn Gateway E2E Tests', () => {

    beforeAll(async () => {
        console.log('🚀 Starting Gateway for E2E tests...');

        // Avvia il gateway
        gatewayProcess = spawn('npm', ['run', 'dev'], {
            cwd: process.cwd(),
            stdio: ['ignore', 'pipe', 'pipe'],
            env: {
                ...process.env,
                PORT: '3000',
                LOG_LEVEL: 'warn',
                ME4BRAIN_URL: 'http://localhost:8000/v1',
                REDIS_URL: 'redis://localhost:6389', // Me4BrAIn Redis
            },
        });

        gatewayProcess.stdout?.on('data', (data) => {
            const output = data.toString();
            if (output.includes('ERROR') || output.includes('error')) {
                console.error('Gateway stdout:', output);
            }
        });

        gatewayProcess.stderr?.on('data', (data) => {
            console.error('Gateway stderr:', data.toString());
        });

        // Aspetta che il gateway sia pronto
        const isReady = await waitForGateway(STARTUP_TIMEOUT);
        if (!isReady) {
            throw new Error('Gateway failed to start within timeout');
        }

        console.log('✅ Gateway ready!');
    }, STARTUP_TIMEOUT + 5000);

    afterAll(async () => {
        if (gatewayProcess) {
            console.log('🛑 Stopping Gateway...');
            gatewayProcess.kill('SIGTERM');

            // Aspetta che il processo termini
            await new Promise<void>((resolve) => {
                const timeout = setTimeout(() => {
                    gatewayProcess?.kill('SIGKILL');
                    resolve();
                }, 5000);

                gatewayProcess?.on('exit', () => {
                    clearTimeout(timeout);
                    resolve();
                });
            });

            console.log('✅ Gateway stopped');
        }
    });

    // ==========================================================================
    // TEST 1: Health Check
    // ==========================================================================

    describe('Health Check', () => {
        it('should return healthy status', async () => {
            const response = await fetch(`${GATEWAY_URL}/health`);

            expect(response.status).toBe(200);

            const data = await response.json() as { status: string; timestamp: number; uptime: number };
            expect(data).toHaveProperty('status', 'healthy');
            expect(data).toHaveProperty('timestamp');
            expect(data).toHaveProperty('uptime');
            expect(typeof data.uptime).toBe('number');
        });

        it('should return ready status', async () => {
            const response = await fetch(`${GATEWAY_URL}/ready`);

            expect(response.status).toBe(200);

            const data = await response.json();
            expect(data).toHaveProperty('ready', true);
        });

        it('should return API status with features', async () => {
            const response = await fetch(`${GATEWAY_URL}/api/status`);

            expect(response.status).toBe(200);

            const data = await response.json() as { gateway: string; channels: string[]; features: { websocket: boolean } };
            expect(data).toHaveProperty('gateway', 'persan');
            expect(data).toHaveProperty('channels');
            expect(data.channels).toContain('webchat');
            expect(data).toHaveProperty('features');
            expect(data.features).toHaveProperty('websocket', true);
        });
    });

    // ==========================================================================
    // TEST 2: WebSocket Connection
    // ==========================================================================

    describe('WebSocket Connection', () => {
        it('should establish connection and receive session:init', async () => {
            const ws = await createWebSocket(WS_URL);

            try {
                const initMsg = await waitForMessage<{
                    type: string;
                    data: { sessionId: string };
                    timestamp: number;
                }>(ws);

                expect(initMsg.type).toBe('session:init');
                expect(initMsg.data).toHaveProperty('sessionId');
                expect(typeof initMsg.data.sessionId).toBe('string');
                expect(initMsg.data.sessionId).toMatch(
                    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
                );
                expect(initMsg.timestamp).toBeGreaterThan(0);
            } finally {
                ws.close();
            }
        }, TEST_TIMEOUT);

        it('should handle multiple concurrent connections', async () => {
            const connections: Array<{ ws: WebSocket; sessionId: string }> = [];

            try {
                // Crea 5 connessioni e raccogli session:init durante la creazione
                const connectionPromises = Array.from({ length: 5 }, async (_, i) => {
                    return new Promise<{ ws: WebSocket; sessionId: string }>((resolve, reject) => {
                        const ws = new WebSocket(WS_URL);
                        const timeout = setTimeout(() => {
                            ws.close();
                            reject(new Error(`Connection ${i} timed out`));
                        }, 10000);

                        ws.on('message', (data) => {
                            clearTimeout(timeout);
                            try {
                                const msg = JSON.parse(data.toString());
                                if (msg.type === 'session:init') {
                                    resolve({ ws, sessionId: msg.data.sessionId });
                                }
                            } catch (e) {
                                reject(e);
                            }
                        });

                        ws.on('error', (error) => {
                            clearTimeout(timeout);
                            reject(error);
                        });
                    });
                });

                // Aspetta tutte le connessioni
                const results = await Promise.all(connectionPromises);
                connections.push(...results);

                // Verifica che tutti gli ID siano validi e unici
                const sessionIds = results.map(r => r.sessionId);

                for (const id of sessionIds) {
                    expect(id).toMatch(
                        /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
                    );
                }

                const uniqueIds = new Set(sessionIds);
                expect(uniqueIds.size).toBe(5);

            } finally {
                connections.forEach(({ ws }) => ws.close());
            }
        }, TEST_TIMEOUT);

        it('should respond to ping with pong', async () => {
            const ws = await createWebSocket(WS_URL);

            try {
                // Aspetta session:init
                await waitForMessage(ws);

                // Invia ping
                const requestId = crypto.randomUUID();
                ws.send(JSON.stringify({
                    type: 'ping',
                    data: {},
                    timestamp: Date.now(),
                    requestId,
                }));

                // Aspetta pong
                const pong = await waitForMessage<{
                    type: string;
                    requestId: string;
                }>(ws);

                expect(pong.type).toBe('pong');
                expect(pong.requestId).toBe(requestId);

            } finally {
                ws.close();
            }
        }, TEST_TIMEOUT);

        it('should handle invalid JSON gracefully', async () => {
            const ws = await createWebSocket(WS_URL);

            try {
                // Aspetta session:init
                await waitForMessage(ws);

                // Invia JSON malformato
                ws.send('not valid json {{{');

                // Dovrebbe ricevere errore
                const errorMsg = await waitForMessage<{
                    type: string;
                    data: { code: string };
                }>(ws);

                expect(errorMsg.type).toBe('error');
                expect(errorMsg.data.code).toBe('PARSE_ERROR');

            } finally {
                ws.close();
            }
        }, TEST_TIMEOUT);

        it('should handle unknown message type', async () => {
            const ws = await createWebSocket(WS_URL);

            try {
                // Aspetta session:init
                await waitForMessage(ws);

                // Invia tipo sconosciuto
                ws.send(JSON.stringify({
                    type: 'unknown:type',
                    data: {},
                    timestamp: Date.now(),
                }));

                // Dovrebbe ricevere errore
                const errorMsg = await waitForMessage<{
                    type: string;
                    data: { code: string; message: string };
                }>(ws);

                expect(errorMsg.type).toBe('error');
                expect(errorMsg.data.code).toBe('UNKNOWN_TYPE');
                expect(errorMsg.data.message).toContain('unknown:type');

            } finally {
                ws.close();
            }
        }, TEST_TIMEOUT);
    });

    // ==========================================================================
    // TEST 3: Chat Flow (Integration con Me4BrAIn)
    // ==========================================================================

    describe('Chat Flow Integration', () => {
        it('should send chat message and receive thinking indicator', async () => {
            const ws = await createWebSocket(WS_URL);

            try {
                // Aspetta session:init
                const initMsg = await waitForMessage<{
                    data: { sessionId: string };
                }>(ws);
                const sessionId = initMsg.data.sessionId;

                // Invia messaggio chat
                ws.send(JSON.stringify({
                    type: 'chat:message',
                    data: {
                        sessionId,
                        content: 'Ciao, come stai?',
                        channel: 'webchat',
                    },
                    timestamp: Date.now(),
                }));

                // Dovrebbe ricevere thinking indicator
                const thinkingMsg = await waitForMessage<{
                    type: string;
                    data: { sessionId: string };
                }>(ws, 5000);

                expect(thinkingMsg.type).toBe('chat:thinking');
                expect(thinkingMsg.data.sessionId).toBe(sessionId);

            } finally {
                ws.close();
            }
        }, TEST_TIMEOUT);

        it('should complete full chat flow with Me4BrAIn', async () => {
            const ws = await createWebSocket(WS_URL);

            try {
                // Aspetta session:init
                const initMsg = await waitForMessage<{
                    data: { sessionId: string };
                }>(ws);
                const sessionId = initMsg.data.sessionId;

                // Invia query semplice che non richiede tools
                ws.send(JSON.stringify({
                    type: 'chat:message',
                    data: {
                        sessionId,
                        content: 'Qual è il prezzo del Bitcoin?',
                        channel: 'webchat',
                    },
                    timestamp: Date.now(),
                }));

                // Aspetta thinking
                const thinking = await waitForMessage<{ type: string }>(ws, 5000);
                expect(thinking.type).toBe('chat:thinking');

                // Aspetta response (può richiedere tempo per Me4BrAIn)
                const response = await waitForMessage<{
                    type: string;
                    data: {
                        content: string;
                        toolsCalled: Array<{ name: string; success: boolean }>;
                        latencyMs: number;
                    };
                }>(ws, 60000); // 60s timeout per Me4BrAIn

                expect(response.type).toBe('chat:response');
                expect(response.data).toHaveProperty('content');
                expect(typeof response.data.content).toBe('string');
                expect(response.data.content.length).toBeGreaterThan(0);
                expect(response.data).toHaveProperty('toolsCalled');
                expect(Array.isArray(response.data.toolsCalled)).toBe(true);
                expect(response.data).toHaveProperty('latencyMs');
                expect(typeof response.data.latencyMs).toBe('number');

                console.log('📝 Chat response:', response.data.content.substring(0, 200));
                console.log('🔧 Tools called:', response.data.toolsCalled);
                console.log('⏱️ Latency:', response.data.latencyMs, 'ms');

            } finally {
                ws.close();
            }
        }, 90000); // 90s timeout per test completo
    });

    // ==========================================================================
    // TEST 4: Error Handling
    // ==========================================================================

    describe('Error Handling', () => {
        it('should handle Me4BrAIn timeout gracefully', async () => {
            const ws = await createWebSocket(WS_URL);

            try {
                // Aspetta session:init
                const initMsg = await waitForMessage<{
                    data: { sessionId: string };
                }>(ws);

                // Query molto complessa che potrebbe causare timeout
                ws.send(JSON.stringify({
                    type: 'chat:message',
                    data: {
                        sessionId: initMsg.data.sessionId,
                        content: 'Fai un\'analisi completa di tutte le azioni del NASDAQ con indicatori tecnici',
                        channel: 'webchat',
                    },
                    timestamp: Date.now(),
                }));

                // Aspetta una risposta (success o error)
                const thinking = await waitForMessage<{ type: string }>(ws, 5000);
                expect(thinking.type).toBe('chat:thinking');

                // La risposta potrebbe essere un errore o una risposta parziale
                const response = await waitForMessage<{
                    type: string;
                    data: unknown;
                }>(ws, 90000);

                // Deve essere una risposta valida (response o error)
                expect(['chat:response', 'error']).toContain(response.type);

            } finally {
                ws.close();
            }
        }, 120000);

        it('should recover after connection drop', async () => {
            // Prima connessione
            const ws1 = await createWebSocket(WS_URL);
            const init1 = await waitForMessage<{ data: { sessionId: string } }>(ws1);
            const sessionId1 = init1.data.sessionId;
            ws1.close();

            // Aspetta un po'
            await new Promise(resolve => setTimeout(resolve, 1000));

            // Seconda connessione - dovrebbe funzionare normalmente
            const ws2 = await createWebSocket(WS_URL);

            try {
                const init2 = await waitForMessage<{ data: { sessionId: string } }>(ws2);

                expect(init2.data.sessionId).not.toBe(sessionId1);
                expect(init2.data.sessionId).toMatch(
                    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
                );

            } finally {
                ws2.close();
            }
        }, TEST_TIMEOUT);
    });

    // ==========================================================================
    // TEST 5: Performance
    // ==========================================================================

    describe('Performance', () => {
        it('should handle rapid message sending', async () => {
            const ws = await createWebSocket(WS_URL);

            try {
                await waitForMessage(ws); // session:init

                // Setup message collector PRIMA di inviare
                const messages: Array<{ type: string; requestId?: string }> = [];
                const collectPromise = new Promise<void>((resolve) => {
                    const handler = (data: WebSocket.RawData) => {
                        try {
                            const msg = JSON.parse(data.toString());
                            messages.push(msg);
                            if (messages.length >= 10) {
                                ws.off('message', handler);
                                resolve();
                            }
                        } catch {
                            // Ignora errori di parsing
                        }
                    };
                    ws.on('message', handler);

                    // Timeout di sicurezza
                    setTimeout(() => {
                        ws.off('message', handler);
                        resolve();
                    }, 10000);
                });

                // Invia 10 ping in rapida successione
                for (let i = 0; i < 10; i++) {
                    const requestId = `ping-${i}`;
                    ws.send(JSON.stringify({
                        type: 'ping',
                        data: {},
                        timestamp: Date.now(),
                        requestId,
                    }));
                }

                // Aspetta tutte le risposte
                await collectPromise;

                // Verifica che tutte siano pong
                const pongs = messages.filter(r => r.type === 'pong');
                expect(pongs.length).toBe(10);

                // Verifica che tutti i requestId siano presenti
                const requestIds = pongs.map(p => p.requestId);
                for (let i = 0; i < 10; i++) {
                    expect(requestIds).toContain(`ping-${i}`);
                }

            } finally {
                ws.close();
            }
        }, TEST_TIMEOUT);

        it('should complete health check within 100ms', async () => {
            const start = Date.now();
            const response = await fetch(`${GATEWAY_URL}/health`);
            const elapsed = Date.now() - start;

            expect(response.ok).toBe(true);
            expect(elapsed).toBeLessThan(100);
        });
    });
});
