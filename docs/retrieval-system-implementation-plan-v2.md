# JAI Retrieval System - Implementation Plan v2.0

**Document Version:** 2.0  
**Created:** 2026-03-23  
**Status:** Active  
**Priority:** Critical

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Current Architecture Analysis](#2-current-architecture-analysis)
3. [Wave 0: Critical Stabilization (Week 1)](#3-wave-0-critical-stabilization-week-1)
4. [Wave 1: Contracts & Coherence (Weeks 2-4)](#4-wave-1-contracts--coherence-weeks-2-4)
5. [Wave 2: Retrieval Core Refactor (Weeks 5-8)](#5-wave-2-retrieval-core-refactor-weeks-5-8)
6. [Wave 3: Domain Hardening (Weeks 9-11)](#6-wave-3-domain-hardening-weeks-9-11)
7. [Wave 4: QA/Perf/SLO (Weeks 12-13)](#7-wave-4-qapervslo-weeks-12-13)
8. [Canonical Tool Contract Schema](#8-canonical-tool-contract-schema)
9. [Retrieval V2 Architecture](#9-retrieval-v2-architecture)
10. [SLO/KPI Targets](#10-slokpi-targets)
11. [Risk Register](#11-risk-register)
12. [Testing Strategy](#12-testing-strategy)

---

## 1. Executive Summary

### Problem Statement

The JAI retrieval system suffers from **systemic architectural debt** that manifests as:

| Issue | Impact | Frequency |
|-------|--------|-----------|
| Double intent layers (engine + router) | Redundancy, latency, divergent decisions | Constant |
| Domain taxonomy drift | Wrong domain → wrong filter → zero useful tools | High |
| Weak fallback mechanisms | User gets "no tools found" on misrouting | High |
| Destructive index rebuilds | Service disruption, hash detection fragility | On startup |
| Monolithic domain modules | Hard to test, regression risk, security exposure | Constant |
| Placeholder domains | False routing positives, degraded trust | Constant |

### Target State

A retrieval system with:
- **Single source of truth** for tool metadata (Canonical Tool Contract)
- **Top-K domain scoring** instead of hard 1-domain assignment
- **Mandatory rescue policy** for zero-result scenarios
- **Incremental indexing** with no destructive operations
- **Decomposed domain modules** for maintainability
- **Operational SLOs** with measurable quality gates

### Expected Outcomes

| Metric | Current | Target |
|--------|---------|--------|
| Tool selection recall@10 | ~0.85 | >0.95 |
| Wrong-domain hard failures | ~5% | <1% |
| Zero-result retrieval rate | ~8% | <2% |
| P95 latency (simple) | Variable | <3s |
| P95 latency (complex) | Variable | <20s |

---

## 2. Current Architecture Analysis

### 2.1 Pipeline Flow (As-Is)

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ ToolCallingEngine (core.py)                                       │
│  ├─ Stage 0: IntentAnalyzer (engine/intent_analyzer.py)        │
│  ├─ Stage 0: UnifiedIntentAnalyzer (engine/unified_intent_...)  │
│  ├─ Stage 0: ContextRewriter (engine/context_rewriter.py)       │
│  └─ Stage 0: Guardrail input                                     │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ HybridToolRouter (hybrid_router/router.py)                │   │
│  │  ├─ Stage 1: DomainClassifier (domain_classifier.py)     │   │
│  │  ├─ Stage 1b: QueryDecomposer                            │   │
│  │  ├─ Stage 2: LlamaIndexToolRetriever (Qdrant)            │   │
│  │  └─ Stage 3: LLM execution model selection               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ ParallelExecutor → ToolIndexManager (Qdrant upsert)      │   │
│  └──────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ ResponseSynthesizer → Guardrail output                   │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Critical Pain Points

#### 2.2.1 Intent Analyzer Proliferation

**Location:** `engine/intent_analyzer.py` + `engine/unified_intent_analyzer.py` + `engine/context_rewriter.py`

**Problem:**
- `ToolCallingEngine.run()` calls both `IntentAnalyzer.analyze()` AND `HybridToolRouter` which has its own `IntentAnalyzer`
- `UnifiedIntentAnalyzer` exists but is conditionally enabled via feature flags
- Logic divergence: one decides "conversation", another decides "domains"

**Evidence:**
```python
# core.py line ~680
if use_unified_intent and self._analyzer is not None:
    analysis = await self._analyzer.analyze(sanitized_query, context)

# router.py line ~256
if self._enable_stage0_intent and self._intent_analyzer:
    intent_analysis = await self._intent_analyzer.analyze(...)
```

#### 2.2.2 Domain Contract Drift

**Location:** Mismatch between:
- `config/tool_hierarchy.yaml` (141 entries)
- `engine/hybrid_router/tool_hierarchy.py` (hierarchy loader)
- `domains/*/tools.py` (actual tool definitions)
- `engine/hybrid_router/domain_classifier.py` (keyword maps)

**Evidence:**
| Domain | YAML Tools | Actual Tools | Delta |
|--------|------------|--------------|-------|
| google_workspace | 59 declared | ~17 actual | -42 missing, +27 ghost |
| finance_crypto | 25 declared | ~17 actual | -8 missing, +8 ghost |
| sports_nba | 5 declared | ~8 actual | +3 over |
| shopping | 0 declared | 0 actual | Placeholder |
| productivity | 0 declared | 0 actual | Placeholder |

#### 2.2.3 Weak Fallback Policy

**Location:** `router.py` lines 346-349

```python
if classification.needs_fallback and not classification.domains:
    # No domains at all - use global top-K
    retrieval = await self._retriever.retrieve_global_topk(query_for_routing, k=25)
```

**Problem:** `needs_fallback` only True when `confidence < 0.3 AND domains == []`.  
If domain is wrong but confidence is high (0.7), wrong filter is applied silently.

#### 2.2.4 Destructive Index Rebuild

**Location:** `tool_index.py` lines 206-218

```python
# Clear existing data - delete collection and recreate
try:
    self._client.delete_collection(CAPABILITIES_COLLECTION)
    await self._ensure_collection()
    ...
```

**Problem:** On every startup with `force_rebuild=True` or hash mismatch, entire collection is deleted.  
**Risk:** If process crashes during rebuild, zero tools available until next successful rebuild.

#### 2.2.5 Hash Detection Fragility

**Location:** `tool_index.py` lines 143-150

```python
# Get first point to check stored hash
points = self._client.scroll(
    collection_name=CAPABILITIES_COLLECTION,
    limit=1,
    with_payload=["_catalog_hash"],
)[0]
```

**Problem:** Hash stored in first point's payload. If points reindexed, first point changes, hash lost.  
**Also:** `add_tool()` method (line 423) does NOT preserve `_catalog_hash` in new points.

---

## 3. Wave 0: Critical Stabilization (Week 1)

**Objective:** Eliminate blockers that cause immediate failures or data loss.

### 3.1 Stop Destructive Rebuild [CRITICAL]

**File:** `backend/src/me4brain/engine/hybrid_router/tool_index.py`

**Change:**
```python
# REMOVE: delete_collection call in build_from_catalog
# REPLACE with upsert logic

async def build_from_catalog(
    self,
    tool_schemas: list[dict[str, Any]],
    tool_domains: dict[str, str],
    force_rebuild: bool = False,
) -> int:
    # ... hash computation ...
    
    # NEW: Incremental upsert instead of rebuild
    # 1. Get existing tool names from collection
    # 2. Compare with incoming schemas
    # 3. Only upsert changed/deleted tools
    # 4. Store manifest in dedicated meta-record (not first point)
```

**Meta-record pattern:**
```python
META_POINT_ID = "__catalog_manifest__"

async def _save_manifest(self, manifest: dict) -> None:
    """Store catalog manifest in dedicated point with fixed ID."""
    # Upsert to fixed ID point
    self._client.upsert(
        collection_name=CAPABILITIES_COLLECTION,
        points=[PointStruct(
            id=META_POINT_ID,
            vector=[0.0] * EMBEDDING_DIM,  # Dummy vector
            payload={"_type": "manifest", "_data": json.dumps(manifest)}
        )]
    )
```

**Verification:**
```bash
cd backend && uv run pytest tests/unit/test_tool_index.py -v
```

### 3.2 Enable Rescue on Zero Results [HIGH]

**File:** `backend/src/me4brain/engine/hybrid_router/llama_tool_retriever.py`

**Change:**
```python
async def retrieve(self, query: str, classification: DomainClassification) -> ToolRetrievalResult:
    # ... existing retrieval logic ...
    
    # NEW: Mandatory rescue policy
    if len(final_tools) == 0:
        logger.warning("zero_tools_retrieved_triggering_rescue", query=query[:50])
        
        # Stage 1: Expand domain - try adjacent/similar domains
        expanded = await self._expand_domain_search(query, classification)
        if expanded:
            return expanded
        
        # Stage 2: Global safety pass
        return await self.retrieve_global_topk(query, k=25)
    
    return ToolRetrievalResult(...)
```

**Verification:**
```bash
cd backend && uv run pytest tests/unit/test_router.py -k "rescue" -v
```

### 3.3 Fix Env Loading [HIGH]

**Files:** All domain modules with `load_dotenv()` without absolute path

**Pattern to fix:**
```python
# WRONG
from dotenv import load_dotenv
load_dotenv()  # Relative to cwd, fragile

# CORRECT
from dotenv import load_dotenv
import os
load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
```

**Files requiring fix:**
- `domains/sports_nba/nba_api.py`
- `domains/finance_crypto/finance_api.py`
- `domains/finance_crypto/crypto_api.py`
- `integrations/premium_apis.py`

**Verification:**
```bash
cd backend && uv run ruff check src/me4brain/domains/ --select=E
```

### 3.4 Disable Placeholder Domains [MEDIUM]

**Files:** `engine/hybrid_router/router.py` + `engine/hybrid_router/domain_classifier.py`

**Change:** Add explicit blocklist:
```python
PLACEHOLDER_DOMAINS = {"shopping", "productivity"}

async def route(self, query, context, max_tools, conversation_history):
    # Before domain classification, check for placeholder-only queries
    if self._is_placeholder_only_query(query):
        logger.info("placeholder_domain_blocked", query=query[:50])
        return []  # No tools - domains not implemented
```

**Verification:**
```bash
cd backend && uv run pytest tests/integration/test_router.py -k "placeholder" -v
```

---

## 4. Wave 1: Contracts & Coherence (Weeks 2-4)

**Objective:** Establish single source of truth for tool metadata.

### 4.1 Canonical Tool Contract Schema

**New File:** `backend/src/me4brain/engine/tool_contract.py`

```python
"""Canonical Tool Contract - Single Source of Truth for Tool Metadata."""

from __future__ import annotations

from enum import Enum
from typing import Protocol, runtime_checkable
from pydantic import BaseModel, Field

class RiskLevel(Enum):
    LOW = "low"           # Read-only, no side effects
    MEDIUM = "medium"     # Write operations, rate limits
    HIGH = "high"         # Destructive, monetary
    CRITICAL = "critical"  # Admin, security-sensitive

class LatencyClass(Enum):
    FAST = "fast"         # <500ms expected
    NORMAL = "normal"     # 500ms-2s expected
    SLOW = "slow"         # 2-10s expected
    VARIABLE = "variable" # External dependency

class ToolContract(BaseModel):
    """Canonical tool metadata contract.
    
    This is the SINGLE SOURCE OF TRUTH for all tool metadata.
    Generated from domain handlers and used to produce:
    - ToolDefinition for catalog
    - Hierarchy index entries
    - Domain classifier keywords
    - Qdrant metadata filters
    - Documentation
    """
    # Identity
    tool_id: str = Field(..., description="Unique tool identifier")
    domain: str = Field(..., description="Primary domain")
    category: str = Field(..., description="Sub-domain category")
    skill: str = Field(..., description="Skill/component name")
    
    # Schema (OpenAI-compatible)
    name: str = Field(..., description="LLM-facing tool name")
    description: str = Field(..., description="Human-readable description")
    parameters: dict[str, Any] = Field(..., description="JSON Schema parameters")
    
    # Classification
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM)
    latency_class: LatencyClass = Field(default=LatencyClass.NORMAL)
    auth_requirements: list[str] = Field(default_factory=list)
    
    # Versioning
    version: str = Field(default="1.0.0")
    schema_version: str = Field(default="2026.1")
    deprecation_status: str = Field(default="active")
    deprecated_aliases: list[str] = Field(default_factory=list)
    
    # Discovery
    aliases: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)  # For classifier
    not_suitable_for: list[str] = Field(default_factory=list)  # Disambiguation
    
    # Index hints (for retrieval tuning)
    embedding_hint: str = Field(..., description="Enhanced embedding text")
    priority_boost: float = Field(default=1.0)  # >1 = boost, <1 = deprioritize
    
    class Config:
        use_enum_values = True


class ToolContractRegistry:
    """Registry for all tool contracts.
    
    SINGLE INSTANCE that must be used for all tool metadata operations.
    """
    
    _instance: ToolContractRegistry | None = None
    
    def __init__(self) -> None:
        self._contracts: dict[str, ToolContract] = {}
        self._domains: dict[str, set[str]] = {}  # domain -> tool_ids
        self._initialized = False
    
    @classmethod
    def get_instance(cls) -> ToolContractRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def register(self, contract: ToolContract) -> None:
        """Register a tool contract."""
        self._contracts[contract.tool_id] = contract
        if contract.domain not in self._domains:
            self._domains[contract.domain] = set()
        self._domains[contract.domain].add(contract.tool_id)
    
    def register_batch(self, contracts: list[ToolContract]) -> int:
        """Register multiple contracts."""
        for c in contracts:
            self.register(c)
        return len(contracts)
    
    def get(self, tool_id: str) -> ToolContract | None:
        return self._contracts.get(tool_id)
    
    def get_by_domain(self, domain: str) -> list[ToolContract]:
        return [self._contracts[tid] for tid in self._domains.get(domain, set())]
    
    def get_all(self) -> list[ToolContract]:
        return list(self._contracts.values())
    
    def get_domain_keywords(self) -> dict[str, list[str]]:
        """Generate keyword map for domain classifier from contracts."""
        keywords: dict[str, set[str]] = {}
        for contract in self._contracts.values():
            if contract.domain not in keywords:
                keywords[contract.domain] = set()
            keywords[contract.domain].update(contract.keywords)
        return {d: list(kw) for d, kw in keywords.items()}
    
    def get_tool_domains(self) -> dict[str, str]:
        """Generate tool_name -> domain map."""
        return {c.name: c.domain for c in self._contracts.values()}
    
    def sync_to_yaml(self, path: str) -> None:
        """Sync contracts to tool_hierarchy.yaml format."""
        import yaml
        hierarchy = {}
        for contract in self._contracts.values():
            if contract.domain not in hierarchy:
                hierarchy[contract.domain] = {}
            if contract.category not in hierarchy[contract.domain]:
                hierarchy[contract.domain][contract.category] = {}
            # ... nested structure
        with open(path, "w") as f:
            yaml.dump(hierarchy, f)
```

### 4.2 Contract Generation from Domain Handlers

**New File:** `backend/src/me4brain/engine/contract_generator.py`

```python
"""Generate ToolContracts from domain handler interfaces."""

async def generate_from_domain(domain_name: str) -> list[ToolContract]:
    """Generate contracts for all tools in a domain.
    
    Reads from:
    1. Domain handler's get_tool_definitions()
    2. Domain handler's get_capabilities()
    3. Annotations on executor functions
    
    Produces canonical ToolContract entries.
    """
    # Implementation details...
```

### 4.3 Strict Schema Validation

**File:** `backend/src/me4brain/engine/hybrid_router/router.py`

**Change:**
```python
# In _execute_tool_selection
def _validate_tool_args(tool_name: str, args: dict, schema: dict) -> tuple[bool, str]:
    """Validate tool arguments against schema with strict mode."""
    params = schema.get("function", {}).get("parameters", {})
    
    # 1. Check for additionalProperties: false
    if params.get("additionalProperties") is False:
        allowed = set(params.get("properties", {}).keys())
        incoming = set(args.keys())
        extra = incoming - allowed
        if extra:
            return False, f"Unknown parameters: {extra}"
    
    # 2. Type validation
    for key, value in args.items():
        if key in params.get("properties", {}):
            expected_type = params["properties"][key].get("type")
            # Type checking logic...
    
    return True, ""

# Usage in _execute_tool_selection:
for tc in tool_calls[:max_tools]:
    args = tc.function.arguments
    is_valid, error_msg = _validate_tool_args(tc.function.name, args, tool.schema)
    if not is_valid:
        logger.warning("invalid_tool_args", tool=tc.function.name, error=error_msg)
        # Retry or skip
```

### 4.4 Auto-Sync Classifier Keywords

**File:** `backend/src/me4brain/engine/hybrid_router/domain_classifier.py`

**Change:**
```python
def __init__(self, ...):
    super().__init__(...)
    
    # Load keywords from canonical registry (NEW)
    registry = ToolContractRegistry.get_instance()
    self._contract_keywords = registry.get_domain_keywords()
    
    # Merge with legacy keywords for过渡
    self._keyword_map = self._merge_keywords()

def _fallback_classification(self, query: str) -> DomainClassification:
    query_lower = query.lower()
    detected_domains = []
    
    for domain, keywords in self._keyword_map.items():
        # Use pre-computed keywords from registry
        if any(kw in query_lower for kw in keywords):
            detected_domains.append(domain)
    
    # ...
```

**Verification:**
```bash
cd backend && uv run pytest tests/unit/test_domain_classifier.py -v
cd backend && uv run mypy src/me4brain/engine/ --strict
```

---

## 5. Wave 2: Retrieval Core Refactor (Weeks 5-8)

**Objective:** Implement robust retrieval with proper fallback policies.

### 5.1 Top-K Domain Scoring

**File:** `backend/src/me4brain/engine/hybrid_router/domain_classifier.py`

**Change:**
```python
class DomainClassification(BaseModel):
    # EXISTING: domains list with single confidence
    # NEW: top_k_domains with per-domain confidence scores
    
    top_k_domains: list[DomainScore] = Field(default_factory=list)
    primary_domain: str | None = None
    
    @property
    def domains(self) -> list[DomainComplexity]:
        """Legacy accessor - convert top_k to DomainComplexity."""
        return [
            DomainComplexity(name=d.domain, complexity=self._infer_complexity(d))
            for d in self.top_k_domains[:3]
        ]
    
    @property
    def confidence(self) -> float:
        """Average confidence across top domains."""
        if not self.top_k_domains:
            return 0.0
        return sum(d.confidence for d in self.top_k_domains) / len(self.top_k_domains)

class DomainScore(BaseModel):
    domain: str
    confidence: float  # 0.0-1.0 calibrated score
    reasoning: str | None = None  # Why this domain


async def classify(self, query: str, ...) -> DomainClassification:
    """Return top-K domains with confidence scores, not hard assignment."""
    
    # LLM returns structured classification:
    # {
    #   "top_domains": [
    #     {"domain": "finance_crypto", "confidence": 0.82, "reasoning": "..."},
    #     {"domain": "web_search", "confidence": 0.35, "reasoning": "..."},
    #   ]
    # }
    
    # Validation: if top_domain.confidence < 0.4, flag for rescue
    if top_domains[0].confidence < 0.4:
        classification.needs_rescue = True
```

### 5.2 Hybrid Retrieval Enhancement

**File:** `backend/src/me4brain/engine/hybrid_router/llama_tool_retriever.py`

**Change:**
```python
class LlamaIndexToolRetriever:
    """Enhanced retrieval with multiple fallback strategies."""
    
    async def retrieve(
        self,
        query: str,
        classification: DomainClassification,
    ) -> ToolRetrievalResult:
        # STAGE 1: Dense vector search with top-K domains
        candidates = await self._dense_retrieve(query, classification.top_k_domains)
        
        # STAGE 2: Lexical/bm25 boost (NEW)
        if len(candidates) < self._config.coarse_top_k:
            lexical_hits = await self._lexical_retrieve(query, classification)
            candidates = self._merge_dense_lexical(candidates, lexical_hits)
        
        # STAGE 3: Cross-domain rerank (NEW)
        reranked = await self._cross_domain_rerank(query, candidates, classification)
        
        # STAGE 4: Payload budget enforcement
        return self._fit_to_payload_limit(reranked)
    
    async def _lexical_retrieve(self, query: str, classification: DomainClassification):
        """BM25 lexical search for recall boost."""
        # Implementation using rank_bm25 or similar
        pass
    
    def _merge_dense_lexical(self, dense: list, lexical: list) -> list:
        """Merge dense and lexical results with score normalization."""
        # Reciprocal Rank Fusion or score interpolation
        pass
```

### 5.3 Mandatory Rescue Policy

**File:** `backend/src/me4brain/engine/hybrid_router/router.py`

**Change:**
```python
class RescuePolicy(Enum):
    DOMAIN_EXPAND = "domain_expand"      # Try adjacent domains
    QUERY_REWRITE = "query_rewrite"     # Rewrite query, retry
    GLOBAL_PASS = "global_pass"         # Remove all filters
    ESCALATE = "escalate"               # Return error with suggestions

async def route(self, query: str, ...) -> list[ToolTask]:
    # ... existing stages 0-2 ...
    
    # AFTER Stage 2: Check rescue conditions
    if self._should_rescue(retrieval, classification):
        logger.info("triggering_rescue_policy", 
                    reason=self._rescue_reason(retrieval, classification))
        
        for policy in [RescuePolicy.DOMAIN_EXPAND, 
                       RescuePolicy.GLOBAL_PASS]:
            result = await self._apply_rescue(policy, query, retrieval, classification)
            if result and len(result.tools) > 0:
                retrieval = result
                break
    
    # Continue with Stage 3
    tool_tasks = await self._execute_tool_selection(...)
    
    # AFTER Stage 3: If still no valid tasks, final rescue
    if len(tool_tasks) == 0:
        logger.warning("final_rescue_triggered")
        tool_tasks = await self._final_rescue(query, ...)
    
    return tool_tasks

def _should_rescue(self, retrieval: ToolRetrievalResult, 
                   classification: DomainClassification) -> bool:
    """Determine if rescue policy should trigger."""
    # Condition 1: Zero results
    if len(retrieval.tools) == 0:
        return True
    
    # Condition 2: Low confidence primary domain
    if (classification.top_k_domains and 
        classification.top_k_domains[0].confidence < 0.4):
        return True
    
    # Condition 3: Score gap between top results is small (ambiguous)
    if len(retrieval.tools) >= 2:
        score_gap = retrieval.tools[0].similarity_score - retrieval.tools[1].similarity_score
        if score_gap < 0.05:  # Very close scores
            return True
    
    return False
```

### 5.4 Dynamic Rerank Budget

**File:** `backend/src/me4brain/engine/hybrid_router/types.py`

**Change:**
```python
class HybridRouterConfig(BaseModel):
    # Existing fields...
    
    # NEW: Dynamic budget based on query complexity
    rerank_budget_base: int = 20
    rerank_budget_per_domain: int = 5
    rerank_timeout_seconds: float = 30.0  # Per-stage timeout
    
    @property
    def rerank_top_n(self) -> int:
        """Dynamic rerank budget based on domain count."""
        # Computed at runtime based on classification
        pass
    
    # NEW: Timeout budgets
    coarse_timeout_seconds: float = 10.0
    rerank_timeout_seconds: float = 30.0
    selection_timeout_seconds: float = 45.0
```

**Verification:**
```bash
cd backend && uv run pytest tests/unit/test_retrieval.py -v -k "rescue or fallback"
cd backend && uv run pytest tests/integration/test_router_flow.py -v
```

---

## 6. Wave 3: Domain Hardening (Weeks 9-11)

**Objective:** Decompose monolithic modules and implement or decommission placeholders.

### 6.1 Decompose google_workspace

**Before:**
```
domains/google_workspace/
├── __init__.py
├── handler.py          # 2000+ lines
├── gmail_api.py        # 1500+ lines
├── calendar_api.py     # 800+ lines
├── drive_api.py       # 1200+ lines
└── ...
```

**After:**
```
domains/google_workspace/
├── __init__.py
├── handler.py          # Thin facade, delegates to capability packs
├── capabilities/
│   ├── gmail.py       # 200-300 lines per capability
│   ├── calendar.py
│   ├── drive.py
│   ├── docs.py
│   ├── sheets.py
│   └── meet.py
├── tools.py           # Generated from contracts
└── executors.py       # Thin delegation
```

### 6.2 Decompose finance_crypto

**After:**
```
domains/finance_crypto/
├── __init__.py
├── handler.py
├── capabilities/
│   ├── crypto.py      # CoinGecko, Binance, Hyperliquid
│   ├── stocks.py      # Yahoo, Finnhub, Alpaca
│   ├── macro.py       # FRED, Edgar
│   └── technicals.py  # Technical indicators
└── ...
```

### 6.3 Implement or Decommission Shopping/Productivity

**Option A: Implement minimally viable**
```python
# shopping - minimal viable implementation
SHOPPING_TOOLS = {
    "shopping_search": {
        "domain": "shopping",
        "description": "Search for products across major e-commerce",
        "mock": True,  # Flag as mock until real implementation
        "note": "DEPRECATED - Use web_search for product queries"
    }
}

# Route all shopping queries to web_search
SHOPPING_KEYWORD_MAP = {
    "cerca_prodotto": "web_search",
    "amazon": "web_search", 
    "ebay": "web_search",
}
```

**Option B: Explicit decommission**
```python
# In domain classifier
if detected_domain == "shopping":
    logger.warning("domain_decommissioned", domain="shopping")
    return DomainClassification(
        domains=[],
        confidence=0.0,
        query_summary="Shopping domain decommissioned - use web_search"
    )
```

### 6.4 Travel Deprecation Cleanup

**File:** `domains/travel/handler.py`

**Change:**
```python
async def execute(self, query: str, analysis: IntentAnalysis, context: dict) -> ToolResult:
    # Check for AviationStack usage
    if self._uses_deprecated_endpoint(tool_name):
        logger.warning(
            "deprecated_travel_endpoint",
            tool=tool_name,
            replacement="amadeus_*",
            sunset_date="2026-06-01"
        )
        return ToolResult(
            success=False,
            error="AviationStack API deprecated. Use Amadeus flight APIs instead."
        )
```

**Verification:**
```bash
cd backend && uv run pytest tests/unit/test_domain_decomposition.py -v
```

---

## 7. Wave 4: QA/Perf/SLO (Weeks 12-13)

**Objective:** Achieve 80%+ test coverage and measurable SLOs.

### 7.1 Test Coverage Requirements

| Component | Current | Target |
|-----------|---------|--------|
| ToolIndexManager | ~30% | 85% |
| DomainClassifier | ~60% | 90% |
| LlamaIndexToolRetriever | ~50% | 85% |
| HybridToolRouter | ~40% | 80% |
| ResponseSynthesizer | ~20% | 70% |
| Shopping domain | 0% | 70% |
| Productivity domain | 0% | 70% |

### 7.2 SLO Dashboard

**Metrics to track:**
```python
# In metrics.py
RETRIEVAL_LATENCY = Histogram("retrieval_latency_seconds", ...)
TOOL_SELECTION_RECALL = Gauge("tool_selection_recall_at_10", ...)
WRONG_DOMAIN_FAILURES = Counter("wrong_domain_failures_total", ...)
ZERO_RESULT_RATE = Counter("zero_result_retrievals_total", ...)
RESCUE_TRIGGER_RATE = Counter("rescue_policy_triggers_total", ...)
```

**SLO Targets:**
| SLO | Target | Alert Threshold |
|-----|--------|-----------------|
| Tool recall@10 | >0.95 | <0.90 |
| Wrong domain rate | <1% | >3% |
| Zero result rate | <2% | >5% |
| P95 simple latency | <3s | >5s |
| P95 complex latency | <20s | >30s |

### 7.3 Golden Set Evaluation

**New File:** `backend/tests/benchmarks/golden_set.py`

```python
"""Golden set for retrieval evaluation."""

GOLDEN_SET = [
    # (query, expected_domains, expected_tools)
    ("meteo Roma", ["geo_weather"], ["openmeteo_current"]),
    ("prezzo Bitcoin", ["finance_crypto"], ["coingecko_price"]),
    ("Lakers vs Celtics", ["sports_nba"], ["nba_live_scores", "nba_player_stats"]),
    # ... 100+ test cases
]

async def evaluate_retrieval(engine: ToolCallingEngine) -> dict:
    """Evaluate engine against golden set."""
    results = []
    for query, expected_domains, expected_tools in GOLDEN_SET:
        tasks = await engine.route(query)
        predicted_tools = [t.tool_name for t in tasks]
        
        # Calculate metrics
        recall = len(set(predicted_tools) & set(expected_tools)) / len(expected_tools)
        wrong_domain = not all(any(d in str(t) for d in expected_domains) for t in tasks)
        
        results.append({
            "query": query,
            "recall": recall,
            "wrong_domain": wrong_domain,
            "predicted": predicted_tools,
            "expected": expected_tools
        })
    
    return {
        "mean_recall": sum(r["recall"] for r in results) / len(results),
        "wrong_domain_rate": sum(r["wrong_domain"] for r in results) / len(results),
        "details": results
    }
```

**Verification:**
```bash
cd backend && uv run pytest tests/benchmarks/test_golden_set.py -v
```

---

## 8. Canonical Tool Contract Schema

### 8.1 Complete Schema Definition

```python
# backend/src/me4brain/engine/tool_contract.py

from pydantic import BaseModel, Field, validator
from typing import Literal

class ToolContract(BaseModel):
    """Canonical tool metadata - SINGLE SOURCE OF TRUTH.
    
    All tool metadata MUST be defined through this contract.
    Auto-generated outputs:
    - ToolDefinition for catalog
    - YAML hierarchy entries  
    - Domain classifier keywords
    - Qdrant metadata
    - API documentation
    """
    
    # ===================
    # IDENTITY (Required)
    # ===================
    tool_id: str = Field(
        ..., 
        description="Unique identifier in snake_case (e.g., gmail_search)"
    )
    domain: str = Field(
        ..., 
        description="Primary domain (e.g., google_workspace)"
    )
    category: str = Field(
        ..., 
        description="Sub-category (e.g., gmail, calendar)"
    )
    skill: str = Field(
        ..., 
        description="Skill name (e.g., search, list)"
    )
    
    # ===================
    # SCHEMA (Required)
    # ===================
    name: str = Field(
        ..., 
        description="LLM-facing function name (e.g., gmail_search)"
    )
    description: str = Field(
        ..., 
        max_length=500,
        description="Clear description of what tool does"
    )
    parameters: dict = Field(
        ..., 
        description="JSON Schema for tool arguments"
    )
    
    # ===================
    # CLASSIFICATION (Optional - defaults provided)
    # ===================
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    latency_class: Literal["fast", "normal", "slow", "variable"] = "normal"
    cost_class: Literal["free", "low", "medium", "high"] = "medium"
    
    # ===================
    # VERSIONING (Required for non-trivial changes)
    # ===================
    version: str = "1.0.0"
    schema_version: str = "2026.1"
    deprecation_status: Literal["active", "deprecated", "removed"] = "active"
    deprecated_aliases: list[str] = []
    sunset_date: str | None = None  # ISO date when deprecated
    
    # ===================
    # DISCOVERY (Used by classifiers and retrieval)
    # ===================
    aliases: list[str] = []  # Alternative names
    keywords: list[str] = []  # For keyword-based fallback
    not_suitable_for: list[str] = []  # Disambiguation hints
    
    # ===================
    # RETRIEVAL TUNING
    # ===================
    embedding_hint: str = ""  # Custom embedding text
    priority_boost: float = 1.0  # >1 boosts, <1 deprioritizes
    min_similarity_score: float = 0.0  # Filter threshold
    
    # ===================
    # EXECUTION HINTS
    # ===================
    retry_policy: dict = {
        "max_attempts": 3,
        "backoff_factor": 1.5,
        "retry_on": ["timeout", "rate_limit", "server_error"]
    }
    timeout_seconds: float = 30.0
    
    # ===================
    # VALIDATORS
    # ===================
    @validator("tool_id")
    def validate_tool_id(cls, v):
        if not v.replace("_", "").isalnum():
            raise ValueError(f"Invalid tool_id: {v}")
        return v
    
    @validator("parameters")
    def validate_parameters(cls, v):
        if "type" not in v and "properties" not in v:
            raise ValueError("Parameters must have 'type' or 'properties'")
        return v
```

### 8.2 Contract → ToolDefinition Generation

```python
# In tool_contract.py

    def to_tool_definition(self) -> ToolDefinition:
        """Generate ToolDefinition from contract."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
            domain=self.domain,
            category=self.category,
            # ... other fields from ToolDefinition schema
        )
    
    def to_qdrant_metadata(self) -> dict:
        """Generate Qdrant payload metadata."""
        return {
            "tool_name": self.tool_id,
            "domain": self.domain,
            "category": self.category,
            "skill": self.skill,
            "description": self.description,
            "risk_level": self.risk_level,
            "type": "tool",
            "subtype": "static",
            "priority_boost": self.priority_boost,
            "schema_json": json.dumps({"function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters
            }}),
            "_contract_version": self.version
        }
```

---

## 9. Retrieval V2 Architecture

### 9.1 Complete Flow Diagram

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 0: INPUT GUARDRAIL                                        │
│  ├─ Threat detection                                             │
│  ├─ Input sanitization                                          │
│  └─ Rate limiting check                                          │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 1: UNIFIED INTENT (Single Layer)                           │
│  ├─ Canonical IntentAnalyzer (NO dual layer)                    │
│  ├─ Context rewriting (if conversation history exists)         │
│  └─ Output: IntentType + SuggestedDomains + Confidence         │
└─────────────────────────────────────────────────────────────────┘
    │
    ├─→ If CONVERSATIONAL (confidence > 0.8) → Early exit
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 2: DOMAIN SCORING (Top-K, not hard assignment)           │
│  ├─ LLM classification → top_k_domains with confidence          │
│  ├─ Keyword fallback (from ToolContract registry)              │
│  └─ Output: List[DomainScore{domain, confidence, reasoning}]   │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 3: RETRIEVAL (Hybrid + Rescue Policy)                     │
│  ├─ Sub-query decomposition (if multi-domain)                    │
│  ├─ Dense retrieval (Qdrant vector search)                     │
│  ├─ Lexical retrieval (BM25 fallback)                           │
│  ├─ Cross-domain reranking                                      │
│  ├─ RESCUE CHECK (if zero/low results)                         │
│  │   ├─ Policy 1: Domain expansion                              │
│  │   ├─ Policy 2: Query rewrite                                 │
│  │   └─ Policy 3: Global safety pass                           │
│  └─ Output: List[RetrievedTool] ranked by score                │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 4: TOOL SELECTION (LLM with validation)                  │
│  ├─ Model selection based on complexity                         │
│  ├─ Strict schema validation (additionalProperties:false)      │
│  ├─ Argument type checking                                      │
│  └─ Output: List[ToolTask] with validated arguments             │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 5: EXECUTION (Parallel + Circuit Breaker)                 │
│  ├─ ParallelExecutor with retry budgets                         │
│  ├─ Per-tool timeout enforcement                                │
│  ├─ Circuit breaker for flaky providers                         │
│  └─ Output: List[ToolResult]                                    │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 6: SYNTHESIS (With Provenance)                            │
│  ├─ Multi-source evidence assembly                              │
│  ├─ Citation with tool provenance                               │
│  ├─ Anti-hallucination: only verified fields                   │
│  └─ Output: EngineResponse with structured + narrative          │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│ Stage 7: OUTPUT GUARDRAIL                                       │
│  ├─ Threat detection                                             │
│  ├─ PII redaction                                               │
│  └─ Rate limiting check                                          │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Domain Scoring Algorithm

```python
async def _score_domains(
    self,
    query: str,
    intent_hints: IntentHints | None,
    context: list[dict] | None
) -> list[DomainScore]:
    """Score domains using calibrated confidence.
    
    Returns top-K domains with confidence scores, not hard assignment.
    Confidence calibration ensures 0.7+ means strong match.
    """
    
    # Build prompt with intent hints
    prompt = self._build_scoring_prompt(query, intent_hints, context)
    
    # LLM returns structured scores
    response = await self._llm.generate_response(prompt)
    data = parse_json(response)
    
    domain_scores = []
    for item in data.get("domain_scores", []):
        score = DomainScore(
            domain=item["domain"],
            confidence=item["confidence"],  # Already calibrated 0-1
            reasoning=item.get("reasoning", "")
        )
        domain_scores.append(score)
    
    # Sort by confidence descending
    domain_scores.sort(key=lambda x: x.confidence, reverse=True)
    
    # Calibration check: if top score < 0.3, likely misrouted query
    if domain_scores and domain_scores[0].confidence < 0.3:
        logger.warning(
            "low_domain_confidence",
            top_domain=domain_scores[0].domain,
            confidence=domain_scores[0].confidence,
            query=query[:50]
        )
    
    return domain_scores[: self._config.max_scored_domains]
```

### 9.3 Rescue Policy Implementation

```python
class RescuePolicyEngine:
    """Implements rescue policies for retrieval failures."""
    
    def __init__(self, retriever: LlamaIndexToolRetriever, config: HybridRouterConfig):
        self._retriever = retriever
        self._config = config
    
    async def apply_rescue(
        self,
        query: str,
        classification: DomainClassification,
        current_results: ToolRetrievalResult,
        trigger_reason: str
    ) -> ToolRetrievalResult:
        """Apply rescue policies until successful or exhausted."""
        
        policies = [
            RescuePolicy.DOMAIN_EXPAND,
            RescuePolicy.LEXICAL_BOOST,
            RescuePolicy.GLOBAL_PASS,
        ]
        
        for policy in policies:
            logger.info(
                "rescue_attempt",
                policy=policy.value,
                trigger_reason=trigger_reason
            )
            
            result = await self._apply_policy(policy, query, classification)
            
            if result and self._is_successful_rescue(result, current_results):
                logger.info(
                    "rescue_succeeded",
                    policy=policy.value,
                    tools_found=len(result.tools)
                )
                result.rescue_applied = True
                result.rescue_policy = policy.value
                return result
        
        # All policies exhausted - return best effort
        logger.warning("rescue_exhausted")
        return current_results
    
    async def _apply_policy(
        self,
        policy: RescuePolicy,
        query: str,
        classification: DomainClassification
    ) -> ToolRetrievalResult | None:
        
        if policy == RescuePolicy.DOMAIN_EXPAND:
            # Add adjacent/similar domains
            expanded_domains = self._get_adjacent_domains(classification)
            # ... retrieval with expanded domains
            
        elif policy == RescuePolicy.LEXICAL_BOOST:
            # Fallback to keyword-based search
            # ... BM25 retrieval
            
        elif policy == RescuePolicy.GLOBAL_PASS:
            # Remove all filters, global top-K
            return await self._retriever.retrieve_global_topk(query, k=25)
        
        return None
```

---

## 10. SLO/KPI Targets

### 10.1 Quality SLOs

| SLO | Definition | Target | Alert | Current Baseline |
|-----|------------|--------|-------|------------------|
| **Tool Selection Recall@10** | % of queries where correct tool in top-10 | >0.95 | <0.90 | ~0.85 |
| **Wrong Domain Hard Failure** | % queries routed to wrong domain | <1% | >3% | ~5% |
| **Zero-Result Rate** | % queries returning 0 tools | <2% | >5% | ~8% |
| **Schema Validation Pass** | % tool calls with valid args | >99.5% | <99% | Unknown |

### 10.2 Latency SLOs (Local Hardware)

| Query Type | Complexity | P50 | P95 | P99 | Alert |
|------------|------------|-----|-----|-----|-------|
| Simple | 1-3 tools | <1s | <3s | <5s | >5s |
| Medium | 4-8 tools | <3s | <8s | <15s | >15s |
| Complex | 8+ tools / multi-intent | <8s | <20s | <30s | >30s |

### 10.3 Operational SLOs

| SLO | Definition | Target | Alert |
|-----|------------|--------|-------|
| **Index Consistency** | Drift between manifest and actual tools | 0 | >0 |
| **Rescue Success Rate** | % rescues that recover results | >80% | <60% |
| **Start Time** | Time to first query ready | <30s | >60s |

### 10.4 KPI Dashboard Queries

```promql
# Retrieval quality
tool_selection_recall_10 = rate(tool_selection_correct[5m]) / rate(tool_selection_total[5m])
wrong_domain_failures = rate(wrong_domain_routed_total[5m])
zero_result_rate = rate(zero_result_retrievals_total[5m]) / rate(retrieval_requests_total[5m])

# Latency
 retrieval_latency_p95 = histogram_quantile(0.95, retrieval_latency_bucket)
rescue_trigger_rate = rate(rescue_policy_triggers_total[5m])

# Index health
index_drift = catalog_tool_count - qdrant_tool_count
```

---

## 11. Risk Register

| Risk | Probability | Impact | Mitigation | Owner |
|------|-------------|--------|------------|-------|
| Breaking existing tool routing | High | Critical | Incremental rollout with feature flags | Backend |
| Qdrant data loss during migration | Low | Critical | Backup before any destructive op | DevOps |
| Performance regression on local HW | Medium | High | Load tests in CI, golden set regression | QA |
| Schema validation rejects valid calls | Medium | Medium | Whitelist approach, monitoring | Backend |
| Rescue policy infinite loop | Low | High | Max 3 rescue attempts, circuit breaker | Backend |
| Domain deprecation breaks user flows | Medium | Medium | Explicit warning messages, fallback | Backend |

---

## 12. Testing Strategy

### 12.1 Test Pyramid

```
           ┌─────────────┐
           │    E2E      │  ← 20 tests (golden set)
           │   (Playwright) │
           └─────────────┘
          ┌───────────────────┐
          │  Integration      │  ← 50 tests
          │  (API flows)     │    - Router flows
          └───────────────────┘    - Tool execution
        ┌─────────────────────────┐
        │      Unit Tests        │  ← 200+ tests
        │   (Component level)   │    - ToolIndexManager
        │                        │    - DomainClassifier
        └─────────────────────────┘    - LlamaIndexToolRetriever
                                        - ToolContract validation
```

### 12.2 Critical Test Scenarios

#### Wave 0 Critical Tests
```python
class TestToolIndexNoDestruction:
    """Verify no destructive rebuild operations."""
    
    async def test_incremental_upsert_preserves_existing(self):
        """Existing tools should not be deleted during incremental update."""
        # Setup: index with 100 tools
        # Action: add_tool() with 1 new tool
        # Assert: 101 tools total, 100 original intact
    
    async def test_manifest_persists_across_rebuilds(self):
        """Catalog hash should persist in dedicated meta-point."""
        # ...

class TestRescuePolicy:
    async def test_zero_results_triggers_rescue(self):
        """Zero retrieved tools should trigger rescue policy."""
    
    async def test_rescue_expands_domains(self):
        """Rescue should try adjacent domains."""

class TestPlaceholderDomains:
    async def test_shopping_routes_to_websearch(self):
        """Shopping queries should be blocked or redirected."""
```

#### Wave 1 Critical Tests
```python
class TestCanonicalContract:
    async def test_contract_generates_tool_definition(self):
        """ToolContract should produce valid ToolDefinition."""
    
    async def test_contract_validates_schema(self):
        """Invalid schemas should raise validation errors."""
    
    async def test_registry_syncs_to_yaml(self):
        """Changes to contracts should sync to hierarchy YAML."""

class TestStrictValidation:
    async def test_additional_properties_false_rejected(self):
        """Tools with additionalProperties:false should reject extra args."""
    
    async def test_type_mismatch_rejected(self):
        """Wrong parameter types should be caught."""
```

### 12.3 Regression Test Suite

```bash
# Golden set regression
cd backend && uv run pytest tests/benchmarks/test_golden_set.py -v --fail-under=0.95

# Latency regression  
cd backend && uv run pytest tests/benchmarks/test_latency.py -v --max-latency-p95=3.0

# Full suite with coverage
cd backend && uv run pytest tests/ -v --cov=src/me4brain/engine \
    --cov-fail-under=80 --tb=short
```

---

## Appendix A: File Changes Summary

| Wave | File | Change Type | Lines |
|------|------|-------------|-------|
| 0 | `tool_index.py` | Refactor | ~150 |
| 0 | `llama_tool_retriever.py` | Enhancement | ~100 |
| 0 | `domain_classifier.py` | Enhancement | ~50 |
| 1 | `tool_contract.py` | New | ~300 |
| 1 | `contract_generator.py` | New | ~200 |
| 1 | `router.py` | Refactor | ~100 |
| 2 | `domain_classifier.py` | Refactor | ~200 |
| 2 | `llama_tool_retriever.py` | Refactor | ~150 |
| 2 | `types.py` | Enhancement | ~50 |
| 3 | `domains/google_workspace/*` | Decompose | ~2000 |
| 3 | `domains/finance_crypto/*` | Decompose | ~1500 |
| 4 | `tests/benchmarks/*` | New | ~500 |

## Appendix B: Dependencies

| Dependency | Purpose | Version |
|------------|---------|---------|
| pydantic | Contract validation | 2.x |
| llama-index | Vector retrieval | 0.10+ |
| qdrant-client | Vector store | 1.x |
| structlog | Structured logging | 24.x |
| pytest-asyncio | Async testing | 0.23+ |
| pytest-cov | Coverage reporting | 4.x |

## Appendix C: Rollback Plan

| Wave | Rollback Procedure | Time |
|------|-------------------|------|
| 0 | Revert tool_index.py from git, clear Qdrant collection, rebuild | 15 min |
| 1 | Feature flag off tool_contract, use legacy paths | 5 min |
| 2 | Set `use_rescue=false` in config | 1 min |
| 3 | Revert to monolithic modules from git | 30 min |
| 4 | Revert test changes | 5 min |

---

**Document Status:** Draft for Review  
**Next Review:** After Wave 0 completion  
**Approval Required:** Yes (Critical milestone)
