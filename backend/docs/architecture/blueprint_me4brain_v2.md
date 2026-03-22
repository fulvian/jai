# BLUEPRINT DI FONDAZIONE: ME4BRAIN CORE v2.0

**Piattaforma Universale di Memoria Agentica "API-First"**

> **Changelog v2.0**: Decisioni architetturali finalizzate dopo ricerca approfondita (Gennaio 2026)

---

## 1. Visione Architetturale: Il "Cervello as-a-Service"

Il sistema non è un chatbot, ma un'**infrastruttura di back-end intelligente** che espone capacità cognitive via API. Applicazioni esterne (CRM, Dashboard Finanziarie, Strumenti Medici, IDE) si connettono a Me4BrAIn per delegare la gestione dello stato, il ragionamento complesso e la memoria a lungo termine.

### Principi Fondamentali

1. **Persistenza Poliglotta Cognitiva** (Texgravec):
   - **Testo (Narrativa)**: Fedeltà episodica e logging
   - **Vettori (Associazione)**: Recupero semantico "fuzzy" e analogia
   - **Grafo (Struttura)**: Ragionamento logico, causale e procedurale (ToG-2/HippoRAG)

2. **Multi-Tenancy Stretta**: Ogni applicazione client e utente finale possiede uno spazio di memoria isolato (Namespace), protetto da Row-Level Security.

3. **API-First Design**: Interfaccia REST/gRPC stateless, backend stateful.

---

## 2. Architettura a Quattro Layer Cognitivi

```
┌─────────────────────────────────────────────────────────────┐
│                    API GATEWAY (FastAPI)                    │
│              Port: 8089 | JWT via Keycloak                  │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                  ORCHESTRATOR (LangGraph)                   │
│         Checkpointing: PostgresSaver (Port: 5489)           │
└─────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
┌───────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   LAYER I     │   │   LAYER II      │   │  LAYER III-IV   │
│ Working Memory│   │   Episodic +    │   │   Semantic +    │
│    (Redis)    │   │   Procedural    │   │   Knowledge     │
│  Port: 6389   │   │   (Qdrant)      │   │ (KuzuDB/Neo4j)  │
│               │   │  Port: 6389/90  │   │ Port: 7478/7697 │
└───────────────┘   └─────────────────┘   └─────────────────┘
```

### Layer I: Working Memory (STM - Short Term Memory)

**Ruolo**: Il "Workbench" Operativo e Contestuale  
**Latenza Target**: <5ms (In-Memory)

| Componente         | Tecnologia    | Funzione                                  |
| ------------------ | ------------- | ----------------------------------------- |
| Stream Sequenziale | Redis Streams | Log immutabile ultimi N turni (TTFT <1ms) |
| Grafo Effimero     | NetworkX      | Grafo leggero in-memory per coreferenze   |
| Semantic Cache     | Redis         | Caching risposte frequenti                |

**Pattern Key**: `tenant:{id}:user:{id}:session:{id}:stream`

### Layer II: Memoria Episodica (LTM Autobiografica)

**Ruolo**: Il "Diario" dell'Agente e dell'Utente  
**Tecnologia**: Qdrant con **Tiered Multitenancy**

**Struttura Dati (Nota Atomica)**:
```json
{
  "tenant_id": "string",
  "user_id": "string", 
  "content": "string",
  "summary": "string",
  "embedding": [float...],
  "event_time": "timestamp",
  "ingestion_time": "timestamp"
}
```

**Multi-Tenancy Strategy**: 
- Single collection `memories` con payload filtering
- Shard key selector per tenant isolation
- Promozione automatica tenant grandi a shard dedicati

### Layer III: Memoria Semantica (Knowledge Graph)

**Ruolo**: Conoscenza Cristallizzata (Fatti, Regole, Relazioni)  
**Tecnologia Primaria**: **KuzuDB** (embedded, ARM-optimized)  
**Tecnologia Secondaria**: Neo4j Community (grafi complessi)

**Architettura Duale (Fast & Slow)**:
- **Hot Path (LightRAG)**: Ingestione rapida, aggiornamenti incrementali
- **Cold Path (HippoRAG)**: Ragionamento profondo con **Personalized PageRank (PPR)**

