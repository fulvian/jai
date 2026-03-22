# Fix Plan: Provider Prefix Bug in LLM Requests

## Problem Summary

**Root Cause**: When model IDs contain a provider prefix (format: `provider_id:model_id`), they are passed directly to NanoGPT API which doesn't recognize this format, resulting in `400 Bad Request - Model not supported`.

**Example**: `fa548723-e5d1-4dc9-847b-c729681c852c:qwen/qwen3.5-397b-a17b-thinking`

**Solution**: Use `resolve_model_client()` from `provider_factory.py` to:
1. Detect provider-prefixed model IDs
2. Extract the actual model name
3. Return the correct client for that provider

---

## Files to Modify

### Priority 1: Core Engine Files (Most Critical)

#### 1. `src/me4brain/engine/unified_intent_analyzer.py`
- **Lines 237-243, 445-454**: LLMRequest creation uses `self.config.model_routing` directly
- **Fix**: Import and use `resolve_model_client()` to get correct client and model name

#### 2. `src/me4brain/engine/hybrid_router/domain_classifier.py`
- **Line 152**: Uses config model directly in LLMRequest
- **Fix**: Same pattern as above

#### 3. `src/me4brain/engine/hybrid_router/query_decomposer.py`
- **Line 229**: Uses config model directly
- **Fix**: Same pattern

#### 4. `src/me4brain/engine/hybrid_router/router.py`
- **Lines 531, 560**: LLMRequest with model from config
- **Fix**: Same pattern

### Priority 2: Other Engine Components

#### 5. `src/me4brain/engine/iterative_executor.py`
- **Lines 1459, 1966**: LLMRequest creation
- **Fix**: Use resolve_model_client()

#### 6. `src/me4brain/engine/core.py`
- **Lines 794, 1026, 1222**: Multiple LLMRequest calls
- **Fix**: Use resolve_model_client()

#### 7. `src/me4brain/core/cognitive_pipeline.py`
- **Lines 272, 526, 2224, 2312**: LLMRequest creation
- **Fix**: Use resolve_model_client()

### Priority 3: Supporting Files

#### 8. `src/me4brain/engine/router.py`
- **Line 93**: LLMRequest creation

#### 9. `src/me4brain/core/orchestrator.py`
- **Line 299**: LLMRequest creation

#### 10. `src/me4brain/core/tool_agent.py`
- **Lines 177, 321**: LLMRequest creation

---

## Implementation Pattern

For each file, replace:

```python
# BEFORE
llm_request = LLMRequest(
    messages=[...],
    model=self.config.model_routing,  # Contains "uuid:model_name"
    ...
)
response = await self.llm_client.generate_response(llm_request)
```

With:

```python
# AFTER
from me4brain.llm.provider_factory import resolve_model_client

client, actual_model = resolve_model_client(self.config.model_routing)
llm_request = LLMRequest(
    messages=[...],
    model=actual_model,  # Just "model_name" without prefix
    ...
)
response = await client.generate_response(llm_request)
```

---

## Optional: Helper Function

Create a utility function to reduce code duplication:

```python
# In me4brain/llm/provider_factory.py

async def make_resolved_llm_request(
    model_id: str,
    messages: list,
    **kwargs,
) -> tuple[LLMProvider, LLMRequest]:
    """Create an LLMRequest with automatic provider resolution.
    
    Handles both provider-prefixed and simple model IDs.
    
    Args:
        model_id: Model identifier (provider-prefixed or simple)
        messages: List of Message objects
        **kwargs: Additional LLMRequest parameters
        
    Returns:
        Tuple of (resolved_client, llm_request)
    """
    client, actual_model = resolve_model_client(model_id)
    request = LLMRequest(
        messages=messages,
        model=actual_model,
        **kwargs,
    )
    return client, request
```

---

## Testing Plan

1. **Unit Tests**: Add tests for `resolve_model_client()` with various model ID formats
2. **Integration Tests**: Test intent analysis with provider-prefixed models
3. **Manual Test**: 
   - Configure a provider-prefixed model in settings
   - Send a query that triggers intent analysis
   - Verify no "Model not supported" error

---

## Rollback Plan

If issues arise:
1. Revert all modified files
2. Alternative fix: Strip provider prefix in `NanoGPTClient._prepare_payload()`

---

## Estimated Effort

- **Priority 1 files**: ~1 hour
- **Priority 2 files**: ~30 minutes  
- **Priority 3 files**: ~1 hour
- **Testing**: ~30 minutes
- **Total**: ~3 hours
