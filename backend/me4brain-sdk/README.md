# Me4BrAIn SDK

**Python SDK per Me4BrAIn Agentic Memory Platform**

[![PyPI version](https://badge.fury.io/py/me4brain-sdk.svg)](https://badge.fury.io/py/me4brain-sdk)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Installazione

```bash
pip install me4brain-sdk

# Con telemetria OpenTelemetry
pip install me4brain-sdk[telemetry]

# Con supporto HIPAA/security
pip install me4brain-sdk[security]

# Tutto incluso
pip install me4brain-sdk[all]
```

## Quick Start

```python
from me4brain_sdk import AsyncMe4BrAInClient

async with AsyncMe4BrAInClient(
    base_url="http://localhost:8089",
    api_key="your-api-key",
) as client:
    # Query cognitiva con memoria
    response = await client.cognitive.query(
        query="Cosa abbiamo discusso ieri sul progetto?",
        session_id="session-123",
    )
    print(response.answer)
    print(f"Confidenza: {response.confidence}")

    # Streaming SSE
    async for chunk in client.cognitive.query_stream(
        query="Riassumi i documenti del progetto",
    ):
        if chunk.content:
            print(chunk.content, end="", flush=True)
```

## 🚀 Multi-Domain Query (NEW v2.0)

Query che richiedono **più domini** vengono eseguite **in parallelo**:

```python
# Query automaticamente ruota a multipli domini
response = await client.cognitive.query(
    query="Confronta prezzo Bitcoin con meteo Milano e partita Lakers stasera",
)
# → Attiva: finance_crypto + geo_weather + sports_nba (parallelo!)

# Vedi quali domini sono stati usati
for result in response.domain_results:
    print(f"Dominio: {result.domain}, Tool: {result.tool_name}")
```

### Come Funziona

```
"Confronta BTC con meteo Roma"
    ↓
analyze_query() → domains_required: ["finance_crypto", "geo_weather"]
    ↓
asyncio.gather(finance.execute(), geo.execute())  # PARALLELO
    ↓
aggregate_results() → risposta cross-domain
```

## 🔧 Tool Calling Engine

Accesso diretto al motore di tool calling con **130+ tools** e **Hybrid Router**:

```python
# Query naturale → tool selection automatico
result = await client.engine.query(
    query="Cerca email su progetto ANCI poi cerca volo per Roma",
)
print(f"Answer: {result.answer}")
print(f"Tools used: {[t.tool_name for t in result.tools_called]}")

# Lista tools disponibili
tools = await client.engine.list_tools(domain="google_workspace")
print(f"Google Workspace tools: {len(tools)}")
```

### Hybrid Router Features

- **Query Decomposition**: Query multi-intent vengono decomposte automaticamente
- **LlamaIndex Retrieval**: BGE-M3 embeddings + LLM reranking (+25% precision)
- **RRF Merge**: Reciprocal Rank Fusion per risultati multi-domain

## Cognitive Reasoning & Planning

L'SDK supporta ragionamento multi-step e generazione piani:

```python
# Multi-step Reasoning
reasoning = await client.cognitive.reason(
    query="Qual è il ROI del progetto considerando tutti i fattori?",
    max_steps=5,
)
print(f"Risposta: {reasoning.response}")
print(f"Confidenza: {reasoning.confidence}")
for step in reasoning.reasoning_steps:
    print(f"  Step {step.step}: {step.description}")

# Piano strutturato
plan = await client.cognitive.plan(
    goal="Lanciare il prodotto in 3 mesi",
    constraints=["Budget 50k", "Team di 4 persone"],
)
for step in plan.plan:
    print(f"{step.step_number}. [{step.action}] {step.description}")
```

## Memory Layers

L'SDK espone i 4 layer di memoria cognitiva:

```python
# Working Memory (sessione corrente)
session = await client.working.create_session(user_id="user-1")
await client.working.add_turn(session.id, role="user", content="Ciao!")

# Episodic Memory (eventi passati)
episodes = await client.episodic.search(
    query="discussione budget",
    limit=10,
)
# Update e related episodes
await client.episodic.update(episode.id, importance=0.9, tags=["importante"])
related = await client.episodic.get_related(episode.id, limit=5)

# Semantic Memory (knowledge graph)
entities = await client.semantic.search(
    query="Mario Rossi",
    limit=5,
)

# List entities by type (without semantic query)
projects = await client.semantic.list_entities(
    entity_type="Project",
    limit=100,
)
for entity in projects["entities"]:
    print(entity["name"])

await client.semantic.traverse(
    start_entity="entity-123",
    max_depth=3,
)

# Procedural Memory (skills/tools)
tools = await client.procedural.search_tools(
    query="calcolo finanziario",
)
```

## 🧠 Skills Auto-Generation (NEW v0.15.0)

Sistema di **Skill Crystallization** basato sul Voyager pattern.

### Workflow

```
Query → Tool Execution → Trace → Crystallization → Approval → Persistence
```

### Skills API

```python
# Lista skill pending approvazione
pending = await client.skills.list_pending()
for skill in pending:
    print(f"[{skill.risk_level}] {skill.name}")
    print(f"  Tool chain: {', '.join(skill.tool_chain)}")

# Approva skill
await client.skills.approve(skill_id="abc123", note="LGTM")

# Rifiuta skill
await client.skills.reject(skill_id="xyz789", note="Not needed")

# Statistiche approvazione
stats = await client.skills.approval_stats()
print(f"Pending: {stats.pending}, Approved: {stats.approved}")
```

### Risk Levels

| Livello   | Azione        | Trigger                           |
| --------- | ------------- | --------------------------------- |
| 🟢 SAFE    | Auto-approve  | Tool read-only (search, weather)  |
| 🟡 NOTIFY  | Log only      | File write, doc creation          |
| 🔴 CONFIRM | HITL required | Delete, send_email                |
| ⛔ DENY    | Blocked       | Pattern pericolosi (rm -rf, sudo) |

### Lista Skill Cristallizzate

```python
# Lista skill salvate
skills = await client.skills.list_skills(skill_type="crystallized")
for s in skills:
    print(f"{s.name} - Usage: {s.usage_count}, Success: {s.success_rate}%")

# Toggle enable/disable
await client.skills.toggle(skill_id="skill-123", enabled=False)
```

## 📋 Session Management (NEW v2.1)

Gestione sessioni con titoli e metadati:

```python
# Lista sessioni utente
sessions = await client.working.list_sessions(user_id="user-1", limit=20)
for s in sessions["sessions"]:
    print(f"{s['session_id']}: {s['title']} ({s['message_count']} msg)")

# Aggiorna titolo sessione
await client.working.update_session(
    session_id="abc-123",
    user_id="user-1",
    title="Chat su progetto ANCI"
)

# Info singola sessione
info = await client.working.get_session(
    session_id="abc-123",
    user_id="user-1"
)
print(f"Creata: {info['created_at']}, Messaggi: {info['message_count']}")
```

## Domini Specializzati

Accesso type-safe a 14 domini:

```python
# Medical (HIPAA compliant)
drug_info = await client.domains.medical.drug_interactions(
    drugs=["aspirin", "warfarin"],
)

# Google Workspace
events = await client.domains.google_workspace.calendar.list_events(
    max_results=10,
)

# Finance & Crypto
stock = await client.domains.finance.stock_price("AAPL")
crypto = await client.domains.finance.crypto_price("BTC")

# Weather
weather = await client.domains.geo_weather.current("Milano, IT")
```

## HIPAA Mode

Per applicazioni healthcare:

```python
from me4brain_sdk import AsyncMe4BrAInClient
from me4brain_sdk.security import HIPAAConfig

client = AsyncMe4BrAInClient(
    base_url="https://api.me4brain.ai",
    api_key="your-key",
    hipaa_mode=HIPAAConfig(
        enabled=True,
        audit_logging=True,
        encryption_at_rest=True,
    ),
)
```

## Integrazioni

### LangChain

```python
from me4brain_sdk.contrib import Me4BrAInLangChainMemory

memory = Me4BrAInLangChainMemory(client=client)
chain = ConversationChain(memory=memory)
```

### LlamaIndex

```python
from me4brain_sdk.contrib import Me4BrAInVectorStore

vector_store = Me4BrAInVectorStore(client=client)
index = VectorStoreIndex.from_vector_store(vector_store)
```

## Documentazione

- [Getting Started](./docs/getting_started.md)
- [API Reference](./docs/api_reference.md)
- [Security Guide](./docs/security.md)
- [Examples](./examples/)

## License

MIT License - vedi [LICENSE](./LICENSE)