> **Decisione v2.0**: KuzuDB come primary per PPR (free, <6GB RAM per 2M nodi, ARM-optimized). Neo4j solo per grafi >500K nodi o query Cypher complesse.
> **Update v2.1 (Gen 2026)**: Su macOS, KuzuDB opera in **File Mode** (crea un file `.db` e non una directory). Il runtime è stato ottimizzato **rimuovendo la dipendenza da Pandas** per l'interazione con il DB, usando iteratori nativi per latenza minima.
> **Update v2.2 (Feb 2026)**: Implementazione **GraphRAG SOTA 2026** con ibridazione Vettoriale/Grafo per Few-Shot Retrieval, estrazione schemi Pydantic-native e Token Budgeting ReAct.

### Layer IV: Memoria Procedurale (Skill & Muscle Memory)

**Ruolo**: Il "Manuale Operativo" Eseguibile  
**Tecnologia**: Qdrant (Few-Shot Store) + KuzuDB (Skill Graph)

**Grafo delle Competenze**:
```
(:Intento)-[:RISOLVE {weight, avg_latency, cost}]->(:Tool)
(:Tool)-[:REQUIRES]->(:Tool)
```

**Meccanismi Evolutivi**:
1. **Ingestione Zero-Shot**: Parsing automatico OpenAPI specs
2. **Rinforzo/Penalizzazione**: Weight adjustment basato su successo/fallimento
3. **Muscle Memory**: Few-shot examples cristallizzati per bypass ragionamento

---

## 3. Il Ciclo Cognitivo: Veglia e Sonno

### Fase di Veglia (Online - Inference)

**Stato**: High Availability, Read-Heavy, Latency-Critical (<2s)

1. **Semantic Router**: Classifica intento (Factual/Thematic/Procedural)
2. **Hybrid Retrieval**: Query parallele Qdrant + KuzuDB
3. **ToG-2 Reasoning**: Navigazione grafo con self-correction
4. **Generation**: Risposta con SSE streaming

### Fase di Sonno (Offline - Consolidation)

**Stato**: Background Processing, Write-Heavy

1. **Digestione (Mem0 Pipeline)**: Estrazione fatti da Working Memory
2. **Ristrutturazione Grafo**: Community detection, summarization update
3. **Garbage Collection**: Pruning vettoriale, consolidamento episodico

**Trigger**: Inattività >10 min OPPURE batch schedulato

---

## 4. API Gateway e Interfaccia Esterna

### Endpoint Principali

| Endpoint             | Metodo | Funzione                                |
| -------------------- | ------ | --------------------------------------- |
| `/v1/agent/invoke`   | POST   | Ragionamento principale (stream SSE)    |
| `/v1/agent/feedback` | POST   | RLHF lite (correzioni utente)           |
| `/v1/memory/ingest`  | POST   | Inserimento conoscenza esplicita        |
| `/v1/memory/inspect` | GET    | Query memoria senza invocare agente     |
| `/v1/memory/forget`  | DELETE | Compliance GDPR (right to be forgotten) |
| `/health`            | GET    | Health check                            |

### Autenticazione e Multi-Tenancy

**Sistema**: **Keycloak self-hosted** (Port: 8489)

- **JWT Tokens**: RS256 con claims `tenant_id`, `user_id`
- **Tenant Isolation**: Realm per tenant principale, metadata per sotto-tenant
- **Rate Limiting**: Redis-based con `slowapi`

**Middleware Chain**:
```
Request → JWT Validation → Tenant Extraction → ContextVar Injection → Handler
```

---

## 5. Stack Tecnologico Definitivo (M1 Pro 16GB)

### Allocazione Risorse RAM

