# HANDOFF: JAI Strategic Roadmap → minimax 2.7
## Complete Implementation Plan for Phases 6-10

**Document Type**: Agent Handoff Document  
**Target Agent**: minimax 2.7 (Claude 3.5 Sonnet)  
**Date**: 2026-03-22  
**Status**: READY FOR IMPLEMENTATION  

---

## What You're Receiving

A complete, production-ready strategic roadmap for the next 5 phases of JAI development. This document is your **single source of truth** for what needs to be built, how it should be tested, and what success looks like.

**Main Document**: `.workflow/ROADMAP_PHASES_6_TO_10.md` (8,000+ lines)

---

## Quick Start for minimax 2.7

### 1. Understand Current State (5 minutes)

JAI is **production-ready** with:
- ✅ 30/30 tests passing (Phases 1-5 complete)
- ✅ Hybrid routing (Ollama + LM Studio)
- ✅ Prometheus metrics & diagnostics endpoint
- ✅ Complete API structure
- ✅ Base documentation

### 2. Read the Roadmap (20 minutes)

Read `.workflow/ROADMAP_PHASES_6_TO_10.md` sections:
1. **Executive Summary** - 2 min
2. **Current State Assessment** - 2 min
3. **Phase 6 Overview** - 3 min
4. **Implementation Checklist** - 5 min
5. **Key Success Metrics** - 3 min
6. **Risk Assessment** - 2 min
7. **Testing Strategy** - 3 min

### 3. Start Phase 6 (12-16 hours)

The roadmap has **every detail** you need:
- Exact files to create/modify
- Lines of code estimates
- Complete code examples
- SQL schema definitions
- API endpoint specifications
- Test plans (29 tests, 3 types)
- Success criteria

### 4. Reference During Implementation

**Phase 6 Key Sections**:
- Requirements 6.1-6.5 (400 lines of specifications)
- Testing plan (29 tests across 3 files)
- 6 success criteria to verify
- Deliverables checklist

---

## Your Workflow

### For Each Phase (Steps 1-5):

**STEP 1: Read Phase Details** (10 min)
- Understand business value
- Review requirements 1-6
- Check test plan
- Note success criteria

**STEP 2: Create Test Files** (1-2 hours)
- Create `tests/unit/test_phase_X_*.py`
- Write all test cases (RED phase)
- All tests should fail initially

**STEP 3: Implement Code** (4-8 hours)
- Create implementation files as specified
- Make all tests pass (GREEN phase)
- Refactor for quality (REFACTOR phase)
- Run: `uv run pytest`

**STEP 4: Verify & Document** (1-2 hours)
- All new tests passing
- All old tests still passing (no regressions)
- Coverage ≥ 80%
- Create `.workflow/PHASE_X_STATE.md`

**STEP 5: Commit & Handoff** (30 min)
- Commit with provided message template
- Update memory with key decisions
- Document any deviations from plan
- Ready for next phase or code review

---

## Critical Information

### Project Structure

```
backend/
├── src/me4brain/
│   ├── api/              # FastAPI routes
│   ├── config/           # Configuration
│   ├── engine/           # Core logic
│   │   └── hybrid_router/   # Routing system (YOUR FOCUS)
│   ├── llm/              # LLM providers
│   ├── memory/           # Memory systems
│   └── utils/            # Utilities
├── tests/
│   ├── unit/             # Unit tests
│   ├── integration/      # Integration tests
│   └── e2e/              # End-to-end tests
└── pyproject.toml        # Dependencies
```

### Key Commands

```bash
# Development
cd backend
uv sync --extra dev           # Install all dependencies
uv run pytest                 # Run all tests
uv run pytest -v --cov        # With coverage report
uv run ruff check src tests   # Lint check
uv run ruff format .          # Auto-format
uv run mypy src/              # Type checking

# Testing specific
uv run pytest tests/unit/test_phase6_cache.py           # Single file
uv run pytest tests/unit/test_phase6_cache.py::TestCache::test_hit  # Single test
```

