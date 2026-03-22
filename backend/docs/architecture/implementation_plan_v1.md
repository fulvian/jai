# Piano di Implementazione: Me4BrAIn Core v0.1

**Data**: Gennaio 2026  
**Versione Blueprint**: v2.0

---

## Obiettivo

Fondare il progetto **Me4BrAIn Core** - Piattaforma Universale di Memoria Agentica API-First.

---

## Decisioni Architetturali

| Aspetto              | Decisione                              | Motivazione                               |
| -------------------- | -------------------------------------- | ----------------------------------------- |
| **ToG-2**            | Custom Python + LangGraph              | Production-ready per API-First + HippoRAG |
| **PPR Algorithm**    | KuzuDB (primary) + NetworkX (fallback) | Free, ARM-optimized, <6GB RAM             |
| **Embedding**        | `BAAI/bge-m3`                          | Multilingual IT/EN, ~800MB, MPS           |
| **Multi-Tenancy**    | Tiered Multitenancy Qdrant             | No refactoring futuro                     |
| **Auth**             | Keycloak self-hosted                   | Free, battle-tested, realms per tenant    |
| **Checkpointing**    | PostgresSaver                          | Durabilità dev/prod uniforme              |
| **Package Manager**  | `uv`                                   | 100x faster di Poetry                     |
| **Graph DB**         | KuzuDB                                 | Embedded, zero Docker, File-mode on macOS |
| **Data Interaction** | Native Iterators (No Pandas)           | Minimal latency, reduced dependency size  |
| **Validation**       | 54 Unit Tests                          | Core logic verified (>85% coverage)       |

---

## Stack Tecnologico

### Servizi Docker (Porte Desuete)

| Servizio        | Immagine                       | Porta Host    | RAM   |
| --------------- | ------------------------------ | ------------- | ----- |
| PostgreSQL      | `postgres:16-alpine`           | **5489**      | 512MB |
| Redis           | `redis:7-alpine`               | **6389**      | 512MB |
| Qdrant          | `qdrant/qdrant:v1.12`          | **6389/6390** | 2GB   |
| Neo4j           | `neo4j:5.26-community`         | **7478/7697** | 3GB   |
| Keycloak        | `quay.io/keycloak/keycloak:26` | **8489**      | 512MB |
| **API Gateway** | FastAPI/Uvicorn                | **8089**      | -     |

---

## Struttura Progetto

```
me4brain/
├── docker/
│   ├── docker-compose.yml
│   └── keycloak/realm-export.json
├── src/me4brain/
│   ├── api/
│   │   ├── main.py
│   │   ├── routes/{agent,memory,health}.py
│   │   └── middleware/{auth,tenant}.py
│   ├── core/
│   │   ├── orchestrator.py      # LangGraph
│   │   ├── state.py             # AgentState
│   │   └── router.py            # Semantic Router
│   ├── memory/
│   │   ├── working.py           # Redis STM
│   │   ├── episodic.py          # Qdrant
│   │   ├── semantic.py          # KuzuDB/Neo4j
│   │   └── procedural.py        # Skill Graph
│   ├── retrieval/
│   │   ├── hipporag.py
│   │   ├── lightrag.py
│   │   └── ppr.py               # KuzuDB PPR
│   ├── embeddings/bge_m3.py
│   └── config/settings.py
├── tests/{unit,integration,e2e}/
├── scripts/{start,stop}.sh
├── pyproject.toml
└── .pre-commit-config.yaml
```

---

## Fasi di Implementazione

### Fase 1: Bootstrap (1-2 giorni) - COMPLETATA
- [x] `uv init` + pyproject.toml
- [x] Docker Compose base con **limiti RAM espliciti**:
- [x] Pre-commit hooks (ruff, mypy)
- [x] Health endpoint

### Fase 2: Memory Layers (3-5 giorni)
- [x] Working Memory (Redis Streams + NetworkX compresso)
- [x] Episodic Memory (Qdrant + Tiered MT + GDPR)
- [x] Semantic Memory (KuzuDB + PPR custom)
- [x] Procedural Memory (Skill Graph + Muscle Memory)
- [x] Embedding service (BGE-M3 + MPS)
- [x] Test unitari passati (5/5 Episodic, 6/6 Semantic)

### Fase 3: Orchestrator (3-5 giorni)
- [x] LangGraph StateGraph con nodi cognitivi
- [x] PostgresSaver checkpointing wrapper
- [x] **Semantic Router (pattern + embedding)** → decide Vector vs Graph
- [x] ToG-2 reasoning loop (PPR-based)
- [x] **Conflict Resolution Module** → Recency Bias + 3 altre strategie
- [x] Test unitari passati (7/7 Router & Conflict)

### Fase 4: Procedural Cortex (2-3 giorni)
- [x] **Muscle Memory PRIMA** del grafo complesso → cache JSON di successo in Qdrant
- [x] Skill Graph (Intento <-> Tool con pesi adattivi)
- [x] **Zero-Shot OpenAPI Ingestion** → parser automatico `openapi.json` → nodi `:Tool`
- [x] Tool Executor con HTTP execution
- [x] Test unitari passati (4/4 Procedural, 7/7 Ingester)

### Fase 5: API Gateway + Sleep Mode (2-3 giorni)
- [x] FastAPI app + JWT middleware (Keycloak JWKS)
- [x] Routes per memoria (store, retrieve, search, query)
- [x] Admin routes (consolidation, scheduler, OpenAPI ingestion)
- [x] Sleep Mode consolidamento background
- [x] **Secondary LLM Provider config** per background jobs
- [x] Test unitari passati (Health & Core components verified)
- [ ] Sleep Mode asincrono (non cron) con queue Redis

### Fase 6: Observability (1-2 giorni)
- [ ] Structlog setup
- [ ] Prometheus metrics
- [ ] Langfuse integration
- [ ] Unit tests (>80% coverage)
- [ ] Integration tests
- [ ] E2E tests
- [ ] README + API docs

---

## Verifica

### Automated
```bash
uv run pytest tests/ -v --cov=src/me4brain
```

### Manual
1. `curl http://localhost:8089/health` → `{"status": "ok"}`
2. Keycloak admin: `http://localhost:8489`
3. Qdrant dashboard: `http://localhost:6390/dashboard`
4. Neo4j browser: `http://localhost:7478`

---

## Dipendenze Core

```toml
[project]
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "langgraph>=0.2",
    "langgraph-checkpoint-postgres>=2",
    "qdrant-client>=1.12",
    "kuzu>=0.8",
    "redis>=5",
    "sentence-transformers>=3",
    "structlog>=24",
    "pyjwt[crypto]>=2.9",
    "python-keycloak>=4",
    "httpx>=0.28",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "ruff", "mypy", "pre-commit"]
```

---

> **Prossimo Step**: Bootstrap progetto con `uv init`