| Componente           | Tecnologia        | RAM Limit    | Porta     |
| -------------------- | ----------------- | ------------ | --------- |
| OS + System          | macOS             | ~4.0 GB      | -         |
| Graph DB (Primary)   | **KuzuDB**        | ~1.5 GB      | embedded  |
| Graph DB (Secondary) | Neo4j             | 3.0 GB       | 7478/7697 |
| Vector DB            | Qdrant            | 2.0 GB       | 6389/6390 |
| STM/Cache            | Redis             | 0.5 GB       | 6389      |
| LangGraph State      | PostgreSQL        | 0.5 GB       | 5489      |
| Auth                 | Keycloak          | 0.5 GB       | 8489      |
| **App Core**         | Python/LangGraph  | ~1.5 GB      | 8089      |
| **Embeddings**       | **BGE-M3**        | ~0.8 GB      | -         |
| **Test Suite**       | Pytest (54 tests) | -            | -         |
| **Margine**          | (Free)            | ~1.7 GB      | -         |
| **TOTALE**           |                   | **~16.0 GB** |           |

### Embedding Model

**Scelta Definitiva**: `BAAI/bge-m3`

| Aspetto      | Specifica           |
| ------------ | ------------------- |
| Dimensioni   | 768                 |
| RAM          | ~800MB              |
| Multilingual | IT, EN, 100+ lingue |
| MPS Support  | Sì (PyTorch)        |
| MTEB Score   | Top-tier            |

### ToG-2 Implementation

**Approccio**: Custom Python + LangGraph (non framework esterni)

```python
# Pseudocode architettura
class ToG2Node:
    async def execute(self, state: AgentState) -> AgentState:
        # 1. Entity extraction
        entities = await self.extract_entities(state.query)
        
        # 2. Graph retrieval (KuzuDB PPR)
        graph_context = await self.ppr_retrieval(entities)
        
        # 3. Vector retrieval (Qdrant)
        vector_context = await self.semantic_retrieval(state.query)
        
        # 4. Merge & reason
        reasoning = await self.llm_reason(graph_context, vector_context)
        
        # 5. Self-correction loop (max 3 iterations)
        if reasoning.confidence < threshold:
            return await self.execute(state.with_refinement(reasoning))
        
        return state.with_answer(reasoning)
```

---

## 6. Observability (Completo)

### Logging
- **Framework**: Structlog (JSON output)
- **Correlation ID**: Per tracing distribuito
- **Tenant Context**: Injection automatica

### Metrics
- **Stack**: Prometheus + Grafana
- **Metriche Chiave**:
  - Request latency (p50, p95, p99)
  - Retrieval time per layer
  - LLM token usage
  - Memory consolidation duration

### LLM Observability
- **Framework**: Langfuse (self-hosted opzionale)
- **Tracing**: Reasoning chains, tool calls, retrieval sources

---

## 7. Docker Compose (Porte Desuete)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    ports: ["5489:5432"]
    mem_limit: 512m
    
  redis:
    image: redis:7-alpine
    ports: ["6389:6379"]
    mem_limit: 512m
    
  qdrant:
    image: qdrant/qdrant:v1.12
    ports: ["6389:6333", "6390:6334"]
    mem_limit: 2g
    
  neo4j:
    image: neo4j:5.26-community
    ports: ["7478:7474", "7697:7687"]
    mem_limit: 3g
    environment:
      NEO4J_PLUGINS: '["apoc"]'
      
  keycloak:
    image: quay.io/keycloak/keycloak:26
    ports: ["8489:8080"]
    mem_limit: 512m
```

---

## 8. Glossario

| Termine                 | Definizione                                                                  |
| ----------------------- | ---------------------------------------------------------------------------- |
| **ToG-2**               | Think-on-Graph 2.0 - Framework per ragionamento iterativo su Knowledge Graph |
| **HippoRAG**            | Framework RAG ispirato all'ippocampo, usa PPR per retrieval associativo      |
| **LightRAG**            | Framework RAG leggero per ingestione incrementale                            |
| **PPR**                 | Personalized PageRank - Algoritmo per ranking nodi basato su random walk     |
| **KuzuDB**              | Graph database embedded, column-oriented, ARM-optimized                      |
| **Tiered Multitenancy** | Pattern Qdrant: single collection + shard promotion per tenant grandi        |
| **Mem0**                | Framework per memory extraction e consolidation                              |
| **A-MEM**               | Agentic Memory - Pattern per note atomiche auto-organizzanti                 |

---

> **Documento Vivo**: Questo blueprint evolverà con l'implementazione. Ogni modifica significativa deve essere tracciata nel CHANGELOG.
