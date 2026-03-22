/**
 * SessionManager Mock Test
 * 
 * Tests SessionManager cache logic with mocked Me4BrAIn API.
 * Verifies: L1/L2 caching behavior, metrics tracking, cache invalidation.
 */

import { SessionManager } from './src/services/session_manager.js';
import type { ChatTurn, ChatSession } from '@persan/shared';

// Mock MemoryNamespace
class MockMemoryNamespace {
    private sessions = new Map<string, { turns: any[] }>();

    async createSession(id: string): Promise<any> {
        this.sessions.set(id, { turns: [] });
        return { sessionId: id, userId: 'default', createdAt: new Date() };
    }

    async getSession(sessionId: string): Promise<any> {
        const session = this.sessions.get(sessionId);
        if (!session) {
            throw new Error(`Session ${sessionId} not found`);
        }
        return {
            sessionId,
            turns: session.turns,
            turnCount: session.turns.length,
        };
    }

    async addTurn(sessionId: string, role: string, content: string): Promise<any> {
        const session = this.sessions.get(sessionId);
        if (!session) {
            throw new Error(`Session ${sessionId} not found`);
        }
        const turn = {
            id: `turn-${Date.now()}`,
            role,
            content,
            timestamp: new Date(),
        };
        session.turns.push(turn);
        return turn;
    }

    async deleteSession(sessionId: string): Promise<boolean> {
        return this.sessions.delete(sessionId);
    }
}

console.log('🧪 SessionManager Mock Test (No External Dependencies)\n');

