# Phase 3: Code Cleanup & Deprecation Removal - State Tracking

**Status**: PHASE 3 IN PROGRESS 🔄  
**Started**: 2026-03-22T12:35:39+01:00  
**Previous Phase**: Phase 2 - COMPLETE (94/94 tests passing)  
**Phase**: Code Cleanup & Deprecation Removal

---

## Phase 3 Components (3 total) - IN PROGRESS

| Component | Objective | Status | Notes |
|-----------|-----------|--------|-------|
| 3.1 | Delete Deprecated Files | ⏳ PENDING | Remove registry_deprecated.py files |
| 3.2 | Remove Deprecated Functions | ⏳ PENDING | Remove create_legacy() and _LEGACY_FALLBACK |
| 3.3 | Clean Qdrant Collections | ⏳ PENDING | Remove old collections, keep me4brain_tools |

---

## Implementation Order

1. **3.2 Remove Deprecated Functions** - IN PROGRESS
   - ✅ Deleted `create_legacy()` from engine/core.py
   - ✅ Deleted `create_with_hybrid_routing()` from engine/core.py
   - ⏳ Remove USE_LEGACY_FALLBACK flag from cognitive_pipeline.py
   - ⏳ Remove legacy fallback code block (lines 869-968)
   - ⏳ Keep _detect_multi_tool_services for reference (no longer called)

2. **3.1 Delete Deprecated Files** - PENDING
   - Analyze if registry_deprecated.py can be safely removed
   
3. **3.3 Clean Qdrant Collections** - PENDING
   - Remove old collections, keep me4brain_tools

---

## Files to Target

### Delete (Confirmed Deprecated)
- ✅ FOUND: `backend/src/me4brain/core/skills/registry_deprecated.py` (372 lines)
  - Status: Marked as deprecated in file docstring
  - Imports: Used by `retriever.py`, `crystallizer.py`, and `__init__.py`
  - Action: DELETE + update imports

### Files NOT Found (Per Phase 3 Plan)
- ❌ `backend/src/me4brain/tools/registry_deprecated.py` - Does not exist (skip)

### Modify (Remove Deprecated Code)
- `backend/src/me4brain/engine/core.py` - Contains 3 functions to remove:
  - `create_legacy()` - Sends ALL 129+ tools to LLM (payload size risk)
  - `create_with_hybrid_routing()` - Alias for create() with deprecation warning
  - `_create_with_hybrid_routing()` - Private factory method (refactor)
  
- `backend/src/me4brain/core/cognitive_pipeline.py` - Remove:
  - `USE_LEGACY_FALLBACK` flag and env var check
  - Related legacy fallback path code
  - `_detect_multi_tool_services()` function (deprecated, legacy-only)

### Verify (Check for Dependencies)
- ✅ No test files import deprecated functions (grep verified)
- ✅ No tests import registry_deprecated (grep verified)
- Test suite uses only current `create()` factory method

---

## Baseline Verification

**Before Phase 3 Cleanup**:
- All 94 tests passing from Phase 1+2 ✅
- Baseline to ensure no regressions during cleanup
- Target: All 94 tests still passing after cleanup

---

## Next Steps

1. [ ] Analyze deprecated files for active dependencies
2. [ ] Run grep search for imports of deprecated modules
3. [ ] Delete deprecated registry files
4. [ ] Remove deprecated functions from core.py
5. [ ] Remove _LEGACY_FALLBACK from cognitive_pipeline.py
6. [ ] Run full test suite to verify no regressions
7. [ ] Commit changes to git

---

## Agent History

| Timestamp | Agent | Task | Status |
|-----------|-------|------|--------|
| 2026-03-22T12:35:39+01:00 | Kilo (General Manager) | Initialize Phase 3 tracking + update docs | IN PROGRESS |

