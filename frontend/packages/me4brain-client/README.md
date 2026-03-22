# Me4BrAIn TypeScript Client

SDK TypeScript per interagire con [Me4BrAIn Core](https://github.com/fulvian/Me4BrAIn).

## Installazione

```bash
npm install @persan/me4brain-client
```

## Quick Start

```typescript
import { Me4BrAInClient } from '@persan/me4brain-client';

const client = new Me4BrAInClient({
    baseUrl: 'http://localhost:8089',
    apiKey: 'your-api-key',
});

// Query naturale
const response = await client.engine.query('Qual è il prezzo del Bitcoin?');
console.log(response.answer);
```

## Namespaces

### Engine

```typescript
// Query with natural language
const result = await client.engine.query('Meteo a Roma e prezzo BTC');

// Direct tool call
const btc = await client.engine.call('coingecko_price', { ids: 'bitcoin' });

// List tools
const tools = await client.engine.listTools({ domain: 'finance_crypto' });
```

### Memory

```typescript
// Create session
const session = await client.memory.createSession();

// Add turn
await client.memory.addTurn(session.sessionId, {
    role: 'user',
    content: 'Ciao!',
});

// Get context
const context = await client.memory.getContext(session.sessionId);
```

### Skills (v0.15.0+)

```typescript
// List crystallized skills
const skills = await client.skills.list('crystallized');

// List pending approval
const pending = await client.skills.listPending();

// Approve a skill
await client.skills.approve(pending[0].id, { note: 'Approved by admin' });

// Reject a skill
await client.skills.reject(pending[1].id, { note: 'Not relevant' });

// Get approval stats
const stats = await client.skills.approvalStats();
console.log(`Pending: ${stats.pending}, Approved: ${stats.approved}`);
```

## Streaming

```typescript
for await (const chunk of client.engine.queryStream('Hello!')) {
    switch (chunk.type) {
        case 'content':
            process.stdout.write(chunk.content ?? '');
            break;
        case 'tool':
            console.log(`Tool: ${chunk.tool_call?.tool}`);
            break;
        case 'done':
            console.log(`\nCompleted in ${chunk.total_latency_ms}ms`);
            break;
    }
}
```

## Types

```typescript
import type {
    // Query
    EngineQueryResponse,
    ToolCallInfo,
    QueryOptions,
    
    // Tools
    ToolInfo,
    CatalogStats,
    
    // Memory
    Session,
    Turn,
    
    // Skills (v0.15.0+)
    PendingSkill,
    SkillInfo,
    ApprovalStats,
    RiskLevel,
} from '@persan/me4brain-client';
```

## Configuration

| Option     | Type   | Default                 | Description                |
| ---------- | ------ | ----------------------- | -------------------------- |
| `baseUrl`  | string | `http://localhost:8000` | Me4BrAIn API URL           |
| `apiKey`   | string | -                       | API key for authentication |
| `tenantId` | string | `default`               | Multi-tenant ID            |
| `timeout`  | number | `300000`                | Request timeout (ms)       |

## Risk Levels

Skills sono classificati per rischio:

| Level     | Description           | Action        |
| --------- | --------------------- | ------------- |
| 🟢 SAFE    | Read-only             | Auto-approve  |
| 🟡 NOTIFY  | Local modification    | Log only      |
| 🔴 CONFIRM | External side effects | HITL required |
| ⛔ DENY    | Dangerous patterns    | Blocked       |

## License

MIT
