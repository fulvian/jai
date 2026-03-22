# JAI - Quick Start Checklist

## Pre-Implementation Verification

Before implementing any fixes, run these diagnostic steps:

### 1. Check Ollama Status
```bash
# Is Ollama running?
curl http://localhost:11434/api/tags

# What models are loaded?
ollama list

# Pull the required model if missing
ollama pull qwen3:14b
```

### 2. Check Current LLM Configuration
```bash
# View current env settings
cd backend
grep -E "^(LLM_|OLLAMA_)" .env

# Check what model the code is using
grep -r "model_routing" src/me4brain/llm/config.py
```

### 3. Run Backend with Debug Logging
```bash
cd backend
LOG_LEVEL=DEBUG uv run me4brain
```

### 4. Test Domain Classification Manually
```bash
# Send a test query and watch logs
curl -X POST http://localhost:8000/v1/engine/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Quali sono le partite NBA stasera?", "debug": true}'
```

### 5. Look for These Log Messages

**Good Signs** (LLM is working):
```
domain_classification_llm_success
domain_classification_start
ollama_request_sent
ollama_response_received
```

**Bad Signs** (Fallback triggered):
```
domain_classification_fallback
domain_classification_timeout
ollama_http_error
ollama_connect_error
ollama_model_not_loaded
```

---

## Immediate Fixes (Can Do Today)

### Fix 1: Sync Environment Variables (5 minutes)

Add these lines to `backend/.env`:

```bash
# Copy these EXACT lines to your .env file
LLM_PRIMARY_MODEL=qwen3:14b
LLM_ROUTING_MODEL=qwen3:14b
LLM_SYNTHESIS_MODEL=qwen3:14b
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen3:14b
LLM_LOCAL_ONLY=true
USE_LOCAL_TOOL_CALLING=true
```

Then restart the backend.

### Fix 2: Verify Model is Loaded (2 minutes)

```bash
# Check if qwen3:14b is loaded
ollama list | grep qwen3

# If not, pull it
ollama pull qwen3:14b

# Verify it works
ollama run qwen3:14b "Hello, respond with just OK"
```

### Fix 3: Reduce Timeout for Debugging (1 minute)

Temporarily edit `backend/src/me4brain/engine/hybrid_router/domain_classifier.py`:

Find:
```python
async with asyncio.timeout(600):
```

Change to:
```python
async with asyncio.timeout(30):  # 30 seconds for debugging
```

---

## Expected Behavior After Fixes

1. **Startup logs should show**:
   ```
   ollama_client_initialized base_url=http://localhost:11434/v1/ model=qwen3:14b
   ```

2. **Query logs should show**:
   ```
   domain_classification_start query_preview=Quali sono le parti...
   domain_classification_llm_success domains=['sports_nba'] confidence=0.95
   ```

3. **Should NOT see**:
   ```
   domain_classification_fallback
   ```

---

## Troubleshooting

### Problem: "Connection refused"
**Cause**: Ollama not running
**Fix**: `ollama serve`

### Problem: "404 Not Found"  
**Cause**: Model not loaded or wrong model name
**Fix**: `ollama pull qwen3:14b` and verify `.env` has correct model name

### Problem: "Timeout after 30s"
**Cause**: Model too slow or inference stuck
**Fix**: Try a smaller model: `ollama pull qwen3:4b`

### Problem: "JSON parse error"
**Cause**: LLM response not valid JSON
**Fix**: Check temperature setting (should be 0.1-0.3 for structured output)

---

## Files Modified by Implementation Plan

| File | Change Type |
|------|-------------|
| `backend/.env` | Add LLM config vars |
| `backend/src/me4brain/engine/hybrid_router/types.py` | Config factory |
| `backend/src/me4brain/engine/hybrid_router/domain_classifier.py` | Retry logic |
| `backend/src/me4brain/llm/health.py` | Model verification |
| `backend/src/me4brain/llm/config.py` | Env var sync |
| `backend/src/me4brain/api/routes/llm_config.py` | Router reset |
