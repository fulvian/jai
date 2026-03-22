/**
 * Integration Test - Me4BrAIn Client
 * 
 * Verifica che il client TypeScript comunichi correttamente con Me4BrAIn.
 */

import { describe, it, expect, beforeAll } from 'vitest';
import { Me4BrAInClient } from '@persan/me4brain-client';

const ME4BRAIN_URL = process.env.ME4BRAIN_URL ?? 'http://localhost:8000/v1';

describe('Me4BrAIn Client Integration', () => {
    let client: Me4BrAInClient;

    beforeAll(() => {
        client = new Me4BrAInClient({
            baseUrl: ME4BRAIN_URL,
            tenantId: 'default',
        });
    });

    describe('Engine Namespace', () => {
        it('should get catalog stats', async () => {
            const stats = await client.engine.stats();

            expect(stats).toHaveProperty('totalTools');
            expect(typeof stats.totalTools).toBe('number');
            expect(stats.totalTools).toBeGreaterThan(0);
            expect(stats).toHaveProperty('domains');
            expect(Array.isArray(stats.domains)).toBe(true);

            console.log(`📊 Total tools: ${stats.totalTools}`);
            console.log(`📁 Domains: ${stats.domains.length}`);
        });

        it('should list tools by domain', async () => {
            const tools = await client.engine.listTools({ domain: 'finance_crypto' });

            expect(Array.isArray(tools)).toBe(true);
            expect(tools.length).toBeGreaterThan(0);

            const toolNames = tools.map((t) => t.name);
            expect(toolNames).toContain('coingecko_price');

            console.log(`🔧 Finance/Crypto tools: ${tools.length}`);
        });

        it('should call tool directly (finnhub_quote)', async () => {
            // Usiamo finnhub invece di coingecko per evitare rate limiting
            const result = await client.engine.call('finnhub_quote', {
                symbol: 'AAPL',
            }) as { symbol: string; current: number; change: number };

            expect(result).toHaveProperty('symbol', 'AAPL');
            expect(result).toHaveProperty('current');
            expect(typeof result.current).toBe('number');
            expect(result.current).toBeGreaterThan(0);

            console.log(`📈 AAPL price: $${result.current}`);
        });

        it('should execute natural language query', async () => {
            const response = await client.engine.query('Ciao');

            expect(response).toHaveProperty('query');
            expect(response).toHaveProperty('answer');
            expect(typeof response.answer).toBe('string');
            expect(response.answer.length).toBeGreaterThan(0);
            expect(response).toHaveProperty('toolsCalled');
            expect(Array.isArray(response.toolsCalled)).toBe(true);
            expect(response).toHaveProperty('totalLatencyMs');
            expect(typeof response.totalLatencyMs).toBe('number');

            console.log(`💬 Query response: ${response.answer.substring(0, 100)}...`);
            console.log(`⏱️ Latency: ${response.totalLatencyMs.toFixed(0)}ms`);
        });

        it('should get tool details', async () => {
            const tool = await client.engine.getTool('coingecko_price');

            expect(tool).toHaveProperty('name', 'coingecko_price');
            expect(tool).toHaveProperty('description');
            expect(typeof tool.description).toBe('string');

            console.log(`📖 Tool: ${tool.name}`);
            console.log(`📝 Description: ${tool.description.substring(0, 80)}...`);
        });
    });

    describe('Error Handling', () => {
        it('should throw on non-existent tool', async () => {
            await expect(
                client.engine.call('non_existent_tool_xyz', {})
            ).rejects.toThrow();
        });

        it('should handle API errors and return result (not throw)', async () => {
            // L'API ritorna result anche con errori, non lancia exception
            // Questo test verifica che la chiamata non crashi
            const result = await client.engine.call('finnhub_quote', {
                symbol: 'INVALID_SYMBOL_XYZ123',
            });

            // Potrebbe essere un result con errore o vuoto
            expect(result).toBeDefined();
        });
    });
});
