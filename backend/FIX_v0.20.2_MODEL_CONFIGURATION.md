# Critical Model Configuration Fix - v0.20.2

**Status**: ✅ **COMPLETED & VERIFIED**  
**Date**: 2026-03-21  
**Commits**: 
- 48b32a9: fix: resolve model configuration discrepancy
- 46748d7: docs: document critical model configuration fix

---

## Problem Summary

The Me4BrAIn system was **ignoring dashboard configuration** and forcing a fallback to the 4B model for routing and synthesis operations.

| Setting | Expected | Actual (Before) | Now (Fixed) |
|---------|----------|-----------------|-----------|
| Dashboard: LLM_ROUTING_MODEL | qwen3.5-9b-mlx | ❌ Forced to qwen3.5:4b | ✅ qwen3.5-9b-mlx |
| Dashboard: LLM_SYNTHESIS_MODEL | qwen3.5-9b-mlx | ❌ Forced to qwen3.5:4b | ✅ qwen3.5-9b-mlx |
| Model Used for Routing | 9B (better) | 4B (worse) ❌ | 9B (better) ✅ |
| Model Used for Synthesis | 9B (better) | 4B (worse) ❌ | 9B (better) ✅ |

---

## Root Cause Analysis

### The Bug Chain

1. **API Route** calls `ToolCallingEngine.create_legacy()` (deprecated method)
2. **create_legacy()** checks `if config.use_local_tool_calling:` (True)
3. **Forces fallback**: `routing_model = config.ollama_model` (qwen3.5:4b)
4. **Ignores dashboard**: `LLM_ROUTING_MODEL` environment variable is completely overridden

### Code Location

**Before Fix** - `src/me4brain/engine/core.py` lines 241-243 (create_legacy):
```python
if config.use_local_tool_calling:
    routing_model = config.ollama_model  # ❌ FORCED 4B!
    synthesis_model = config.ollama_model  # ❌ FORCED 4B!
```

**Impact**: With `use_local_tool_calling=true`, any dashboard configuration is bypassed.

---

## The Fix

### 1. API Route Change

**File**: `src/me4brain/api/routes/engine.py`

```python
# BEFORE: Using deprecated legacy method
_engine_instance = await ToolCallingEngine.create_legacy()

# AFTER: Using current main factory method
_engine_instance = await ToolCallingEngine.create()
```

**Why**: `create()` delegates to `_create_with_hybrid_routing()` which respects dashboard config.

### 2. Core Logic Fix

**File**: `src/me4brain/engine/core.py` (Lines 342-345)

```python
# FIXED: Now respects dashboard configuration
# Resolve routing and synthesis models from config
# Respect dashboard preferences: LLM_ROUTING_MODEL and LLM_SYNTHESIS_MODEL
if routing_model is None:
    routing_model = config.model_routing  # ✅ Uses 9B from dashboard
if synthesis_model is None:
    synthesis_model = config.model_synthesis  # ✅ Uses 9B from dashboard
```

**Key Insight**: Instead of forcing fallback, we now use dashboard config as the source of truth.

### 3. Configuration Defaults Update

**File**: `src/me4brain/llm/config.py`

```python
# BEFORE
model_routing: str = "mlx-qwen3.5-9b-claude-4.6-opus-reasoning-distilled"  # Wrong for routing
model_synthesis: str = "qwen3.5-4b-mlx"  # 4B fallback

# AFTER
model_routing: str = "qwen3.5-9b-mlx"  # Correct: 9B for domain classification
model_synthesis: str = "qwen3.5-9b-mlx"  # Correct: 9B for synthesis
```

### 4. Environment Variable Fix

**File**: `/.env`

```bash
# BEFORE
LLM_ROUTING_MODEL='mlx/qwen3.5:9b'  # Non-existent model name
LLM_SYNTHESIS_MODEL='mlx/qwen3.5:9b'  # Non-existent model name

# AFTER
LLM_ROUTING_MODEL='qwen3.5-9b-mlx'  # Correct LM Studio format
LLM_SYNTHESIS_MODEL='qwen3.5-9b-mlx'  # Correct LM Studio format
```

---

## Verification

### Test 1: Configuration Loading ✅
```
✅ model_routing = qwen3.5-9b-mlx (from config)
✅ model_synthesis = qwen3.5-9b-mlx (from config)
✅ Config loads correctly from .env
```

### Test 2: Execution Flow ✅
```
✅ API calls: ToolCallingEngine.create()
✅ create() delegates to: _create_with_hybrid_routing()
✅ _create_with_hybrid_routing() uses: config.model_routing (9B)
✅ NOT forcing ollama_model fallback
```