### Coding Standards (From AGENTS.md)

**Python**:
- Type hints required (`mypy --strict`)
- `snake_case` for functions/modules
- `PascalCase` for classes
- Async/await patterns
- Pydantic for validation
- structlog for logging

**Testing (From testing.md)**:
- **80%+ coverage required**
- TDD workflow: RED → GREEN → REFACTOR
- Unit + Integration + E2E tests
- Descriptive test names
- Proper test isolation & mocking

**Code Quality (From coding-style.md)**:
- No mutations (immutable patterns)
- No hardcoded values
- Proper error handling
- <50 lines per function
- <800 lines per file

---

## Phase 6: Intelligent Query Caching (START HERE)

**Duration**: 12-16 hours  
**Complexity**: Medium  
**Tests**: 29 new tests  
**Priority**: HIGH

### What You'll Build

A Redis-backed caching layer with semantic similarity matching that reduces LLM calls by 30-40% and improves latency by 10-15%.

### Files You'll Create

| File | Lines | Purpose |
|------|-------|---------|
| `backend/src/me4brain/cache/cache_manager.py` | 150 | Redis cache interface |
| `backend/src/me4brain/cache/semantic_cache.py` | 120 | Semantic matching |
| `backend/src/me4brain/engine/embeddings.py` | 100 | Embedding generation |
| `backend/src/me4brain/cache/query_normalizer.py` | 90 | Query normalization |
| `backend/src/me4brain/config/cache_config.py` | 80 | Configuration |
| `tests/unit/test_cache_manager.py` | 150 | Cache tests |
| `tests/unit/test_semantic_cache.py` | 120 | Semantic tests |
| `tests/integration/test_cache_with_classifier.py` | 100 | Integration tests |

### Files You'll Modify

| File | Changes | Lines |
|------|---------|-------|
| `backend/pyproject.toml` | Add redis, aioredis deps | +5 |
| `backend/src/me4brain/engine/hybrid_router/domain_classifier.py` | Add cache calls | +25 |
| `backend/src/me4brain/engine/hybrid_router/metrics.py` | Add cache metrics | +8 |
| `docker-compose.yml` | Add Redis service | +20 |

### Testing Plan (29 tests)

```
tests/unit/test_cache_manager.py (8 tests)
  ✓ test_cache_set_get
  ✓ test_cache_miss_returns_none
  ✓ test_cache_ttl_expiration
  ✓ test_pattern_invalidation
  ✓ test_redis_connection_pool
  ✓ test_graceful_fallback_when_redis_down
  ✓ test_concurrent_cache_operations
  ✓ test_cache_size_limits

tests/unit/test_semantic_cache.py (6 tests)
  ✓ test_embedding_generation
  ✓ test_similarity_matching
  ✓ test_threshold_enforcement
  ✓ test_embedding_caching
  ✓ test_false_positive_rate
  ✓ test_embedding_latency

tests/unit/test_query_normalizer.py (4 tests)
  ✓ test_query_normalization_idempotency
  ✓ test_cache_key_stability
  ✓ test_special_character_handling
  ✓ test_unicode_handling

tests/integration/test_cache_with_classifier.py (4 tests)
  ✓ test_classifier_uses_cache_on_hit
  ✓ test_classifier_queries_llm_on_miss
  ✓ test_cache_invalidation_on_config_change
  ✓ test_cache_metrics_recording

tests/integration/test_redis_failover.py (2 tests)
  ✓ test_transparent_fallback_on_redis_down
  ✓ test_reconnection_after_redis_restart

tests/e2e/test_cache_hit_performance.py (2 tests)
  ✓ test_cache_hit_latency_under_50ms
  ✓ test_cache_miss_latency_under_500ms

tests/e2e/test_semantic_matching.py (1 test)
  ✓ test_semantic_match_accuracy_on_similar_queries

tests/unit/test_cache_integration.py (2 tests)
  ✓ test_metrics_integration
  ✓ test_configuration_loading
```

