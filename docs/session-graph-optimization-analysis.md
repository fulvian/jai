# JAI Session Knowledge Graph - Architecture Analysis & Optimization Plan

**Document Version:** 1.0  
**Created:** 2026-03-23  
**Author:** AI Architecture Analysis  
**Status:** Analysis Complete  
**Scope:** Session Knowledge Graph, Drag-and-Drop, Vector Embeddings, Auto-Cataloging

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Overview](#2-current-architecture-overview)
3. [Detailed Component Analysis](#3-detailed-component-analysis)
4. [Identified Issues & Criticalities](#4-identified-issues--criticalities)
5. [Best Practices Research (SOTA 2025-2026)](#5-best-practices-research-sota-2025-2026)
6. [Gap Analysis](#6-gap-analysis)
7. [Optimization Plan](#7-optimization-plan)
8. [Implementation Priority Matrix](#8-implementation-priority-matrix)
9. [Testing Strategy](#9-testing-strategy)
10. [References](#10-references)

---

## 1. Executive Summary

### 1.1 Analysis Scope

This document analyzes JAI's **Session Knowledge Graph** system, focusing on:

- **Backend (Me4BrAIn)**: Neo4j graph storage, BGE-M3 embeddings, domain classification, hybrid retrieval
- **Frontend (PersAn)**: Session management, graph exploration, drag-and-drop canvas, caching

### 1.2 Key Findings

| Area | Current State | Target State | Gap Severity |
|------|---------------|--------------|--------------|
| **Graph Architecture** | Neo4j with 5 node types, manual community detection | GraphRAG-compliant with dynamic clustering | Medium |
| **Embeddings** | BGE-M3 single-process, synchronous | Batch processing with caching | High |
| **Hybrid Search** | Vector + PageRank + LLM rerank | Cascaded retrieval with BM25 boost | Medium |
| **Caching** | L1 + L2 with basic stampede protection | Multi-tier with pub/sub invalidation | Low |
| **DnD System** | @dnd-kit sortable | Cross-list with optimistic updates | Medium |
| **Auto-Cataloging** | Louvain community detection with cooldown | Real-time incremental clustering | Medium |

### 1.3 Critical Issues Requiring Immediate Attention

1. **Fire-and-forget async tasks** without error tracking in session ingestion
2. **Embedding service is singleton** - potential bottleneck under load
3. **In-memory cooldown tracking** not distributed across instances
4. **Missing retry logic** in frontend graph service
5. **Hardcoded similarity thresholds** without adaptive calibration

---

## 2. Current Architecture Overview

### 2.1 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (PersAn)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────────────┐  │
│  │  ChatPanel.tsx  │    │  Canvas.tsx     │    │  GraphExplorer.tsx      │  │
│  │  - Send queries │    │  - @dnd-kit     │    │  - Cluster exploration  │  │
│  │  - Turn display │    │  - Item sorting │    │  - Connected nodes      │  │
│  └────────┬────────┘    └────────┬────────┘    └───────────┬─────────────┘  │
│           │                      │                         │                 │
│  ┌────────▼──────────────────────▼─────────────────────────▼─────────────┐  │
│  │                     React Hooks (useSessionGraph.ts)                    │  │
│  │  - useSessionClusters()     - useRelatedSessions()                     │  │
│  │  - useSessionSearch()       - useConnectedNodes()                      │  │
│  │  - useTopics()              - usePromptLibrary()                       │  │
│  └────────────────────────────────┬──────────────────────────────────────┘  │
│                                   │                                          │
└───────────────────────────────────┼──────────────────────────────────────────┘
                                    │ HTTP/REST
┌───────────────────────────────────┼──────────────────────────────────────────┐
│                          GATEWAY (Fastify)                                    │
├───────────────────────────────────┼──────────────────────────────────────────┤
│                                   │                                          │
│  ┌────────────────────────────────▼──────────────────────────────────────┐  │
│  │                    SessionManager (session_manager.ts)                 │  │
│  │  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────────┐   │  │
│  │  │  L1 Cache   │◄──►│  L2 Cache   │◄──►│  Redis Pub/Sub          │   │  │
│  │  │  (Map)      │    │  (Redis)    │    │  (Invalidation)         │   │  │
│  │  └─────────────┘    └─────────────┘    └─────────────────────────┘   │  │
│  └────────────────────────────────┬──────────────────────────────────────┘  │
│                                   │                                          │
│  ┌────────────────────────────────▼──────────────────────────────────────┐  │
│  │               GraphSessionService (graph_session_service.ts)           │  │
│  │  - ingestSession()     - searchSessions()                              │  │
│  │  - getRelatedSessions() - getClusters()                                │  │
│  └────────────────────────────────┬──────────────────────────────────────┘  │
│                                   │                                          │
└───────────────────────────────────┼──────────────────────────────────────────┘
                                    │ HTTP (8000)
┌───────────────────────────────────┼──────────────────────────────────────────┐
│                         BACKEND (Me4BrAIn)                                    │
├───────────────────────────────────┼──────────────────────────────────────────┤
│                                   │                                          │
│  ┌────────────────────────────────▼──────────────────────────────────────┐  │
│  │                   API Routes (session_graph.py)                        │  │
│  │  POST /graph/ingest    GET /graph/search    GET /graph/clusters       │  │
│  │  GET /graph/related    GET /graph/topics    GET /graph/connected-nodes│  │
│  └────────────────────────────────┬──────────────────────────────────────┘  │
│                                   │                                          │
│  ┌────────────────────────────────▼──────────────────────────────────────┐  │
│  │               SessionKnowledgeGraph (session_graph.py)                 │  │
│  │                                                                        │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────┐ │  │
│  │  │ BGEM3Service │  │ Neo4j Driver │  │ DomainClassifier             │ │  │
│  │  │ (bge_m3.py)  │  │ (Graph DB)   │  │ (domain_classifier.py)       │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────────────────────────┘ │  │
│  │                                                                        │  │
│  │  Node Types:                    Relationships:                        │  │
│  │  - Session                      - CONTAINS (Session→Turn)             │  │
│  │  - Turn                         - HAS_TOPIC (Session→Topic)           │  │
│  │  - Topic                        - RELATED_TO (Session↔Session)        │  │
│  │  - PromptTemplate               - BELONGS_TO (Session→TopicCluster)   │  │
│  │  - TopicCluster                 - FOLLOWS (Turn→Turn)                 │  │
│  │                                 - MENTIONS (Turn→Topic)               │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow: Session Ingestion Pipeline

```
User completes chat session
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. Gateway: ChatSessionStore.addTurn()                          │
│    - Save turn to Redis                                          │
│    - Fire-and-forget: triggerGraphIngestion()                   │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼ (async, no error tracking)
┌─────────────────────────────────────────────────────────────────┐
│ 2. Gateway: GraphSessionService.ingestSession()                  │
│    - POST to backend /api/graph/ingest                           │
│    - No retry logic currently                                    │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Backend: SessionKnowledgeGraph.ingest_session()               │
│    a) Create/update Session node                                 │
│    b) Create Turn nodes with CONTAINS relationship              │
│    c) Extract topics from content (LLM-based)                   │
│    d) Link MENTIONS relationships to Topic nodes                │
│    e) Generate BGE-M3 embeddings for session                    │
│    f) Store embedding in Session node                           │
│    g) Compute similarity with existing sessions                 │
│    h) Create RELATED_TO relationships (threshold > 0.75)        │
│    i) Trigger community detection (if cooldown expired)         │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Backend: Community Detection (async background)              │
│    - Run Neo4j GDS Louvain algorithm                            │
│    - Create/update TopicCluster nodes                           │
│    - Assign BELONGS_TO relationships                            │
│    - In-memory cooldown (not distributed!)                      │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Data Flow: Hybrid Search Pipeline

```
User query: "find sessions about Python"
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. Generate query embedding (BGE-M3)                            │
│    - 1024-dimension dense vector                                │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Neo4j Vector Search (top-50)                                  │
│    - Cosine similarity on Session.embedding                     │
│    - Filter by domain if provided                               │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. Graph Boost (PageRank-style)                                  │
│    - Boost sessions with more RELATED_TO connections            │
│    - Consider cluster membership for context                    │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. LLM Reranking (Mistral via DynamicLLMClient)                 │
│    - Rerank top candidates based on semantic relevance          │
│    - Apply RRF (Reciprocal Rank Fusion)                         │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Return ranked SessionSearchResult[]                          │
│    - sessionId, title, score, topics, clusterName               │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Component Analysis

### 3.1 Backend: SessionKnowledgeGraph (session_graph.py)

**Location:** `backend/src/me4brain/memory/session_graph.py`  
**Lines:** ~1500+  
**Complexity:** High

#### 3.1.1 Key Classes and Methods

| Class/Method | Purpose | Lines | Complexity |
|--------------|---------|-------|------------|
| `SessionKnowledgeGraph` | Main orchestrator | 1500+ | High |
| `ingest_session()` | Session ingestion pipeline | ~200 | High |
| `hybrid_search()` | Multi-stage search | ~150 | High |
| `_run_community_detection()` | Louvain clustering | ~100 | Medium |
| `_compute_session_similarity()` | Embedding comparison | ~50 | Low |
| `get_related_sessions()` | Graph traversal | ~80 | Medium |

#### 3.1.2 Code Quality Observations

**Strengths:**
- Well-structured with clear method separation
- Comprehensive logging with structlog
- Async/await patterns correctly applied
- Type hints throughout

**Weaknesses:**
- Monolithic class (~1500 lines)
- Community detection cooldown is in-memory (not distributed)
- Similarity threshold (0.75) is hardcoded
- No circuit breaker for Neo4j failures
- Fire-and-forget patterns without error propagation

### 3.2 Backend: BGEM3Service (bge_m3.py)

**Location:** `backend/src/me4brain/embeddings/bge_m3.py`  
**Pattern:** Singleton service

#### 3.2.1 Current Implementation

```python
class BGEM3Service:
    """BGE-M3 embedding service - singleton pattern."""
    
    _instance: "BGEM3Service | None" = None
    
    def __init__(self):
        self._model = FlagModel(
            "BAAI/bge-m3",
            use_fp16=True,  # CPU/MPS optimized
            devices=["mps"] if torch.backends.mps.is_available() else ["cpu"],
        )
        self._dim = 1024
```

#### 3.2.2 Performance Characteristics

| Metric | Current Value | Concern |
|--------|---------------|---------|
| Embedding dimension | 1024 | OK |
| Batch size support | Limited | **Issue** |
| Caching | None | **Issue** |
| Device | CPU/MPS | OK for local |
| Memory footprint | ~2GB | High |

### 3.3 Backend: DomainClassifier (domain_classifier.py)

**Location:** `backend/src/me4brain/engine/hybrid_router/domain_classifier.py`

#### 3.3.1 Classification Strategy

```
Query → LLM Classification (Mistral)
           │
           ├─ Success (confidence > threshold) → Return domains
           │
           └─ Degradation (timeout/error)
                    │
                    ├─ Level 1: Keyword fallback
                    │
                    ├─ Level 2: Cached results
                    │
                    └─ Level 3: Default domains
```

#### 3.3.2 Degradation Levels

| Level | Trigger | Strategy | Impact |
|-------|---------|----------|--------|
| 0 | Normal | LLM classification | Full accuracy |
| 1 | LLM timeout (3s) | Keyword matching | Reduced accuracy |
| 2 | Repeated failures | Cache-based | Stale results |
| 3 | System failure | Hardcoded defaults | Minimal functionality |

### 3.4 Frontend: SessionManager (session_manager.ts)

**Location:** `frontend/packages/gateway/src/services/session_manager.ts`  
**Pattern:** Multi-tier cache with pub/sub

#### 3.4.1 Cache Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    SessionManager                            │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────────────┐                                         │
│  │   L1 Cache      │ ← In-memory Map<string, CachedSession>  │
│  │   TTL: 5 min    │   Max: 1000 entries (LRU eviction)      │
│  └────────┬────────┘                                         │
│           │ Miss                                             │
│           ▼                                                  │
│  ┌─────────────────┐                                         │
│  │   L2 Cache      │ ← Redis with TTL                        │
│  │   TTL: 1 hour   │   Key: persan:session:{id}              │
│  └────────┬────────┘                                         │
│           │ Miss                                             │
│           ▼                                                  │
│  ┌─────────────────┐                                         │
│  │   Data Source   │ ← ChatSessionStore (Redis persistent)   │
│  └─────────────────┘                                         │
│                                                               │
│  ┌─────────────────┐                                         │
│  │   Pub/Sub       │ ← Redis channel: persan:invalidation    │
│  │   Invalidation  │   Cross-instance cache sync             │
│  └─────────────────┘                                         │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

#### 3.4.2 Stampede Protection

```typescript
// Current implementation
private async _singleflight<T>(key: string, fn: () => Promise<T>): Promise<T> {
    const existing = this._inFlight.get(key);
    if (existing) return existing;
    
    const promise = fn();
    this._inFlight.set(key, promise);
    
    try {
        return await promise;
    } finally {
        this._inFlight.delete(key);
    }
}
```

### 3.5 Frontend: Canvas & DnD System (Canvas.tsx)

**Location:** `frontend/frontend/src/components/canvas/Canvas.tsx`  
**Library:** @dnd-kit/core, @dnd-kit/sortable

#### 3.5.1 Current DnD Implementation

```typescript
// Simplified structure
<DndContext
    sensors={sensors}
    collisionDetection={closestCenter}
    onDragEnd={handleDragEnd}
>
    <SortableContext items={items} strategy={verticalListSortingStrategy}>
        {items.map((item) => (
            <SortableItem key={item.id} id={item.id} />
        ))}
    </SortableContext>
</DndContext>
```

#### 3.5.2 Capabilities

| Feature | Implemented | Notes |
|---------|-------------|-------|
| Single list sorting | Yes | Basic sortable |
| Cross-list transfer | Partial | Limited |
| Optimistic updates | No | **Gap** |
| Keyboard accessibility | Yes | Via @dnd-kit |
| Touch support | Yes | Via sensors |

### 3.6 Frontend: React Hooks (useSessionGraph.ts)

**Location:** `frontend/frontend/src/hooks/useSessionGraph.ts`

#### 3.6.1 Available Hooks

| Hook | Purpose | Data Fetching | Caching |
|------|---------|---------------|---------|
| `useSessionClusters()` | List all clusters | On mount | fetchedRef |
| `useRelatedSessions(sessionId)` | Related sessions | On sessionId change | None |
| `useSessionSearch()` | Semantic search | Manual trigger | None |
| `useTopics()` | All topics | On mount | None |
| `usePromptLibrary()` | Prompt templates | On mount + manual | None |
| `useConnectedNodes(sessionId)` | Graph exploration | On sessionId change | None |

#### 3.6.2 Code Quality Observations

**Strengths:**
- Clean separation of concerns
- Proper TypeScript interfaces
- Safe null handling with `data ?? []`

**Weaknesses:**
- No SWR-style stale-while-revalidate
- No error state management
- No retry logic
- Manual refetch patterns

---

## 4. Identified Issues & Criticalities

### 4.1 Critical Issues (P0)

#### Issue #1: Fire-and-Forget Async Tasks

**Location:** `chat_session_store.ts:326-327`

```typescript
// Fire-and-forget: indicizza nel Session Knowledge Graph dopo turn assistant
if (turn.role === 'assistant') {
    this.triggerGraphIngestion(sessionId).catch(() => { });  // ⚠️ Errors silently swallowed
}
```

**Impact:** Graph ingestion failures are invisible. Sessions may not be indexed without any indication.

**Fix Priority:** P0 - Critical

**Recommended Fix:**
```typescript
if (turn.role === 'assistant') {
    this.triggerGraphIngestion(sessionId)
        .catch((error) => {
            logger.error('graph_ingestion_failed', { sessionId, error: error.message });
            // Queue for retry
            this.queueForRetry(sessionId);
        });
}
```

#### Issue #2: Embedding Service Singleton Bottleneck

**Location:** `bge_m3.py`

**Problem:** Single embedding model instance processes all requests sequentially.

**Impact:** Under high load, embedding generation becomes a bottleneck.

**Recommended Fix:**
- Implement batch processing queue
- Add embedding cache with LRU eviction
- Consider model replication for horizontal scaling

#### Issue #3: In-Memory Community Detection Cooldown

**Location:** `session_graph.py` (community detection cooldown)

**Problem:** Cooldown tracking uses instance-local variable, not shared across pods.

**Impact:** In multi-instance deployment, community detection runs more frequently than intended, wasting resources.

**Recommended Fix:**
```python
# Use Redis for distributed cooldown
async def _should_run_community_detection(self) -> bool:
    cooldown_key = "jai:community_detection:last_run"
    last_run = await self.redis.get(cooldown_key)
    if last_run and (time.time() - float(last_run)) < COOLDOWN_SECONDS:
        return False
    await self.redis.setex(cooldown_key, COOLDOWN_SECONDS, str(time.time()))
    return True
```

### 4.2 High Priority Issues (P1)

#### Issue #4: Missing Retry Logic in GraphSessionService

**Location:** `graph_session_service.ts`

**Problem:** No retry mechanism for transient failures.

```typescript
// Current - no retry
async ingestSession(...): Promise<boolean> {
    try {
        const response = await fetch(...);
        return response.ok;
    } catch {
        return false;
    }
}
```

**Recommended Fix:**
```typescript
import { retry } from '@persan/shared';

async ingestSession(...): Promise<boolean> {
    return retry(
        async () => {
            const response = await fetch(...);
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            return true;
        },
        { maxAttempts: 3, backoffMs: 1000, exponential: true }
    );
}
```

#### Issue #5: Hardcoded Similarity Threshold

**Location:** `session_graph.py`

```python
SIMILARITY_THRESHOLD = 0.75  # Hardcoded
```

**Problem:** No adaptive calibration based on corpus statistics.

**Recommended Fix:**
- Compute corpus-wide similarity distribution
- Use percentile-based thresholds (e.g., top 10%)
- Allow per-domain threshold configuration

#### Issue #6: No Batch Embedding Operations

**Location:** `bge_m3.py`

**Problem:** Embeddings generated one-by-one, missing batch efficiency gains.

**Evidence from SOTA research:**
> "Implement caching strategies for frequently accessed embeddings... Optimize batching strategies for large batch sizes and high training throughput" - BGE-M3 best practices

**Recommended Fix:**
```python
async def embed_batch(self, texts: list[str], batch_size: int = 32) -> list[np.ndarray]:
    """Batch embed multiple texts for efficiency."""
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_embeddings = self._model.encode(batch, max_length=8192)
        embeddings.extend(batch_embeddings)
    return embeddings
```

### 4.3 Medium Priority Issues (P2)

#### Issue #7: Simple LRU Eviction in SessionManager

**Location:** `session_manager.ts`

**Problem:** Basic LRU without access frequency consideration.

**SOTA practice:** Adaptive TTL based on access frequency.

#### Issue #8: No Error State in React Hooks

**Location:** `useSessionGraph.ts`

**Problem:** Hooks don't expose error states to UI.

```typescript
// Current
export function useSessionClusters() {
    const [clusters, setClusters] = useState<SessionCluster[]>([]);
    const [loading, setLoading] = useState(false);
    // ⚠️ No error state
```

**Recommended Fix:**
```typescript
export function useSessionClusters() {
    const [clusters, setClusters] = useState<SessionCluster[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<Error | null>(null);
    
    const fetchClusters = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await graphFetch<SessionCluster[]>('/api/graph/clusters');
            setClusters(data ?? []);
        } catch (err) {
            setError(err instanceof Error ? err : new Error('Unknown error'));
        } finally {
            setLoading(false);
        }
    }, []);
```

#### Issue #9: Limited Cross-List DnD

**Location:** `Canvas.tsx`

**Problem:** Basic sortable implementation without full cross-list transfer support.

**SOTA practice (dnd-kit 2025):**
```typescript
// Use onDragOver for real-time updates during drag
<DragDropProvider
    onDragOver={(event) => {
        setItems((items) => move(items, event));
    }}
    onDragEnd={(event) => {
        if (event.canceled) {
            setItems(snapshot.current);
            return;
        }
        // Persist to backend
    }}
>
```

---

## 5. Best Practices Research (SOTA 2025-2026)

### 5.1 GraphRAG Architecture Best Practices

Based on research from ACL 2025, Neo4j Nodes 2025, and industry publications:

#### 5.1.1 Hybrid Retrieval Pipeline

**SOTA Pattern (2026):**
```
Query → Entity Extraction (SpaCy + LLM) → Seed Nodes
     │
     ├── Dense Vector Search (BGE-M3, top-50)
     │
     ├── Lexical/BM25 Search (keyword backup)
     │
     ├── 1-hop Graph Traversal (from seed nodes)
     │
     ├── Subgraph Extraction
     │
     ├── Neural Reranker (cross-encoder)
     │
     └── RRF Fusion → Final Results
```

**Key Insight:** "Most production teams aren't using pure GraphRAG. They're running hybrid setups: vector search for the initial retrieval pass, graph traversal for relationship expansion, then reranking before feeding to the LLM."

#### 5.1.2 GraphRAG Performance Benchmarks

| Metric | Pure RAG | GraphRAG | Improvement |
|--------|----------|----------|-------------|
| Hallucination rate | Baseline | -6% | ACL 2025 FinanceBench |
| Token usage | Baseline | -80% | ACL 2025 |
| Multi-hop reasoning | 49.9% | 94.2% | Cedars-Sinai KRAGEN |
| Retrieval precision | Baseline | +20-35% | Neo4j Nodes 2025 |

#### 5.1.3 Recommended Graph Schema Enhancements

**Current JAI Schema:**
```
(Session)-[:CONTAINS]->(Turn)
(Session)-[:HAS_TOPIC]->(Topic)
(Session)-[:RELATED_TO]->(Session)
(Session)-[:BELONGS_TO]->(TopicCluster)
```

**Enhanced Schema (SOTA):**
```
// Add temporal relationships
(Turn)-[:FOLLOWS {timestamp}]->(Turn)

// Add semantic entity extraction
(Turn)-[:MENTIONS]->(Entity {type, confidence})
(Entity)-[:RELATED_TO {relation_type}]->(Entity)

// Add user context
(Session)-[:CREATED_BY]->(User)
(User)-[:INTERESTED_IN]->(Topic)

// Add provenance tracking
(Session)-[:DERIVED_FROM {method}]->(Source)
```

### 5.2 Embedding Best Practices (BGE-M3 2025-2026)

#### 5.2.1 Performance Optimization

**From FlagEmbedding and SOTA research:**

| Practice | Implementation | Benefit |
|----------|----------------|---------|
| **Batch processing** | `batch_size=32, max_length=8192` | 3-5x throughput |
| **FP16 mode** | `use_fp16=True` | 50% memory, faster |
| **Multi-vector retrieval** | Dense + sparse + multi-vector | Higher recall |
| **Embedding caching** | Redis with TTL | Reduce compute 80%+ |
| **Dimension reduction** | PCA to 512 for storage | 50% storage savings |

#### 5.2.2 Recommended Caching Strategy

```python
class EmbeddingCache:
    """LRU cache for embeddings with Redis backend."""
    
    def __init__(self, redis_client, max_local_size=10000):
        self.redis = redis_client
        self.local_cache = LRUCache(maxsize=max_local_size)
    
    async def get_or_compute(self, text: str) -> np.ndarray:
        # Hash-based key
        key = f"emb:{hashlib.sha256(text.encode()).hexdigest()[:16]}"
        
        # L1: Local cache
        if key in self.local_cache:
            return self.local_cache[key]
        
        # L2: Redis cache
        cached = await self.redis.get(key)
        if cached:
            embedding = np.frombuffer(cached, dtype=np.float32)
            self.local_cache[key] = embedding
            return embedding
        
        # Compute
        embedding = self.model.encode(text)
        
        # Store
        await self.redis.setex(key, 86400, embedding.tobytes())
        self.local_cache[key] = embedding
        
        return embedding
```

### 5.3 Community Detection Best Practices

#### 5.3.1 Algorithm Comparison

| Algorithm | Speed | Quality | Use Case |
|-----------|-------|---------|----------|
| **Louvain** | Fast | Good | Current JAI choice |
| **Leiden** | Medium | Better | Recommended upgrade |
| **Label Propagation** | Very fast | Fair | Real-time updates |
| **Spectral** | Slow | Excellent | Small graphs |

#### 5.3.2 Incremental Clustering (SOTA)

**Problem:** Full Louvain on every update is expensive.

**Solution:** Incremental community updates:
```python
async def incremental_cluster_update(self, new_session: Session):
    """Update clusters incrementally without full recomputation."""
    
    # Find most similar existing session
    similar = await self.find_most_similar(new_session)
    
    if similar and similar.similarity > 0.85:
        # Assign to same cluster
        await self.assign_to_cluster(new_session, similar.cluster_id)
    else:
        # Create singleton cluster, merge later
        await self.create_singleton_cluster(new_session)
    
    # Periodically run full Louvain (e.g., hourly)
    if await self._should_run_full_clustering():
        asyncio.create_task(self._run_full_clustering())
```

### 5.4 Caching Best Practices (Redis 2025-2026)

#### 5.4.1 Multi-Tier Caching Pattern

```
┌─────────────────────────────────────────────────────────────┐
│                     L1 (In-Memory)                           │
│  - Size: 1000 entries                                       │
│  - TTL: 30-60 seconds                                       │
│  - Adaptive TTL based on access frequency                   │
└─────────────────────────────────────────────────────────────┘
                           │ Miss
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     L2 (Redis)                               │
│  - TTL: 5-60 minutes                                        │
│  - Write-through from L1                                    │
│  - Pub/Sub for cross-instance invalidation                  │
└─────────────────────────────────────────────────────────────┘
                           │ Miss
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   Database / Source                          │
└─────────────────────────────────────────────────────────────┘
```

#### 5.4.2 Stampede Protection Strategies (SOTA 2026)

| Strategy | Implementation | Use Case |
|----------|----------------|----------|
| **Singleflight** | Request coalescing | Default |
| **Probabilistic early refresh** | `ttl * random(0.8, 1.0)` | Spread expiry |
| **Distributed locking** | `SETNX` with timeout | Critical data |
| **Background refresh** | Return stale, refresh async | High availability |

**Combined Pattern:**
```python
class StampedeResistantCache:
    async def get(self, key: str, fetch_fn, ttl: int = 300, beta: float = 1.0):
        cached = await self.redis.hgetall(f"cache:{key}")
        
        if cached:
            value = json.loads(cached.get('value'))
            delta = float(cached.get('delta', 1))
            cached_at = float(cached.get('cached_at', 0))
            age = time.time() - cached_at
            
            # Fresh data
            if age < ttl:
                # Probabilistic early refresh
                if random.random() < (age / ttl) * beta:
                    asyncio.create_task(self._background_refresh(key, fetch_fn))
                return value
        
        # Cache miss - use singleflight
        return await self._singleflight_fetch(key, fetch_fn, ttl)
```

### 5.5 Drag-and-Drop Best Practices (dnd-kit 2025)

#### 5.5.1 Modern DnD Patterns

**Optimistic Updates:**
```typescript
function MultiListApp() {
    const [items, setItems] = useState({...});
    const snapshot = useRef(structuredClone(items));
    
    return (
        <DragDropProvider
            onDragStart={() => {
                // Save snapshot for cancellation
                snapshot.current = structuredClone(items);
            }}
            onDragOver={(event) => {
                // Real-time visual updates during drag
                setItems((items) => move(items, event));
            }}
            onDragEnd={(event) => {
                if (event.canceled) {
                    // Restore on cancel
                    setItems(snapshot.current);
                    return;
                }
                // Persist to backend
                persistOrder(items);
            }}
        >
            {/* ... */}
        </DragDropProvider>
    );
}
```

#### 5.5.2 Accessibility Requirements

| Feature | Implementation |
|---------|----------------|
| Keyboard navigation | Arrow keys + Enter/Space |
| Screen reader | ARIA live regions |
| Focus management | Auto-focus on drop |
| Cancel gesture | Escape key |

---

## 6. Gap Analysis

### 6.1 Feature Gap Matrix

| Feature | Current State | SOTA 2026 | Gap | Priority |
|---------|---------------|-----------|-----|----------|
| **Hybrid search** | Vector + Graph + LLM rerank | + BM25 lexical | Medium | P1 |
| **Entity extraction** | LLM-based topics | SpaCy NER + LLM | Low | P2 |
| **Embedding caching** | None | Multi-tier LRU | High | P0 |
| **Batch embeddings** | Sequential | Batch (32+) | High | P1 |
| **Community detection** | Full Louvain | Incremental + Leiden | Medium | P2 |
| **Cross-list DnD** | Basic sortable | Full multi-list | Medium | P2 |
| **Optimistic updates** | None | Snapshot + rollback | Medium | P2 |
| **Error handling** | Minimal | Full observability | High | P1 |
| **Distributed cooldown** | In-memory | Redis-backed | High | P0 |

### 6.2 Architecture Gap Analysis

#### 6.2.1 Backend Gaps

| Component | Gap | Impact | Effort |
|-----------|-----|--------|--------|
| SessionKnowledgeGraph | Monolithic class | Maintainability | High |
| BGEM3Service | No caching | Performance | Medium |
| DomainClassifier | Hardcoded thresholds | Flexibility | Low |
| Community detection | Not distributed | Scaling | Medium |

#### 6.2.2 Frontend Gaps

| Component | Gap | Impact | Effort |
|-----------|-----|--------|--------|
| useSessionGraph hooks | No error states | UX | Low |
| GraphSessionService | No retry logic | Reliability | Low |
| Canvas DnD | Limited cross-list | Feature | Medium |
| SessionManager | Basic LRU eviction | Performance | Low |

---

## 7. Optimization Plan

### 7.1 Phase 1: Critical Stabilization (Week 1-2)

#### 7.1.1 Fix Fire-and-Forget Pattern

**File:** `frontend/packages/gateway/src/services/chat_session_store.ts`

**Changes:**
```typescript
// Add retry queue
private retryQueue: Map<string, { sessionId: string; attempts: number }> = new Map();

private async triggerGraphIngestion(sessionId: string): Promise<void> {
    try {
        const { graphSessionService } = await import('./graph_session_service.js');
        const session = await this.getSession(sessionId);
        if (!session || !session.turns.length) return;

        const success = await graphSessionService.ingestSession(
            sessionId,
            session.title,
            session.turns.map((t) => ({
                role: t.role,
                content: t.content,
                timestamp: t.timestamp,
            })),
            session.created_at,
            session.updated_at,
        );
        
        if (!success) {
            this.queueForRetry(sessionId);
        }
    } catch (error) {
        console.error('[ChatSessionStore] Graph ingestion failed:', (error as Error).message);
        this.queueForRetry(sessionId);
    }
}

private queueForRetry(sessionId: string): void {
    const existing = this.retryQueue.get(sessionId);
    if (existing && existing.attempts >= 3) {
        console.error('[ChatSessionStore] Max retries exceeded for:', sessionId);
        return;
    }
    this.retryQueue.set(sessionId, {
        sessionId,
        attempts: (existing?.attempts ?? 0) + 1,
    });
}
```

#### 7.1.2 Add Retry Logic to GraphSessionService

**File:** `frontend/packages/gateway/src/services/graph_session_service.ts`

**Changes:**
```typescript
import { sleep } from '@persan/shared';

async function fetchWithRetry<T>(
    url: string,
    options: RequestInit,
    maxAttempts = 3,
    backoffMs = 1000,
): Promise<T | null> {
    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            const response = await fetch(url, options);
            if (response.ok) {
                return await response.json();
            }
            if (response.status >= 500) {
                throw new Error(`Server error: ${response.status}`);
            }
            return null;
        } catch (error) {
            if (attempt === maxAttempts) {
                console.error(`[GraphSessionService] Failed after ${maxAttempts} attempts:`, error);
                return null;
            }
            await sleep(backoffMs * Math.pow(2, attempt - 1));
        }
    }
    return null;
}
```

#### 7.1.3 Distributed Community Detection Cooldown

**File:** `backend/src/me4brain/memory/session_graph.py`

**Changes:**
```python
COMMUNITY_COOLDOWN_KEY = "jai:community_detection:last_run"
COMMUNITY_COOLDOWN_SECONDS = 300  # 5 minutes

async def _should_run_community_detection(self) -> bool:
    """Check cooldown using distributed Redis lock."""
    if not self._redis:
        # Fallback to in-memory
        return self._check_local_cooldown()
    
    try:
        last_run = await self._redis.get(COMMUNITY_COOLDOWN_KEY)
        if last_run:
            elapsed = time.time() - float(last_run)
            if elapsed < COMMUNITY_COOLDOWN_SECONDS:
                return False
        
        # Acquire lock and set cooldown
        acquired = await self._redis.setnx(
            f"{COMMUNITY_COOLDOWN_KEY}:lock",
            str(time.time()),
        )
        if acquired:
            await self._redis.setex(
                COMMUNITY_COOLDOWN_KEY,
                COMMUNITY_COOLDOWN_SECONDS,
                str(time.time()),
            )
            await self._redis.delete(f"{COMMUNITY_COOLDOWN_KEY}:lock")
            return True
        return False
    except Exception as e:
        logger.warning("community_cooldown_check_failed", error=str(e))
        return self._check_local_cooldown()
```

### 7.2 Phase 2: Embedding Optimization (Week 3-4)

#### 7.2.1 Implement Embedding Cache

**New File:** `backend/src/me4brain/embeddings/embedding_cache.py`

```python
"""Embedding cache with multi-tier storage."""

import hashlib
from typing import Optional
import numpy as np
from cachetools import LRUCache
import structlog

logger = structlog.get_logger(__name__)


class EmbeddingCache:
    """Multi-tier embedding cache (L1: memory, L2: Redis)."""
    
    def __init__(
        self,
        redis_client,
        local_max_size: int = 10000,
        redis_ttl_seconds: int = 86400,
    ):
        self._redis = redis_client
        self._local = LRUCache(maxsize=local_max_size)
        self._redis_ttl = redis_ttl_seconds
        self._hits = 0
        self._misses = 0
    
    def _compute_key(self, text: str) -> str:
        """Compute cache key from text hash."""
        return f"emb:{hashlib.sha256(text.encode()).hexdigest()[:16]}"
    
    async def get(self, text: str) -> Optional[np.ndarray]:
        """Get embedding from cache (L1 then L2)."""
        key = self._compute_key(text)
        
        # L1: Local cache
        if key in self._local:
            self._hits += 1
            return self._local[key]
        
        # L2: Redis cache
        if self._redis:
            try:
                cached = await self._redis.get(key)
                if cached:
                    embedding = np.frombuffer(cached, dtype=np.float32)
                    self._local[key] = embedding  # Populate L1
                    self._hits += 1
                    return embedding
            except Exception as e:
                logger.warning("embedding_cache_redis_error", error=str(e))
        
        self._misses += 1
        return None
    
    async def set(self, text: str, embedding: np.ndarray) -> None:
        """Store embedding in cache (both L1 and L2)."""
        key = self._compute_key(text)
        
        # L1: Local cache
        self._local[key] = embedding
        
        # L2: Redis cache
        if self._redis:
            try:
                await self._redis.setex(key, self._redis_ttl, embedding.tobytes())
            except Exception as e:
                logger.warning("embedding_cache_redis_set_error", error=str(e))
    
    def stats(self) -> dict:
        """Return cache statistics."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0,
            "local_size": len(self._local),
        }
```

#### 7.2.2 Add Batch Embedding Support

**File:** `backend/src/me4brain/embeddings/bge_m3.py`

**Changes:**
```python
async def embed_batch(
    self,
    texts: list[str],
    batch_size: int = 32,
    max_length: int = 8192,
) -> list[np.ndarray]:
    """Batch embed multiple texts for efficiency.
    
    Args:
        texts: List of texts to embed
        batch_size: Processing batch size (default 32)
        max_length: Maximum token length
    
    Returns:
        List of embeddings in same order as input
    """
    if not texts:
        return []
    
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        
        # Check cache first
        cached = []
        to_compute = []
        to_compute_indices = []
        
        for j, text in enumerate(batch):
            cached_emb = await self._cache.get(text)
            if cached_emb is not None:
                cached.append((i + j, cached_emb))
            else:
                to_compute.append(text)
                to_compute_indices.append(i + j)
        
        # Compute missing embeddings
        if to_compute:
            batch_embeddings = self._model.encode(
                to_compute,
                batch_size=len(to_compute),
                max_length=max_length,
            )['dense_vecs']
            
            # Cache and collect
            for text, idx, emb in zip(to_compute, to_compute_indices, batch_embeddings):
                await self._cache.set(text, emb)
                cached.append((idx, emb))
        
        # Sort by original index
        cached.sort(key=lambda x: x[0])
        embeddings.extend([emb for _, emb in cached])
    
    return embeddings
```

### 7.3 Phase 3: Frontend Enhancements (Week 5-6)

#### 7.3.1 Add Error States to Hooks

**File:** `frontend/frontend/src/hooks/useSessionGraph.ts`

**Changes:**
```typescript
interface UseQueryResult<T> {
    data: T;
    loading: boolean;
    error: Error | null;
    refetch: () => Promise<void>;
}

export function useSessionClusters(): UseQueryResult<SessionCluster[]> {
    const [clusters, setClusters] = useState<SessionCluster[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<Error | null>(null);
    const fetchedRef = useRef(false);

    const fetchClusters = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const data = await graphFetch<SessionCluster[]>('/api/graph/clusters');
            const safeData = (data ?? []).map(cluster => ({
                ...cluster,
                topics: cluster.topics || [],
                sessionIds: cluster.sessionIds || [],
            }));
            setClusters(safeData);
        } catch (err) {
            setError(err instanceof Error ? err : new Error('Failed to fetch clusters'));
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        if (!fetchedRef.current) {
            fetchedRef.current = true;
            fetchClusters();
        }
    }, [fetchClusters]);

    return { data: clusters, loading, error, refetch: fetchClusters };
}
```

#### 7.3.2 Enhanced DnD with Optimistic Updates

**File:** `frontend/frontend/src/components/canvas/Canvas.tsx`

**Changes:**
```typescript
import { DragDropProvider, move } from '@dnd-kit/react';
import { useRef } from 'react';

function Canvas({ initialItems }) {
    const [items, setItems] = useState(initialItems);
    const snapshot = useRef<typeof items>(null);
    
    const handleDragStart = () => {
        // Save snapshot for potential rollback
        snapshot.current = structuredClone(items);
    };
    
    const handleDragOver = (event) => {
        // Real-time visual update during drag
        setItems((current) => move(current, event));
    };
    
    const handleDragEnd = async (event) => {
        if (event.canceled) {
            // Restore on cancel
            setItems(snapshot.current!);
            return;
        }
        
        try {
            // Persist to backend
            await saveItemOrder(items);
        } catch (error) {
            // Rollback on error
            setItems(snapshot.current!);
            toast.error('Failed to save order');
        }
    };
    
    return (
        <DragDropProvider
            onDragStart={handleDragStart}
            onDragOver={handleDragOver}
            onDragEnd={handleDragEnd}
        >
            {/* ... */}
        </DragDropProvider>
    );
}
```

### 7.4 Phase 4: Advanced Optimizations (Week 7-8)

#### 7.4.1 Implement BM25 Lexical Search

**New File:** `backend/src/me4brain/memory/lexical_search.py`

```python
"""BM25 lexical search for hybrid retrieval."""

from rank_bm25 import BM25Okapi
import structlog

logger = structlog.get_logger(__name__)


class LexicalSearcher:
    """BM25-based lexical search for recall boost."""
    
    def __init__(self):
        self._corpus: list[str] = []
        self._ids: list[str] = []
        self._bm25: BM25Okapi | None = None
    
    def index(self, documents: list[tuple[str, str]]) -> None:
        """Index documents for BM25 search.
        
        Args:
            documents: List of (id, text) tuples
        """
        self._ids = [doc[0] for doc in documents]
        self._corpus = [doc[1].lower().split() for doc in documents]
        self._bm25 = BM25Okapi(self._corpus)
        logger.info("lexical_index_built", doc_count=len(documents))
    
    def search(self, query: str, top_k: int = 50) -> list[tuple[str, float]]:
        """Search for documents matching query.
        
        Args:
            query: Search query
            top_k: Number of results to return
        
        Returns:
            List of (document_id, score) tuples
        """
        if not self._bm25:
            return []
        
        tokenized_query = query.lower().split()
        scores = self._bm25.get_scores(tokenized_query)
        
        # Get top-k indices
        top_indices = sorted(
            range(len(scores)),
            key=lambda i: scores[i],
            reverse=True,
        )[:top_k]
        
        return [(self._ids[i], scores[i]) for i in top_indices if scores[i] > 0]
```

#### 7.4.2 Implement RRF Fusion

**File:** `backend/src/me4brain/memory/session_graph.py`

**Changes:**
```python
def _reciprocal_rank_fusion(
    self,
    dense_results: list[tuple[str, float]],
    lexical_results: list[tuple[str, float]],
    graph_results: list[tuple[str, float]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Combine multiple result lists using Reciprocal Rank Fusion.
    
    Args:
        dense_results: Results from vector search
        lexical_results: Results from BM25 search
        graph_results: Results from graph traversal
        k: RRF parameter (default 60)
    
    Returns:
        Fused results sorted by combined score
    """
    scores: dict[str, float] = {}
    
    for rank, (doc_id, _) in enumerate(dense_results):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
    
    for rank, (doc_id, _) in enumerate(lexical_results):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
    
    for rank, (doc_id, _) in enumerate(graph_results):
        scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
    
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

#### 7.4.3 Incremental Community Detection

**File:** `backend/src/me4brain/memory/session_graph.py`

**Changes:**
```python
async def _incremental_cluster_assignment(self, session_id: str) -> str:
    """Assign session to cluster incrementally without full Louvain.
    
    Strategy:
    1. Find most similar existing session
    2. If similarity > threshold, assign to same cluster
    3. Otherwise, create singleton cluster
    4. Periodically run full clustering in background
    """
    # Find most similar session
    similar_sessions = await self.get_related_sessions(session_id, limit=1)
    
    if similar_sessions and similar_sessions[0].score > 0.85:
        # Assign to same cluster
        similar_id = similar_sessions[0].session_id
        cluster_id = await self._get_session_cluster(similar_id)
        if cluster_id:
            await self._assign_to_cluster(session_id, cluster_id)
            return cluster_id
    
    # Create singleton cluster
    cluster_id = f"cluster_{session_id}"
    await self._create_cluster(cluster_id, sessions=[session_id])
    
    # Schedule full clustering if needed
    if await self._should_run_full_clustering():
        asyncio.create_task(self._run_full_clustering())
    
    return cluster_id
```

---

## 8. Implementation Priority Matrix

### 8.1 Priority Classification

| Priority | Definition | Timeline |
|----------|------------|----------|
| **P0** | Critical - System stability | Week 1 |
| **P1** | High - Performance/reliability | Week 2-3 |
| **P2** | Medium - Feature enhancement | Week 4-6 |
| **P3** | Low - Nice to have | Week 7+ |

### 8.2 Implementation Backlog

| ID | Task | Priority | Effort | Impact | Owner |
|----|------|----------|--------|--------|-------|
| **OPT-001** | Fix fire-and-forget pattern | P0 | Low | High | Backend |
| **OPT-002** | Add retry logic to GraphSessionService | P0 | Low | High | Frontend |
| **OPT-003** | Distributed community cooldown | P0 | Medium | High | Backend |
| **OPT-004** | Implement embedding cache | P1 | Medium | High | Backend |
| **OPT-005** | Add batch embedding support | P1 | Medium | High | Backend |
| **OPT-006** | Add error states to React hooks | P1 | Low | Medium | Frontend |
| **OPT-007** | Implement BM25 lexical search | P2 | Medium | Medium | Backend |
| **OPT-008** | Implement RRF fusion | P2 | Low | Medium | Backend |
| **OPT-009** | Enhanced DnD with optimistic updates | P2 | Medium | Medium | Frontend |
| **OPT-010** | Incremental community detection | P2 | High | Medium | Backend |
| **OPT-011** | Adaptive similarity thresholds | P2 | Medium | Low | Backend |
| **OPT-012** | Cross-list DnD support | P2 | Medium | Medium | Frontend |
| **OPT-013** | Adaptive TTL in SessionManager | P3 | Low | Low | Frontend |
| **OPT-014** | Entity extraction with SpaCy | P3 | High | Medium | Backend |

### 8.3 Dependency Graph

```
OPT-001 ─────────────┐
OPT-002 ─────────────┼──► System Stability
OPT-003 ─────────────┘

OPT-004 ──────┬──► OPT-005 ──► Embedding Performance
              │
OPT-007 ──────┼──► OPT-008 ──► Hybrid Search
              │
OPT-010 ──────┘

OPT-006 ──────────────────────► Frontend Reliability

OPT-009 ──────┬──► OPT-012 ──► DnD Enhancement
              │
OPT-013 ──────┘
```

---

## 9. Testing Strategy

### 9.1 Test Coverage Targets

| Component | Current | Target | Priority |
|-----------|---------|--------|----------|
| SessionKnowledgeGraph | ~40% | 80% | P1 |
| BGEM3Service | ~20% | 70% | P1 |
| EmbeddingCache (new) | 0% | 90% | P0 |
| GraphSessionService | ~30% | 80% | P1 |
| SessionManager | ~50% | 85% | P2 |
| useSessionGraph hooks | ~0% | 70% | P2 |
| Canvas DnD | ~20% | 70% | P2 |

### 9.2 Critical Test Scenarios

#### 9.2.1 Backend Tests

```python
# tests/unit/test_embedding_cache.py
class TestEmbeddingCache:
    async def test_l1_hit(self):
        """L1 cache should return immediately on hit."""
    
    async def test_l2_fallback(self):
        """Should fallback to L2 on L1 miss."""
    
    async def test_cache_population(self):
        """L1 should be populated after L2 hit."""
    
    async def test_batch_embedding_with_cache(self):
        """Batch should use cache for known texts."""


# tests/unit/test_session_graph.py
class TestDistributedCooldown:
    async def test_cooldown_uses_redis(self):
        """Cooldown should use Redis for distributed tracking."""
    
    async def test_cooldown_fallback_to_local(self):
        """Should fallback to local on Redis failure."""


class TestRRFFusion:
    def test_single_source(self):
        """RRF should work with single source."""
    
    def test_multiple_sources(self):
        """RRF should combine multiple sources correctly."""
    
    def test_tie_breaking(self):
        """RRF should handle ties deterministically."""
```

#### 9.2.2 Frontend Tests

```typescript
// __tests__/useSessionGraph.test.ts
describe('useSessionClusters', () => {
    it('should expose error state on fetch failure', async () => {
        // Mock fetch to fail
        mockFetch.mockRejectedValue(new Error('Network error'));
        
        const { result } = renderHook(() => useSessionClusters());
        
        await waitFor(() => {
            expect(result.current.error).toBeInstanceOf(Error);
            expect(result.current.error?.message).toBe('Network error');
        });
    });
});

// __tests__/graph_session_service.test.ts
describe('GraphSessionService retry', () => {
    it('should retry on 5xx errors', async () => {
        mockFetch
            .mockResolvedValueOnce({ ok: false, status: 503 })
            .mockResolvedValueOnce({ ok: true, json: () => Promise.resolve({}) });
        
        const result = await graphSessionService.ingestSession(...);
        
        expect(mockFetch).toHaveBeenCalledTimes(2);
        expect(result).toBe(true);
    });
});
```

### 9.3 Performance Benchmarks

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Embedding generation (single) | ~200ms | ~200ms | Baseline |
| Embedding generation (batch 32) | N/A | <1s | New capability |
| Cache hit rate | N/A | >80% | New metric |
| Session ingestion P95 | ~2s | <1s | With caching |
| Hybrid search P95 | ~3s | <2s | With BM25 + RRF |
| Community detection | ~10s | <5s | Incremental |

---

## Implementation Status (2026-03-23)

### P0 Tasks - Critical Stabilization ✅ COMPLETED

| Task | Description | Status | Files |
|------|-------------|--------|-------|
| **OPT-001** | Fix fire-and-forget pattern | ✅ Complete | `chat_session_store.ts` |
| **OPT-002** | Add retry logic to GraphSessionService | ✅ Complete | `retry.ts`, `graph_session_service.ts` |
| **OPT-003** | Distributed community detection cooldown | ✅ Complete | `session_graph.py` |

### OPT-001: Fire-and-Forget Pattern Fix

**Problem**: Graph ingestion errors were silently swallowed with `.catch(() => {})`

**Solution**:
- Added retry queue tracking in-flight graph ingestion requests
- Implemented proper error logging with structured logging
- Added `GRAPH_INGESTION_MAX_RETRIES` (3 attempts) with exponential backoff

**Files Modified**:
- `frontend/packages/gateway/src/services/chat_session_store.ts`

### OPT-002: Retry Logic Implementation

**Solution**:
- Created `retry.ts` utility module with SOTA 2026 patterns:
  - Exponential backoff with jitter (base 2, 0.8-1.2 range)
  - Non-retryable error codes support
  - Deadline-aware retry
  - Circuit breaker pattern (CLOSED/OPEN/HALF_OPEN states)
- Integrated retry into `GraphSessionService.ingestSession()`
- Added retry to `ChatSessionStore.triggerGraphIngestion()`

**Files Created**:
- `frontend/packages/shared/src/retry.ts` (360 lines)
- `frontend/packages/shared/src/__tests__/retry.test.ts` (317 lines, 24 tests)

**Files Modified**:
- `frontend/packages/shared/src/index.ts` (added export)
- `frontend/packages/gateway/src/services/graph_session_service.ts`
- `frontend/packages/gateway/src/services/chat_session_store.ts`

### OPT-003: Distributed Community Detection Cooldown

**Problem**: In-memory cooldown tracking not shared across pods

**Solution**:
- Implemented Redis-based distributed cooldown with atomic `SETEX`
- Added lazy Redis initialization with fallback to in-memory
- Per-tenant cooldown keys: `me4brain:community_detection:last_run:{tenant_id}`
- Cooldown period: 5 minutes (300 seconds)

**Files Modified**:
- `backend/src/me4brain/memory/session_graph.py`

### Test Coverage

| Component | Tests | Status |
|-----------|-------|--------|
| `retry.ts` | 24 tests | ✅ All passing |
| Backend import | N/A | ✅ Verified |
| Frontend build | 4 packages | ✅ Pass |

### Next Steps (P1-P3)

| Priority | Task | Description |
|----------|------|-------------|
| P1 | OPT-004 | Embedding cache implementation |
| P1 | OPT-005 | Batch embedding support |
| P1 | OPT-006 | Error states in React hooks |
| P2 | OPT-007 | BM25 lexical search |
| P2 | OPT-008 | RRF fusion |
| P2 | OPT-009 | Enhanced DnD with optimistic updates |
| P2 | OPT-010 | Incremental community detection |
| P2 | OPT-011 | Adaptive similarity thresholds |
| P2 | OPT-012 | Cross-list DnD support |

---

## 10. References

### 10.1 Research Papers & Publications

1. **GraphRAG (ACL 2025)**: "Leveraging Graph-Based Efficiency to Minimize Hallucinations in LLM-Driven RAG for Finance Data" - BNP Paribas, Neo4j
2. **BGE-M3 (arXiv 2024)**: "BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings Through Self-Knowledge Distillation"
3. **KRAGEN (Cedars-Sinai)**: Knowledge graph for Alzheimer's research achieving 94.2% accuracy
4. **KG²RAG**: "Knowledge Graph-Guided Retrieval Augmented Generation" - arXiv

### 10.2 Industry Best Practices

1. **Neo4j Nodes 2025**: "Enhancing RAG with GraphRAG Patterns in Neo4j"
2. **Gartner 2025**: Knowledge Graphs as "Critical Enabler" for GenAI
3. **Redis Caching Patterns**: Multi-tier caching with stampede protection
4. **dnd-kit Documentation**: Modern drag-and-drop patterns for React

### 10.3 Related JAI Documentation

1. `docs/retrieval-system-implementation-plan-v2.md` - Retrieval system refactoring
2. `TDD-auto-session-title.md` - Session title generation spec
3. `AGENTS.md` - Coding guidelines and project structure

---

## Appendix A: Code Examples

### A.1 Complete EmbeddingCache Implementation

See Section 7.2.1 for full implementation.

### A.2 Complete GraphSessionService with Retry

See Section 7.1.2 for full implementation.

### A.3 Enhanced useSessionGraph Hook

See Section 7.3.1 for full implementation.

---

**Document End**

*This analysis document is intended as a reference for development planning. Code modifications should follow the project's coding standards as defined in `AGENTS.md` and include appropriate test coverage.*
