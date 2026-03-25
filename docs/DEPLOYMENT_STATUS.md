# JAI - Local Deployment Status

**Date**: 2026-03-25  
**Time**: 16:33 CET  
**Status**: ✅ SYSTEM DEPLOYED AND FUNCTIONAL

---

## Services Status

| Service | Port | Status | Notes |
|---------|------|--------|-------|
| **Backend (FastAPI)** | 8000 | ✅ Running | v0.1.0, CPU embeddings |
| **Frontend (Next.js)** | 3020 | ✅ Running | React UI |
| **Gateway (Fastify)** | 3030 | ✅ Running | API Gateway |
| **PostgreSQL** | 5432 | ✅ Healthy (Docker) | Primary database |
| **Redis** | 6379 | ✅ Healthy (Docker) | Cache & sessions |
| **Qdrant** | 6333 | ✅ Running (Docker) | Vector database |
| **Neo4j** | 7474/7687 | ✅ Running (Docker) | Graph database |

---

## Architecture Changes (2026-03-25)

### Key Updates

1. **Port Standardization**: Backend canonical port is now **8000** (was 8089)
2. **PyTorch CPU-only**: Embedding model runs on CPU to avoid VRAM issues on AMD ROCm
3. **Gateway Alignment**: All 8089 fallback references removed, points to :8000
4. **Neo4j Container**: Runs in Docker instead of local brew

### Environment Variables

Backend now uses `ME4BRAIN_*` prefix for core config:
- `ME4BRAIN_PORT=8000`
- `ME4BRAIN_DEBUG=true`
- `EMBEDDING_DEVICE=cpu` (forced, not mps)

### Frontend Ports

- Frontend: **3020** (not 3000)
- Gateway: **3030**
- Backend: **8000**

---

## Verification Commands

```bash
# Check all ports
ss -tlnp | grep -E "(3020|3030|8000)"

# Backend health
curl http://localhost:8000/health

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:3020

# Gateway
curl http://localhost:3030/api/config/test
```

---

## Health Check Response

```json
{
  "status": "healthy",
  "version": "0.1.0",
  "uptime_seconds": 147.88,
  "services": [
    {"name": "redis", "status": "ok"},
    {"name": "qdrant", "status": "ok", "details": {"collections_count": 3}},
    {"name": "neo4j", "status": "ok"},
    {"name": "bge_m3", "status": "ok", "details": {"dimension": 1024, "model_loaded": true}},
    {"name": "database", "status": "ok"},
    {"name": "llm_providers", "status": "ok", "details": {"lmstudio_healthy": true}}
  ]
}
```

---

## Known Issues

1. **Ollama Not Running**: Backend logs show model not found - Ollama not installed/started
2. **LMStudio Fallback**: LLM uses LMStudio when Ollama unavailable
3. **VRAM Pressure**: AMD iGPU at 94% - embeddings forced to CPU

---

## Quick Test

```bash
# Test backend API
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"Ciao"}]}'
```

---

## Files Modified (2026-03-25)

### Backend
- `backend/pyproject.toml` - UV index CPU per torch
- `backend/uv.lock` - Lock file generato
- `backend/src/me4brain/config/settings.py` - port=8000, device=cpu
- `backend/.env` - Aggiornato con variabili normalizzate
- `backend/.env.normalized` - Template variabili corrette

### Gateway (8089 → 8000)
- `frontend/packages/gateway/src/services/session_manager_instance.ts`
- `frontend/packages/gateway/src/routes/config.ts`
- `frontend/packages/gateway/src/routes/providers.ts`
- `frontend/packages/gateway/src/services/graph_session_service.ts`
- `frontend/packages/gateway/src/services/title_generator.ts`

### Frontend
- `frontend/frontend/src/lib/whisper.ts` - Stub per modulo mancante

### Documentation
- `docs/issues_analysis/local-deploy-baseline-2026-03-25/` - Baseline report e runbook

---

## Startup Commands

```bash
# 1. Docker services
cd /home/fulvio/coding/jai
docker-compose -f docker-compose.dev.yml up -d
docker run -d --name jai-neo4j -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/neo4j_password neo4j:5

# 2. Backend
cd /home/fulvio/coding/jai/backend
uv run uvicorn me4brain.api.main:app --host 0.0.0.0 --port 8000

# 3. Gateway
cd /home/fulvio/coding/jai/frontend
npm run dev --workspace=packages/gateway

# 4. Frontend
cd /home/fulvio/coding/jai/frontend/frontend
npm run dev
```

---

## Next Steps for Full LLM Support

```bash
# Install Ollama (optional, LMStudio already working)
brew install ollama
ollama pull qwen3.5:9b

# Or continue using LMStudio
```