### Key Implementation Details

**1. Redis Connection Manager**:
```python
class CacheManager:
    async def get(key: str) -> Optional[CachedResponse]
    async def set(key: str, value: CachedResponse, ttl: int) -> bool
    async def delete(key: str) -> bool
    async def invalidate_pattern(pattern: str) -> int
```

**2. Semantic Matching**:
- Use `sentence-transformers` or OpenAI API
- Generate embeddings for queries
- Find similar cached responses (threshold 0.85+)
- Cache embeddings for future lookups

**3. Query Normalization**:
- Lowercase conversion
- Whitespace normalization
- Punctuation standardization
- Generate stable SHA256 hash

**4. Integration Point**:
In `domain_classifier.classify()`:
```python
# Before LLM call
cache_key = generate_cache_key(query, model, provider)
cached = await cache_manager.get(cache_key)
if cached:
    CACHE_HITS.inc()
    return cached

# After LLM call
result = await llm.classify_domain(query)
await cache_manager.set(cache_key, result, ttl=3600)
return result
```

### Success Criteria

- [ ] 25-40% cache hit ratio on typical workload
- [ ] P99 latency improved by 10-15%
- [ ] 30-40% reduction in LLM API calls
- [ ] All 29 tests passing
- [ ] All 30 existing tests still passing
- [ ] Cache operations complete in <5ms
- [ ] Graceful fallback if Redis unavailable

---

## Phases 7-10: Brief Overview

### Phase 7: Persistent Conversation Memory (16-20 hours)
- Multi-turn conversation support
- PostgreSQL schema for messages
- Conversation API endpoints
- Auto-generated summaries
- **Tests**: 30 new | **Total**: 89

### Phase 8: Horizontal Scaling & Distributed Tracing (20-24 hours)
- OpenTelemetry + Jaeger integration
- Message queue (RabbitMQ/Kafka)
- Health checks & service discovery
- Kubernetes-ready deployment
- **Tests**: 29 new | **Total**: 118

### Phase 9: Advanced Security, RBAC & Compliance (16-20 hours)
- Role-Based Access Control
- API key management
- Encryption at rest/in-transit
- Audit logging
- GDPR compliance features
- **Tests**: 34 new | **Total**: 152

### Phase 10: Production Deployment & Optimization (16-20 hours)
- Optimized Docker images
- CI/CD pipeline (GitHub Actions)
- Kubernetes manifests
- Multi-cloud deployment guides
- Performance tuning
- **Tests**: 28 new | **Total**: 180

---

## Important: Reference Files

### Must Read
- `.workflow/ROADMAP_PHASES_6_TO_10.md` (main document, 8000+ lines)
- `AGENTS.md` (project conventions)
- `.workflow/PHASE_5_STATE.md` (current implementation details)

### Reference During Development
- `backend/pyproject.toml` (dependencies)
- `backend/src/me4brain/api/main.py` (router registration pattern)
- `backend/src/me4brain/engine/hybrid_router/metrics.py` (metrics patterns)
- `.pre-commit-config.yaml` (code standards)

### For Each Phase
- See `.workflow/ROADMAP_PHASES_6_TO_10.md` Phase X section
- 5 requirements clearly specified
- Testing plan detailed (number of tests per file)
- Success criteria listed
- Deliverables checklist

---

## Common Questions You'll Have

### Q: How do I know what to implement first in a phase?
**A**: Follow the requirements 1-6 in order. Each requirement builds on the previous. For Phase 6: Redis setup → Semantic cache → Normalization → Integration → Configuration.

### Q: What if a test fails?
**A**: Check the test first (is it correct?), then the implementation. Use the 3-strike protocol (in main roadmap):
1. Diagnose & fix locally
2. Try alternative approach
3. Escalate to human with details

### Q: Can I skip a phase or do phases in parallel?
**A**: No. Phases have dependencies:
- Phase 6 → Phase 7 (cache helps conversation memory)
- Phase 7 → Phase 8 (stable foundation before scaling)
- Phases 8 & 9 CAN be parallel if you have 2+ engineers