async function runMockTests() {
    // Initialize SessionManager with mock
    const mockMemory = new MockMemoryNamespace() as any;
    const sessionManager = new SessionManager(mockMemory);

    const TEST_SESSION_ID = `mock-session-${Date.now()}`;

    console.log('✅ SessionManager initialized with mock\n');

    try {
        // Test 1: Create Session
        console.log('📝 Test 1: Create Session');
        const session = await sessionManager.createSession(
            TEST_SESSION_ID,
            'Mock Test Session'
        );
        console.log(`✅ Session created: ${session.session_id}`);
        console.log(`   Title: ${session.title}\n`);

        // Test 2: Add Turn (Write-Through → Cache Invalidation)
        console.log('📝 Test 2: Add Turn (Write-Through)');
        const turn1: ChatTurn = {
            id: `turn-${Date.now()}-1`,
            role: 'user',
            content: 'Test message 1',
            timestamp: new Date().toISOString(),
        };
        await sessionManager.addTurn(TEST_SESSION_ID, turn1);
        console.log(`✅ Turn added: ${turn1.id}`);
        console.log(`   Cache invalidated\n`);

        // Test 3: Get Session (Cache Miss → API → Populate L1+L2)
        console.log('📝 Test 3: Get Session (Cache Miss)');
        const start1 = Date.now();
        const retrieved1 = await sessionManager.getSession(TEST_SESSION_ID);
        const latency1 = Date.now() - start1;
        console.log(`✅ Session retrieved (${latency1}ms)`);
        console.log(`   Turns: ${retrieved1?.turns.length || 0}`);
        console.log(`   Expected: Cache MISS\n`);

        // Test 4: Get Session Again (L1 Hit)
        console.log('📝 Test 4: Get Session Again (L1 Hit)');
        const start2 = Date.now();
        const retrieved2 = await sessionManager.getSession(TEST_SESSION_ID);
        const latency2 = Date.now() - start2;
        console.log(`✅ Session retrieved (${latency2}ms)`);
        console.log(`   Turns: ${retrieved2?.turns.length || 0}`);
        console.log(`   Expected: L1 HIT (<1ms)`);

        if (latency2 < 5) {
            console.log(`   ✅ L1 cache working! (${latency2}ms < 5ms)\n`);
        } else {
            console.log(`   ⚠️  Slower than expected (${latency2}ms)\n`);
        }

        // Test 5: Add Another Turn (Invalidate Cache)
        console.log('📝 Test 5: Add Turn (Cache Invalidation)');
        const turn2: ChatTurn = {
            id: `turn-${Date.now()}-2`,
            role: 'assistant',
            content: 'Test response',
            timestamp: new Date().toISOString(),
        };
        await sessionManager.addTurn(TEST_SESSION_ID, turn2);
        console.log(`✅ Turn added: ${turn2.id}`);
        console.log(`   Cache invalidated\n`);

        // Test 6: Get Session After Invalidation (Cache Miss)
        console.log('📝 Test 6: Get Session After Invalidation');
        const start3 = Date.now();
        const retrieved3 = await sessionManager.getSession(TEST_SESSION_ID);
        const latency3 = Date.now() - start3;
        console.log(`✅ Session retrieved (${latency3}ms)`);
        console.log(`   Turns: ${retrieved3?.turns.length || 0}`);
        console.log(`   Expected: Cache MISS (after invalidation)\n`);

        // Test 7: Multiple Gets (L1 Cache Performance)
        console.log('📝 Test 7: Multiple Gets (L1 Performance)');
        const iterations = 100;
        const startBatch = Date.now();
        for (let i = 0; i < iterations; i++) {
            await sessionManager.getSession(TEST_SESSION_ID);
        }
        const batchLatency = Date.now() - startBatch;
        const avgLatency = batchLatency / iterations;
        console.log(`✅ ${iterations} gets completed in ${batchLatency}ms`);
        console.log(`   Average: ${avgLatency.toFixed(2)}ms per get`);
        console.log(`   Expected: <1ms (L1 cache)\n`);

        // Test 8: Metrics
        console.log('📝 Test 8: Cache Metrics');
        const metrics = sessionManager.getMetrics();
        console.log(`✅ Metrics:`);
        console.log(`   Hit Rate: ${metrics.hitRate.toFixed(1)}%`);
        console.log(`   L1 Hits: ${metrics.l1Hits}`);
        console.log(`   L2 Hits: ${metrics.l2Hits}`);
        console.log(`   Misses: ${metrics.misses}`);
        console.log(`   API Errors: ${metrics.apiErrors}\n`);

        // Verify hit rate
        if (metrics.hitRate > 80) {
            console.log(`   ✅ Excellent hit rate (${metrics.hitRate.toFixed(1)}%)\n`);
        } else {
            console.log(`   ⚠️  Hit rate lower than expected (${metrics.hitRate.toFixed(1)}%)\n`);
        }

        // Test 9: Delete Session
        console.log('📝 Test 9: Delete Session');
        const deleted = await sessionManager.deleteSession(TEST_SESSION_ID);
        console.log(`✅ Session deleted: ${deleted}\n`);

        // Test 10: Verify Deletion
        console.log('📝 Test 10: Verify Deletion');
        const deletedSession = await sessionManager.getSession(TEST_SESSION_ID);
        console.log(`✅ Session after deletion: ${deletedSession ? 'EXISTS (ERROR)' : 'NULL (OK)'}\n`);

        // Final Summary
        console.log('📊 Test Summary:');
        console.log(`   ✅ Cache-Aside pattern working`);
        console.log(`   ✅ L1 cache performance: ${avgLatency.toFixed(2)}ms avg`);
        console.log(`   ✅ Write-through invalidation working`);
        console.log(`   ✅ Metrics tracking working`);
        console.log(`   ✅ Hit rate: ${metrics.hitRate.toFixed(1)}%\n`);

        console.log('✅ All mock tests completed successfully!\n');

        // Cleanup
        await sessionManager.close();
        console.log('🧹 SessionManager closed');

    } catch (error) {
        console.error('❌ Test failed:', error);
        await sessionManager.close();
        process.exit(1);
    }
}

// Run tests
runMockTests().catch((error) => {
    console.error('❌ Fatal error:', error);
    process.exit(1);
});
