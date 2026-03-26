# LM Studio Integration - Context Length Support

## Overview

JAI now supports dynamic `context_length` configuration for LM Studio models. When a user sets `context_window_size` in the dashboard settings, the system will load (or reload) the specified LM Studio model with the requested context length.

## How It Works

### Flow

```
User sets context_window in Dashboard (e.g., 32768)
         ↓
Backend receives config update
         ↓
When making a query, backend calls LM Studio API:
POST /api/v1/models/load
{
  "model": "qwen/qwen3.5-9b",
  "context_length": 32768
}
         ↓
LM Studio loads model with specified context
```

### Auto-Reload Behavior

If the model is already loaded but with a different `context_length`, the system will automatically reload it:

```
Model currently loaded with context_length=8192
User changes context_window to 32768
         ↓
System detects mismatch
         ↓
Calls POST /api/v1/models/load with new context_length
         ↓
Model reloaded with new context_length (takes ~3-4 seconds)
```

## Model Discovery Information

The system now exposes additional LM Studio model information:

| Field | Description |
|-------|-------------|
| `context_window` | Current context_length (8192 if model is loaded) |
| `max_context_length` | Maximum context the model supports (e.g., 262144 for Qwen models) |
| `is_loaded` | Whether the model is currently loaded in LM Studio |
| `quantization` | Model quantization (e.g., "Q4_K_M") |

### Example API Response

```json
{
  "id": "qwen/qwen3.5-9b",
  "name": "qwen3.5-9b (Locale)",
  "provider": "local_mlx",
  "context_window": 8192,
  "max_context_length": 262144,
  "is_loaded": true,
  "quantization": "Q4_K_M"
}
```

## Configuration

### Via Dashboard

1. Open Dashboard at http://localhost:3020
2. Go to Settings → LLM Models
3. Modify "Context Window" parameter
4. Save Configuration

### Via Environment Variables

```env
# In backend/.env
LLM_CONTEXT_WINDOW_SIZE=32768
```

## Files Modified

| File | Changes |
|------|---------|
| `src/me4brain/llm/nanogpt.py` | LMStudioAutoLoader with context_length support |
| `src/me4brain/llm/model_discovery.py` | Enhanced LM Studio API discovery |
| `src/me4brain/api/routes/llm_config.py` | Added max_context_length, is_loaded fields |

## LM Studio API Reference

### Load Model with Context Length

```bash
POST http://localhost:1234/api/v1/models/load
Content-Type: application/json

{
  "model": "qwen/qwen3.5-9b",
  "context_length": 32768
}
```

### Response

```json
{
  "type": "llm",
  "instance_id": "qwen/qwen3.5-9b",
  "load_time_seconds": 3.674,
  "status": "loaded"
}
```

### Get Loaded Models Info

```bash
GET http://localhost:1234/api/v1/models
```

Returns detailed model info including `loaded_instances[].config.context_length`.
