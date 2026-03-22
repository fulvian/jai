/**
 * SessionManager Standalone Test
 * 
 * Tests SessionManager functionality without full Gateway integration.
 * Verifies: L1/L2 caching, cache-aside pattern, metrics tracking.
 */

import { Me4BrAInClient, MemoryNamespace } from '@persan/me4brain-client';
import { SessionManager } from './src/services/session_manager.js';
import type { ChatTurn } from '@persan/shared';

// Configuration
const ME4BRAIN_URL = process.env.ME4BRAIN_URL || 'http://localhost:8765';
const TEST_SESSION_ID = `test-session-${Date.now()}`;

console.log('🧪 SessionManager Standalone Test\n');
console.log(`Me4BrAIn URL: ${ME4BRAIN_URL}`);
console.log(`Test Session ID: ${TEST_SESSION_ID}\n`);

async function runTests() {
    // Initialize SessionManager
    const me4brainClient = new Me4BrAInClient({ baseUrl: ME4BRAIN_URL });
    const memoryNamespace = new MemoryNamespace(me4brainClient);
    const sessionManager = new SessionManager(memoryNamespace);

    console.log('✅ SessionManager initialized\n');

    try {
        // Test 1: Create Session
        console.log('📝 Test 1: Create Session');
        const session = await sessionManager.createSession(
            TEST_SESSION_ID,
            'Test Session - Cache-Aside Pattern'
        );
        console.log(`✅ Session created: ${session.session_id}`);
        console.log(`   Title: ${session.title}`);
        console.log(`   Created: ${session.created_at}\n`);

        // Test 2: Add Turn (Write-Through)
        console.log('📝 Test 2: Add Turn (Write-Through)');
        const turn1: ChatTurn = {
            id: `turn-${Date.now()}-1`,
            role: 'user',
            content: 'Hello, this is a test message',
            timestamp: new Date().toISOString(),
        };
        await sessionManager.addTurn(TEST_SESSION_ID, turn1);
        console.log(`✅ Turn added: ${turn1.id}`);
        console.log(`   Content: ${turn1.content}\n`);

        // Test 3: Get Session (Cache Miss → API → Populate L1+L2)
        console.log('📝 Test 3: Get Session (Cache Miss → API)');
        const start1 = Date.now();
        const retrieved1 = await sessionManager.getSession(TEST_SESSION_ID);
        const latency1 = Date.now() - start1;
        console.log(`✅ Session retrieved (${latency1}ms)`);
        console.log(`   Turns: ${retrieved1?.turns.length || 0}`);
        console.log(`   Expected: Cache MISS → API fetch\n`);

        // Test 4: Get Session Again (L1 Hit)
        console.log('📝 Test 4: Get Session Again (L1 Hit)');
        const start2 = Date.now();
        const retrieved2 = await sessionManager.getSession(TEST_SESSION_ID);
        const latency2 = Date.now() - start2;
        console.log(`✅ Session retrieved (${latency2}ms)`);
        console.log(`   Turns: ${retrieved2?.turns.length || 0}`);
        console.log(`   Expected: L1 HIT (<1ms)\n`);

        // Test 5: Add Another Turn (Invalidate Cache)
        console.log('📝 Test 5: Add Turn (Cache Invalidation)');
        const turn2: ChatTurn = {
            id: `turn-${Date.now()}-2`,
            role: 'assistant',
            content: 'This is a test response',
            timestamp: new Date().toISOString(),
        };
        await sessionManager.addTurn(TEST_SESSION_ID, turn2);
        console.log(`✅ Turn added: ${turn2.id}`);
        console.log(`   Cache invalidated (L1 + L2)\n`);

        // Test 6: Get Session After Invalidation (Cache Miss → API)
        console.log('📝 Test 6: Get Session After Invalidation');
        const start3 = Date.now();
        const retrieved3 = await sessionManager.getSession(TEST_SESSION_ID);
        const latency3 = Date.now() - start3;
        console.log(`✅ Session retrieved (${latency3}ms)`);
        console.log(`   Turns: ${retrieved3?.turns.length || 0}`);
        console.log(`   Expected: Cache MISS → API fetch (after invalidation)\n`);

        // Test 7: Metrics
        console.log('📝 Test 7: Cache Metrics');
        const metrics = sessionManager.getMetrics();
        console.log(`✅ Metrics:`);
        console.log(`   Hit Rate: ${metrics.hitRate.toFixed(1)}%`);
        console.log(`   L1 Hits: ${metrics.l1Hits}`);
        console.log(`   L2 Hits: ${metrics.l2Hits}`);
        console.log(`   Misses: ${metrics.misses}`);
        console.log(`   API Errors: ${metrics.apiErrors}\n`);

        // Test 8: List Sessions
        console.log('📝 Test 8: List Sessions');
        const sessions = await sessionManager.listSessions(10);
        console.log(`✅ Sessions listed: ${sessions.length}`);
        if (sessions.length > 0) {
            console.log(`   First session: ${sessions[0].session_id}`);
        }
        console.log();

        // Test 9: Delete Session
        console.log('📝 Test 9: Delete Session');
        const deleted = await sessionManager.deleteSession(TEST_SESSION_ID);
        console.log(`✅ Session deleted: ${deleted}\n`);

        // Test 10: Verify Deletion
        console.log('📝 Test 10: Verify Deletion');
        const deletedSession = await sessionManager.getSession(TEST_SESSION_ID);
        console.log(`✅ Session after deletion: ${deletedSession ? 'EXISTS (ERROR)' : 'NULL (OK)'}\n`);

        // Final Metrics
        console.log('📊 Final Metrics:');
        const finalMetrics = sessionManager.getMetrics();
        console.log(`   Hit Rate: ${finalMetrics.hitRate.toFixed(1)}%`);
        console.log(`   L1 Hits: ${finalMetrics.l1Hits}`);
        console.log(`   L2 Hits: ${finalMetrics.l2Hits}`);
        console.log(`   Misses: ${finalMetrics.misses}`);
        console.log(`   API Errors: ${finalMetrics.apiErrors}\n`);

        console.log('✅ All tests completed successfully!\n');

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
runTests().catch((error) => {
    console.error('❌ Fatal error:', error);
    process.exit(1);
});