### Test 3: Production Logs ✅
```
From API startup (2026-03-21 22:47:07):
{
  "routing_model": "qwen3.5-9b-mlx",
  "synthesis_model": "qwen3.5-9b-mlx",
  "tools_discovered": 139,
  "event": "engine_created_with_hybrid_routing"
}
```

### Test 4: Real Query Execution ✅
```
Query: "Which NBA teams are favorites in todays games?"
Response: 
- Tools called: 3 (nba_upcoming_games, nba_betting_odds, nba_team_stats)
- Status: Success ✅
- Models used: 9B (verified in logs)
```

---

## Model Hierarchy (Fixed)

The system now respects the correct configuration hierarchy:

```
1. Dashboard Config (Highest Priority)
   ├─ LLM_ROUTING_MODEL → used by _create_with_hybrid_routing()
   └─ LLM_SYNTHESIS_MODEL → used by _create_with_hybrid_routing()

2. System Defaults (Fallback)
   ├─ config.model_routing = "qwen3.5-9b-mlx"
   └─ config.model_synthesis = "qwen3.5-9b-mlx"

3. Ollama Fallback (Only for legacy paths)
   └─ config.ollama_model = "qwen3.5:4b" (UNUSED in routing/synthesis now)
```

---

## Performance Impact

### Before Fix
- **Routing Model**: 4B (qwen3.5:4b via Ollama)
- **Synthesis Model**: 4B (qwen3.5:4b via Ollama)
- **Domain Classification**: Lower accuracy, may misroute queries
- **Latency**: Slightly faster (smaller model) but poor quality
- **Quality**: Reduced reasoning capacity

### After Fix
- **Routing Model**: 9B (qwen3.5-9b-mlx via LM Studio)
- **Synthesis Model**: 9B (qwen3.5-9b-mlx via LM Studio)
- **Domain Classification**: Higher accuracy, better routing precision
- **Latency**: Slightly slower (larger model) but acceptable
- **Quality**: Improved reasoning and synthesis

---

## Deployment Checklist

- [x] Root cause identified and documented
- [x] Code fixed in `core.py`
- [x] Configuration defaults updated
- [x] Environment variables corrected
- [x] Execution flow verified
- [x] All tests passing
- [x] Production logs confirm fix
- [x] Real queries executing successfully
- [x] Commits created and pushed
- [x] Changelog updated
- [x] Documentation written

---

## Files Changed

| File | Lines | Change | Status |
|------|-------|--------|--------|
| src/me4brain/engine/core.py | 342-345 | Respect dashboard config | ✅ Deployed |
| src/me4brain/llm/config.py | 44, 62 | Update defaults to 9B | ✅ Deployed |
| /.env | 42-43 | Fix model names | ✅ Deployed |
| src/me4brain/api/routes/engine.py | 181 | Use create() not create_legacy() | ✅ Deployed |
| CHANGELOG.md | Added | Document fix | ✅ Deployed |

---

## Monitoring Recommendations

**Track these metrics over 24 hours to confirm improvement**:

1. **Query Latency**: Should be acceptable despite 9B being larger
2. **Domain Classification Accuracy**: Count successful vs misrouted queries
3. **Answer Quality**: Monitor user satisfaction/feedback
4. **Error Rates**: Should remain stable or decrease
5. **Model Loading**: Confirm qwen3.5-9b-mlx loads successfully

**Expected Results**:
- ✅ Correct model shown in logs (9B, not 4B)
- ✅ Domain routing more accurate
- ✅ Complex queries handled better
- ✅ Latency slightly higher but acceptable

---

## Conclusion

The critical model configuration discrepancy has been completely resolved. The system now correctly respects dashboard preferences and uses the 9B model for improved reasoning quality and classification accuracy.

**Status**: ✅ **PRODUCTION READY**

---

## Quick Reference

**To verify this fix is working**:

1. Check API logs on startup:
   ```bash
   grep "routing_model.*9b" /path/to/logs
   # Should show: "routing_model": "qwen3.5-9b-mlx"
   ```

2. Verify configuration:
   ```bash
   python -c "
   from me4brain.llm.config import get_llm_config
   config = get_llm_config()
   print(f'routing: {config.model_routing}')
   print(f'synthesis: {config.model_synthesis}')
   "
   # Should show both as "qwen3.5-9b-mlx"
   ```

3. Test a query:
   ```bash
   curl -X POST http://localhost:8089/v1/engine/query \
     -H "Content-Type: application/json" \
     -d '{"query":"Test query","timeout_seconds":60}'
   ```

---

**Git Commits**:
- `48b32a9`: fix: resolve model configuration discrepancy
- `46748d7`: docs: document critical model configuration fix

