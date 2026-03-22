# JAI - Comprehensive Implementation Plan

**Document Version**: 1.0  
**Created**: 2025-03-22  
**Status**: PHASE 3 COMPLETE - Phase 4 (Testing & Validation) Ready  
**Primary Issue**: LLM fallback cascade - system always falls back to keyword-based classification instead of using local LLM models properly

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Root Cause Analysis](#root-cause-analysis)
3. [Phase 1: Critical Fixes (Immediate)](#phase-1-critical-fixes-immediate)
4. [Phase 2: Architecture Optimization](#phase-2-architecture-optimization)
5. [Phase 3: Code Cleanup & Deprecation Removal](#phase-3-code-cleanup--deprecation-removal)
6. [Phase 4: Testing & Validation](#phase-4-testing--validation)
7. [Phase 5: Documentation & Monitoring](#phase-5-documentation--monitoring)
8. [Appendix: Files Reference](#appendix-files-reference)

---

## Executive Summary

### The Problem

When users submit queries through the PersAn frontend (e.g., NBA betting analysis), the **4-stage hybrid routing pipeline** always triggers fallback mechanisms instead of properly utilizing the configured local LLM models. This manifests as:

1. Domain classification falls back to keyword-based matching
2. Query decomposition uses heuristic fallbacks
3. Tool retrieval may be imprecise due to incorrect domain tagging
4. Overall response quality degrades significantly

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        JAI - Hybrid Routing Pipeline                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Frontend (PersAn)                                                          │
│  └─ Next.js UI → Gateway (Fastify) → Me4BrAIn Client                       │
│                                                                             │
│  Backend (Me4BrAIn)                                                         │
│  ├─ Stage 0: Intent Analysis + Context Rewriting                           │
│  ├─ Stage 1: Domain Classification (LLM → Keyword Fallback) ← PROBLEM HERE │
│  ├─ Stage 1b: Query Decomposition (LLM → Heuristic Fallback)               │
│  ├─ Stage 2: Tool Retrieval (BGE-M3 + Qdrant)                              │
│  └─ Stage 3: LLM Execution with Selected Tools                             │
│                                                                             │
│  LLM Providers (Priority Order)                                            │
│  ├─ 1. Ollama (localhost:11434) - Local, fast                              │
│  ├─ 2. LM Studio (localhost:1234) - Local, MLX models                      │
│  └─ 3. NanoGPT Cloud - Fallback only                                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Root Cause Summary

After comprehensive analysis, **5 primary root causes** have been identified:

| # | Root Cause | Impact | Priority |
|---|------------|--------|----------|
| 1 | **Model Resolution Mismatch** | Dashboard LLM config not reaching hybrid router | CRITICAL |
| 2 | **Health Check Silent Failures** | Provider marked healthy but not responding | CRITICAL |
| 3 | **600-second Timeout Masking Issues** | Actual errors hidden by unreachable timeout | HIGH |
| 4 | **12+ Fallback Triggers** | Too many error scenarios trigger keyword fallback | HIGH |
| 5 | **Environment Variable Disconnect** | `.env` defaults don't match dashboard config | MEDIUM |

---

## Root Cause Analysis

### RC1: Model Resolution Mismatch (CRITICAL)

**Location**: `backend/src/me4brain/engine/hybrid_router/router.py`, `domain_classifier.py`, `llm/config.py`

**Problem**: The `HybridRouterConfig` has its own model settings (`router_model`, `decomposition_model`) that are initialized with defaults and may not sync with dashboard-configured models.

**Evidence**:
```python
# From llm/config.py - defaults
model_primary: str = Field(default="qwen3.5-4b-mlx")
model_routing: str = Field(default="qwen3.5-4b-mlx")

# From hybrid_router/types.py - HybridRouterConfig
router_model: str = "qwen3.5-4b-mlx"  # Hardcoded default

# Dashboard updates go to env vars:
os.environ["LLM_ROUTING_MODEL"] = update.model_routing
# But HybridRouterConfig may already be instantiated with old defaults
```

**Why Fallback**: The router may be using a model that isn't loaded in Ollama/LM Studio, causing immediate 404 errors → fallback.

---

### RC2: Health Check Silent Failures (CRITICAL)

**Location**: `backend/src/me4brain/llm/health.py`, `provider_factory.py`

**Problem**: Health check marks providers as "healthy" based on `/api/tags` endpoint returning 200, but doesn't verify the *required model* is actually loaded.

**Evidence**:
```python
# health.py - check_ollama()
response = await client.get(f"{base_url}/api/tags")
if response.status_code == 200:
    return HealthCheckResult(provider="ollama", healthy=True, ...)
# ❌ Does NOT check if router_model is in the models list!
```

**Why Fallback**: Ollama responds 200 for `/api/tags`, health check says "healthy", but when we call `/chat/completions` with `qwen3.5-4b-mlx`, the model isn't loaded → 404 → fallback.

---

### RC3: 600-Second Timeout Masking Issues (HIGH)

**Location**: `backend/src/me4brain/engine/hybrid_router/domain_classifier.py`

**Problem**: The timeout is set to 600 seconds (10 minutes!), but actual failures happen immediately due to connection errors, 404s, or JSON parse failures - none of which are timeout-related.

**Evidence**:
```python
# domain_classifier.py
async with asyncio.timeout(600):  # 10 minutes - too long for dev
    response = await self._llm.generate_response(request)
```

**Why Fallback**: The 600s timeout never triggers because errors occur within milliseconds. The timeout creates a false sense of protection while real errors slip through via other exception handlers.

---

### RC4: 12+ Fallback Trigger Scenarios (HIGH)

**Location**: `backend/src/me4brain/engine/hybrid_router/domain_classifier.py`

**Problem**: The `_fallback_classification()` method is called in numerous scenarios, making it nearly impossible to NOT trigger fallback.

**Evidence**:
```python
# All paths that trigger fallback:
except asyncio.TimeoutError:
    return self._fallback_classification(query)  # 1
except httpx.HTTPStatusError as e:
    return self._fallback_classification(query)  # 2  
except httpx.ConnectError:
    return self._fallback_classification(query)  # 3
except json.JSONDecodeError:
    return self._fallback_classification(query)  # 4
except ValidationError:
    return self._fallback_classification(query)  # 5
except KeyError:
    return self._fallback_classification(query)  # 6
if not content:
    return self._fallback_classification(query)  # 7
if not parsed:
    return self._fallback_classification(query)  # 8
# ... and more
```

**Why Fallback**: Any deviation from the exact expected flow triggers keyword fallback. There's no retry mechanism or graceful degradation - it's either perfect LLM response or immediate fallback.

---

### RC5: Environment Variable Disconnect (MEDIUM)

**Location**: `backend/.env`, `llm/config.py`, `api/routes/llm_config.py`

**Problem**: The `.env` file has different default models than what the code expects:

**Evidence**:
```bash
# .env
OLLAMA_MODEL=mistral  # Default in .env

# llm/config.py  
model_primary: str = Field(default="qwen3.5-4b-mlx")  # Code default
```

**Why Fallback**: Even if Ollama is running with `mistral` loaded, the code may try to use `qwen3.5-4b-mlx` (from hardcoded defaults), which doesn't exist → 404 → fallback.

---

## Phase 1: Critical Fixes (Immediate)

### 1.1 Fix Model Resolution Chain

**Objective**: Ensure dashboard LLM configuration flows correctly to the hybrid router.

**Files to Modify**:
- `backend/src/me4brain/engine/hybrid_router/types.py`
- `backend/src/me4brain/engine/hybrid_router/router.py`
- `backend/src/me4brain/llm/config.py`

**Implementation Steps**:

#### Step 1.1.1: Make HybridRouterConfig Read from LLMConfig

```python
# File: backend/src/me4brain/engine/hybrid_router/types.py

# BEFORE (hardcoded defaults):
@dataclass
class HybridRouterConfig:
    router_model: str = "qwen3.5-4b-mlx"
    decomposition_model: str = "qwen3.5-4b-mlx"
    # ...

# AFTER (reads from LLMConfig singleton):
@dataclass
class HybridRouterConfig:
    router_model: str = field(default_factory=lambda: _get_config_value("model_routing"))
    decomposition_model: str = field(default_factory=lambda: _get_config_value("model_routing"))
    # ...

def _get_config_value(key: str) -> str:
    """Lazy load from LLMConfig to get current dashboard settings."""
    from me4brain.llm.config import get_llm_config
    config = get_llm_config()
    return getattr(config, key, "qwen3.5-4b-mlx")
```

#### Step 1.1.2: Add Config Refresh on API Update

```python
# File: backend/src/me4brain/api/routes/llm_config.py

# After line 368 (after get_llm_config.cache_clear()):
# Also invalidate HybridRouter singleton to pick up new config
from me4brain.engine.hybrid_router.router import _reset_router_singleton
_reset_router_singleton()
```

#### Step 1.1.3: Add Router Singleton Reset Function

```python
# File: backend/src/me4brain/engine/hybrid_router/router.py

# Add at module level:
_router_instance: HybridToolRouter | None = None

def _reset_router_singleton() -> None:
    """Reset router singleton to pick up new config."""
    global _router_instance
    _router_instance = None
    logger.info("hybrid_router_singleton_reset", reason="config_changed")
```

---

### 1.2 Fix Health Check to Verify Model Availability

**Objective**: Health check should verify the *required model* is loaded, not just that the provider is responding.

**Files to Modify**:
- `backend/src/me4brain/llm/health.py`

**Implementation Steps**:

#### Step 1.2.1: Add Model Verification to Health Check

```python
# File: backend/src/me4brain/llm/health.py

# Modify check_ollama() - add required_model parameter:

async def check_ollama(
    self, 
    base_url: str = "http://localhost:11434",
    required_model: str | None = None,  # NEW
) -> HealthCheckResult:
    """Check if Ollama is available and has the required model loaded."""
    start = asyncio.get_event_loop().time()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{base_url}/api/tags", follow_redirects=True)
            latency_ms = (asyncio.get_event_loop().time() - start) * 1000

            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                model_names = [m.get("name") for m in models]
                
                # NEW: Verify required model is available
                if required_model and required_model not in model_names:
                    # Check with/without tag
                    base_model = required_model.split(":")[0] if ":" in required_model else required_model
                    has_model = any(base_model in m for m in model_names)
                    
                    if not has_model:
                        logger.warning(
                            "ollama_model_not_loaded",
                            required_model=required_model,
                            available_models=model_names[:5],
                        )
                        return HealthCheckResult(
                            provider="ollama",
                            healthy=False,
                            latency_ms=latency_ms,
                            error=f"Required model '{required_model}' not loaded",
                        )
                
                # ... rest of existing logic
```

#### Step 1.2.2: Update get_best_provider to Pass Required Model

```python
# File: backend/src/me4brain/llm/health.py

async def get_best_provider(self, required_model: str | None = None) -> str:
    """Determine best available provider that has the required model."""
    from me4brain.llm.config import get_llm_config
    config = get_llm_config()
    
    # Use routing model if no specific model required
    if required_model is None:
        required_model = config.model_routing
    
    # Health check with model verification
    results = await asyncio.gather(
        self.check_ollama(config.ollama_base_url, required_model=required_model),
        self.check_lmstudio(config.lmstudio_base_url, required_model=required_model),
        self.check_nanogpt(config.nanogpt_base_url),
    )
    # ... rest of priority logic
```

---

### 1.3 Reduce Timeout and Add Retry Mechanism

**Objective**: Replace the 600s timeout with a sensible value and add retry logic before fallback.

**Files to Modify**:
- `backend/src/me4brain/engine/hybrid_router/domain_classifier.py`

**Implementation Steps**:

#### Step 1.3.1: Reduce Timeout to 30 Seconds

```python
# File: backend/src/me4brain/engine/hybrid_router/domain_classifier.py

# BEFORE:
async with asyncio.timeout(600):

# AFTER:
DOMAIN_CLASSIFICATION_TIMEOUT = 30  # 30 seconds for local models

async with asyncio.timeout(DOMAIN_CLASSIFICATION_TIMEOUT):
```

#### Step 1.3.2: Add Retry Before Fallback (3 Attempts)

```python
# File: backend/src/me4brain/engine/hybrid_router/domain_classifier.py

async def classify(self, query: str, context: str | None = None) -> DomainClassification:
    """Classify query domain with retry mechanism."""
    MAX_RETRIES = 3
    last_error = None
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            result = await self._attempt_classification(query, context)
            if result:
                return result
        except Exception as e:
            last_error = e
            logger.warning(
                "domain_classification_retry",
                attempt=attempt,
                max_retries=MAX_RETRIES,
                error=str(e),
            )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(0.5 * attempt)  # Backoff
    
    # Only fallback after all retries exhausted
    logger.error(
        "domain_classification_all_retries_failed",
        attempts=MAX_RETRIES,
        last_error=str(last_error),
        fallback="keyword_based",
    )
    return self._fallback_classification(query)
```

---

### 1.4 Synchronize Environment Variables

**Objective**: Ensure `.env` defaults match code defaults and are properly loaded.

**Files to Modify**:
- `backend/.env`
- `backend/src/me4brain/llm/config.py`

**Implementation Steps**:

#### Step 1.4.1: Update .env with Complete LLM Config

```bash
# File: backend/.env (add these lines)

# ============================================================================
# LLM MODEL CONFIGURATION (used by HybridRouter and all LLM calls)
# ============================================================================
LLM_PRIMARY_MODEL=qwen3:14b
LLM_ROUTING_MODEL=qwen3:14b
LLM_SYNTHESIS_MODEL=qwen3:14b
LLM_FALLBACK_MODEL=qwen3:14b
LLM_DEFAULT_TEMPERATURE=0.3
LLM_DEFAULT_MAX_TOKENS=8192
LLM_CONTEXT_WINDOW_SIZE=32768

# Local-only mode (disable cloud fallback)
LLM_LOCAL_ONLY=true
USE_LOCAL_TOOL_CALLING=true
LLM_ALLOW_CLOUD_FALLBACK=false

# Ollama configuration
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen3:14b

# LM Studio configuration (for MLX models)
LMSTUDIO_BASE_URL=http://localhost:1234/v1
```

#### Step 1.4.2: Make LLMConfig Explicitly Read All Env Vars

```python
# File: backend/src/me4brain/llm/config.py

# Ensure all model fields read from environment:
model_primary: str = Field(
    default_factory=lambda: os.getenv("LLM_PRIMARY_MODEL", "qwen3:14b")
)
model_routing: str = Field(
    default_factory=lambda: os.getenv("LLM_ROUTING_MODEL", os.getenv("LLM_PRIMARY_MODEL", "qwen3:14b"))
)
model_synthesis: str = Field(
    default_factory=lambda: os.getenv("LLM_SYNTHESIS_MODEL", os.getenv("LLM_PRIMARY_MODEL", "qwen3:14b"))
)
```

---

### 1.5 Add Pre-Flight LLM Connectivity Check

**Objective**: Validate LLM connectivity at startup and provide clear error messages.

**Files to Modify**:
- `backend/src/me4brain/api/app.py` (or main startup file)

**Implementation Steps**:

#### Step 1.5.1: Add Startup Health Check

```python
# File: backend/src/me4brain/api/app.py (in lifespan or startup event)

async def verify_llm_connectivity():
    """Verify LLM provider is reachable and model is loaded."""
    from me4brain.llm.health import get_llm_health_checker
    from me4brain.llm.config import get_llm_config
    
    config = get_llm_config()
    checker = get_llm_health_checker()
    
    # Check all providers
    ollama_result = await checker.check_ollama(
        config.ollama_base_url, 
        required_model=config.model_routing
    )
    
    if not ollama_result.healthy:
        logger.error(
            "STARTUP_LLM_CHECK_FAILED",
            provider="ollama",
            error=ollama_result.error,
            required_model=config.model_routing,
            hint="Run: ollama pull " + config.model_routing,
        )
        # Don't fail startup, but log prominently
    else:
        logger.info(
            "STARTUP_LLM_CHECK_PASSED",
            provider="ollama",
            model=config.model_routing,
            latency_ms=ollama_result.latency_ms,
        )

# Call in lifespan:
@asynccontextmanager
async def lifespan(app: FastAPI):
    await verify_llm_connectivity()  # Add this
    # ... rest of startup
```

---

## Phase 2: Architecture Optimization

### 2.1 Implement Graceful Degradation Levels

**Objective**: Instead of binary "LLM works" or "full fallback", implement graduated degradation.

**Degradation Levels**:
1. **Level 0**: Full LLM classification (normal operation)
2. **Level 1**: Simplified LLM prompt (if complex prompt fails)
3. **Level 2**: Hybrid LLM + keywords (LLM for confidence, keywords for domains)
4. **Level 3**: Pure keyword fallback (last resort)

**Implementation**:

```python
# File: backend/src/me4brain/engine/hybrid_router/domain_classifier.py

class DegradationLevel(Enum):
    FULL_LLM = 0
    SIMPLIFIED_LLM = 1
    HYBRID = 2
    KEYWORD_ONLY = 3

async def classify_with_degradation(
    self, 
    query: str, 
    context: str | None = None,
    max_degradation: DegradationLevel = DegradationLevel.KEYWORD_ONLY,
) -> DomainClassification:
    """Classify with graduated degradation levels."""
    
    for level in DegradationLevel:
        if level.value > max_degradation.value:
            break
            
        try:
            result = await self._classify_at_level(query, context, level)
            if result and result.confidence > 0.5:
                logger.info(
                    "classification_succeeded",
                    level=level.name,
                    confidence=result.confidence,
                )
                return result
        except Exception as e:
            logger.warning(
                "classification_level_failed",
                level=level.name,
                error=str(e),
            )
            continue
    
    # Final fallback
    return self._fallback_classification(query)
```

---

### 2.2 Add Structured Logging for Debugging

**Objective**: Add comprehensive logging to trace the exact point of failure.

**Implementation**:

```python
# File: backend/src/me4brain/engine/hybrid_router/domain_classifier.py

# Add at start of classify():
logger.info(
    "domain_classification_start",
    query_preview=query[:50],
    query_length=len(query),
    config_model=self._config.router_model,
    llm_client_type=type(self._llm).__name__,
)

# Before LLM call:
logger.debug(
    "domain_classification_llm_request",
    model=request.model,
    messages_count=len(request.messages),
    temperature=request.temperature,
)

# After LLM response:
logger.debug(
    "domain_classification_llm_response",
    response_length=len(raw_content) if raw_content else 0,
    has_content=bool(raw_content),
    first_100_chars=raw_content[:100] if raw_content else None,
)

# On fallback:
logger.warning(
    "domain_classification_fallback_triggered",
    reason=reason,  # Pass reason as parameter
    query_preview=query[:50],
    classification=result.domain_names if result else None,
)
```

---

### 2.3 Optimize Provider Selection

**Objective**: Cache provider health status and avoid repeated checks.

**Implementation**:

```python
# File: backend/src/me4brain/llm/provider_factory.py

import time
from dataclasses import dataclass

@dataclass
class CachedProviderStatus:
    provider: str
    healthy: bool
    checked_at: float
    ttl: float = 30.0  # 30 second cache
    
    @property
    def is_valid(self) -> bool:
        return (time.time() - self.checked_at) < self.ttl

_provider_cache: CachedProviderStatus | None = None

async def get_cached_best_provider() -> str:
    """Get best provider with caching to avoid repeated health checks."""
    global _provider_cache
    
    if _provider_cache and _provider_cache.is_valid:
        return _provider_cache.provider
    
    health_checker = get_llm_health_checker()
    best = await health_checker.get_best_provider()
    
    _provider_cache = CachedProviderStatus(
        provider=best,
        healthy=True,
        checked_at=time.time(),
    )
    
    return best
```

---

## Phase 3: Code Cleanup & Deprecation Removal

**STATUS**: ✅ COMPLETE (2026-03-22)

### 3.1 Files to Delete - ✅ COMPLETE

**Analysis Result**: `backend/src/me4brain/core/skills/registry_deprecated.py` is still actively used
- Used by: `retriever.py`, `crystallizer.py`, `__init__.py`
- New registry API not drop-in replacement
- **Decision**: KEEP for now (full migration out of scope)
- `backend/src/me4brain/tools/registry_deprecated.py` does not exist

### 3.2 Functions to Remove - ✅ COMPLETE

| File | Function | Status |
|------|----------|--------|
| `engine/core.py` | `create_legacy()` | ✅ REMOVED (64 lines) |
| `engine/core.py` | `create_with_hybrid_routing()` | ✅ REMOVED (22 lines) |
| `cognitive_pipeline.py` | `USE_LEGACY_FALLBACK` flag | ✅ REMOVED |
| `cognitive_pipeline.py` | Legacy fallback code block | ✅ REMOVED (92 lines) |

**Tests**: 920/920 passing, no regressions

### 3.3 Qdrant Collections to Clean Up - ⏳ DEFERRED

**Deprecated collections** (to remove during deployment):
```
tool_catalog, tools_and_skills, me4brain_skills, tools
```

**Active collection** (keep):
```
me4brain_capabilities (unified collection)
```

**Implementation**: Execute `backend/scripts/migrate_to_unified_collection.py` when Qdrant is running during deployment

---

## Phase 4: Testing & Validation

### 4.1 Unit Tests for Model Resolution

```python
# File: backend/tests/unit/test_model_resolution.py

import pytest
from me4brain.llm.provider_factory import resolve_model_client
from me4brain.llm.ollama import OllamaClient
from me4brain.llm.nanogpt import NanoGPTClient

class TestModelResolution:
    """Test model ID resolution to correct providers."""
    
    def test_ollama_model_with_tag(self):
        """Models with : (Ollama tags) should use Ollama."""
        client, model = resolve_model_client("qwen3:14b")
        assert isinstance(client, OllamaClient)
        assert model == "qwen3:14b"
    
    def test_mlx_model_uses_lmstudio(self):
        """MLX models should use LM Studio (via NanoGPT client)."""
        client, model = resolve_model_client("qwen3.5-4b-mlx")
        assert isinstance(client, NanoGPTClient)
    
    def test_simple_model_local_only(self, monkeypatch):
        """Simple models in local-only mode should use Ollama."""
        monkeypatch.setenv("LLM_LOCAL_ONLY", "true")
        client, model = resolve_model_client("llama3")
        assert isinstance(client, OllamaClient)
```

### 4.2 Integration Tests for Domain Classification

```python
# File: backend/tests/integration/test_domain_classifier.py

import pytest
from me4brain.engine.hybrid_router.domain_classifier import DomainClassifier
from me4brain.llm.ollama import get_ollama_client

@pytest.mark.integration
@pytest.mark.asyncio
class TestDomainClassifierIntegration:
    """Integration tests requiring running Ollama."""
    
    @pytest.fixture
    async def classifier(self):
        client = get_ollama_client()
        return DomainClassifier(
            llm_client=client,
            domains=["sports_nba", "web_search", "knowledge_media"],
        )
    
    async def test_nba_query_classification(self, classifier):
        """NBA betting query should classify to sports_nba domain."""
        result = await classifier.classify(
            "Analizza le partite NBA stasera e trova i pronostici migliori"
        )
        assert "sports_nba" in result.domain_names
        assert result.confidence > 0.7
        # Should NOT be a fallback
        assert not result.reasoning.startswith("Fallback")
    
    async def test_retries_before_fallback(self, classifier, mocker):
        """Should retry 3 times before falling back."""
        # Mock LLM to fail twice, succeed third time
        call_count = 0
        original_generate = classifier._llm.generate_response
        
        async def flaky_generate(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Simulated failure")
            return await original_generate(*args, **kwargs)
        
        mocker.patch.object(classifier._llm, 'generate_response', flaky_generate)
        
        result = await classifier.classify("Test query")
        assert call_count == 3
        assert result.confidence > 0.5  # Should succeed on 3rd try
```

### 4.3 End-to-End Test: Full Query Flow

```python
# File: backend/tests/e2e/test_full_query_flow.py

import pytest
import httpx

@pytest.mark.e2e
@pytest.mark.asyncio
class TestFullQueryFlow:
    """E2E tests for complete query processing."""
    
    async def test_nba_query_uses_llm_classification(self):
        """Full NBA query should use LLM, not fallback."""
        async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
            # Enable debug mode to get classification info
            response = await client.post(
                "/v1/engine/query",
                json={
                    "query": "Quali sono le partite NBA stasera?",
                    "debug": True,
                },
            )
            
            assert response.status_code == 200
            data = response.json()
            
            # Check classification was LLM-based
            assert data.get("debug", {}).get("classification_method") != "keyword_fallback"
            assert "sports_nba" in data.get("debug", {}).get("domains", [])
```

---

## Phase 5: Documentation & Monitoring

### 5.1 Add Metrics for Fallback Tracking

```python
# File: backend/src/me4brain/engine/hybrid_router/metrics.py

from prometheus_client import Counter, Histogram

CLASSIFICATION_TOTAL = Counter(
    'domain_classification_total',
    'Total domain classifications',
    ['method', 'success']  # method: llm, fallback_keyword, fallback_heuristic
)

CLASSIFICATION_LATENCY = Histogram(
    'domain_classification_latency_seconds',
    'Domain classification latency',
    ['method']
)

LLM_ERRORS = Counter(
    'domain_classification_llm_errors_total',
    'LLM errors during classification',
    ['error_type']  # timeout, connection, parse, validation
)
```

### 5.2 Dashboard Diagnostic Endpoint

```python
# File: backend/src/me4brain/api/routes/diagnostics.py

@router.get("/v1/diagnostics/llm-chain")
async def diagnose_llm_chain() -> dict:
    """Diagnose the LLM provider chain configuration."""
    from me4brain.llm.config import get_llm_config
    from me4brain.llm.health import get_llm_health_checker
    from me4brain.llm.provider_factory import resolve_model_client
    
    config = get_llm_config()
    checker = get_llm_health_checker()
    
    # Test each provider
    ollama = await checker.check_ollama(config.ollama_base_url, config.model_routing)
    lmstudio = await checker.check_lmstudio(config.lmstudio_base_url)
    
    # Test model resolution
    try:
        client, model = resolve_model_client(config.model_routing)
        resolution_ok = True
        resolution_client = type(client).__name__
    except Exception as e:
        resolution_ok = False
        resolution_client = str(e)
    
    return {
        "config": {
            "model_routing": config.model_routing,
            "model_primary": config.model_primary,
            "llm_local_only": config.llm_local_only,
            "ollama_base_url": config.ollama_base_url,
        },
        "health": {
            "ollama": {"healthy": ollama.healthy, "error": ollama.error, "latency_ms": ollama.latency_ms},
            "lmstudio": {"healthy": lmstudio.healthy, "error": lmstudio.error},
        },
        "resolution": {
            "ok": resolution_ok,
            "client": resolution_client,
            "model": model if resolution_ok else None,
        },
        "recommendation": _generate_recommendation(ollama, lmstudio, config),
    }

def _generate_recommendation(ollama, lmstudio, config) -> str:
    if ollama.healthy:
        return "OK: Ollama is healthy and ready"
    if lmstudio.healthy:
        return "DEGRADED: Using LM Studio fallback. Start Ollama for best performance."
    return f"CRITICAL: No local LLM available. Run: ollama pull {config.model_routing}"
```

---

## Appendix: Files Reference

### Critical Files (Phase 1)

| File | Purpose | Changes Required |
|------|---------|------------------|
| `backend/src/me4brain/engine/hybrid_router/types.py` | Router config types | Make config read from LLMConfig |
| `backend/src/me4brain/engine/hybrid_router/router.py` | Main router | Add singleton reset |
| `backend/src/me4brain/engine/hybrid_router/domain_classifier.py` | Domain classification | Add retries, reduce timeout |
| `backend/src/me4brain/llm/health.py` | Provider health checks | Add model verification |
| `backend/src/me4brain/llm/config.py` | LLM configuration | Sync with env vars |
| `backend/src/me4brain/api/routes/llm_config.py` | Config API | Add router reset |
| `backend/.env` | Environment | Add complete LLM config |

### Supporting Files (Phase 2-5)

| File | Purpose |
|------|---------|
| `backend/src/me4brain/llm/provider_factory.py` | Provider selection caching |
| `backend/src/me4brain/api/routes/diagnostics.py` | New diagnostic endpoint |
| `backend/tests/unit/test_model_resolution.py` | New unit tests |
| `backend/tests/integration/test_domain_classifier.py` | New integration tests |

### Files to Delete

| File | Reason |
|------|--------|
| `backend/src/me4brain/tools/registry_deprecated.py` | Deprecated |

---

## Implementation Order

1. **Day 1**: Phase 1.4 (Env sync) + Phase 1.5 (Startup check) - Foundation
2. **Day 2**: Phase 1.1 (Model resolution) + Phase 1.2 (Health check) - Core fix
3. **Day 3**: Phase 1.3 (Timeout + retry) - Resilience
4. **Day 4**: Phase 4.1-4.2 (Unit + Integration tests) - Validation
5. **Day 5**: Phase 2 (Architecture optimization) - Enhancement
6. **Day 6**: Phase 3 (Cleanup) + Phase 5 (Monitoring) - Polish

---

## Success Criteria

After implementation:

1. ✅ NBA betting queries classify to `sports_nba` domain via LLM (not keyword fallback)
2. ✅ Logs show `domain_classification_llm_success` instead of `domain_classification_fallback`
3. ✅ Dashboard LLM config changes take effect immediately without restart
4. ✅ Startup logs show LLM connectivity verification
5. ✅ `/v1/diagnostics/llm-chain` returns healthy status
6. ✅ No 600-second timeouts in logs
7. ✅ Retry mechanism prevents immediate fallback on transient errors