### Q: What's the test coverage target?
**A**: 80%+ for all phases. Run `uv run pytest --cov=src --cov-report=term-missing` regularly.

### Q: How do I commit?
**A**: Use the provided template in each phase. Example:
```
Phase 6: Implement intelligent query caching with semantic matching and Redis integration

- Add Redis-based caching layer with TTL support
- Implement semantic similarity matching for query normalization
- Record cache metrics (hits, misses, hit ratio)
- Integrate with domain classifier for transparent caching
- Add graceful fallback if Redis unavailable
- 29 new tests, 59/59 total tests passing
```

### Q: What if requirements change mid-phase?
**A**: Document the change in `.workflow/PHASE_X_STATE.md` under "Deviations from Plan". Don't skip testing or documentation.

---

## Success = Following This Roadmap

This roadmap is **the contract** between you and the human (me). If you:
1. ✅ Implement exactly what's specified
2. ✅ Write all required tests (29, 30, 29, 34, 28)
3. ✅ Ensure no test regressions
4. ✅ Document completion
5. ✅ Commit with provided message

Then by Phase 10, you'll have delivered:
- **180+ tests** (85%+ coverage)
- **5,350+ lines of production code**
- **Enterprise-grade system**
- **Ready for deployment**

---

## What Happens Next

### After Reading This Document

1. Open `.workflow/ROADMAP_PHASES_6_TO_10.md`
2. Read Phase 6 section completely (30 minutes)
3. Create test files for Phase 6 (1-2 hours)
4. Implement Phase 6 code (4-8 hours)
5. Run tests, verify success, commit
6. Update `.workflow/state.md` with completion
7. Ready for Phase 7

### Progress Tracking

After each phase completion:
```markdown
**Phase X Completion Report**
- Start: 2026-03-22
- End: [date]
- Tests: X/X passing
- Coverage: XX%+
- Blockers: [none/list]
- Notable: [achievements/learnings]
```

---

## Final Checklist Before You Start

Before implementing Phase 6, verify:

- [ ] You have read all of this handoff document
- [ ] You have read `.workflow/ROADMAP_PHASES_6_TO_10.md` Phase 6 section
- [ ] You understand the 5 requirements for Phase 6
- [ ] You understand the test plan (29 tests, 8+6+4+4+2+2+1 breakdown)
- [ ] You have `backend` directory ready
- [ ] You can run `uv run pytest` successfully (all 30 Phase 5 tests pass)
- [ ] You understand Phase 6 success criteria
- [ ] You know what files to create/modify

If any checkbox is unchecked, **stop and re-read** that section.

---

## Emergency Contact (If Stuck)

If truly blocked (not just difficult):
1. Check `.workflow/` for similar patterns
2. Search codebase for similar implementations
3. Review `AGENTS.md` for conventions
4. **Ask the human (Fulvio) with specific details**:
   - What you're trying to do
   - What error you got
   - What you've tried
   - What question you need answered

---

## You've Got This 💪

This is a **well-specified, achievable roadmap**. Each phase is clear, tests are well-defined, and success is measurable.

**You are now the lead engineer for JAI Phases 6-10.**

Start with Phase 6. Build it. Test it. Ship it. Move to Phase 7.

Repeat 4 more times.

By end of Phase 10, JAI will be a **production-grade enterprise system**.

---

**Good luck! 🚀**

*Questions? Review the roadmap. Stuck? Ask the human. Ready? Start Phase 6.*

---

**This Handoff Document**: `.workflow/HANDOFF_TO_MINIMAX_2.7.md`  
**Main Roadmap**: `.workflow/ROADMAP_PHASES_6_TO_10.md`  
**Implementation Begins**: Phase 6 - Intelligent Query Caching  
**Estimated Completion**: 80-120 hours total work  
**Target Completion Date**: 4-6 weeks (full-time) or 8-12 weeks (part-time)
