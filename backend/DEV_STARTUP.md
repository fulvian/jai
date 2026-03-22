# Development Mode Startup Guide

**Status**: READY TO START

---

## Quick Start (2 minutes)

### Option 1: Start All Services (Recommended)

```bash
cd Me4BrAIn
bash scripts/start_all_dev.sh
```

This will start:
- Backend server (http://localhost:8089)
- Frontend server (http://localhost:3020)
- Monitoring dashboard

### Option 2: Start Services Individually

#### Terminal 1: Backend
```bash
cd Me4BrAIn
bash scripts/start_dev.sh
```

#### Terminal 2: Frontend (PersAn)
```bash
cd PersAn
# Start gateway first
cd packages/gateway && npm run dev
# Then start frontend
cd frontend && npm run dev
```

#### Terminal 3: Monitoring
```bash
cd Me4BrAIn
python scripts/monitor_intent.py
```

---

## Pre-Startup Checklist

Before running the system, always verify these:

### ✅ Check 1: Debug Mode Enabled

Look for this in the backend log:
```
{"debug": true, ...}
```

If you see `"debug": false`, the auth is not working correctly.

**How to fix**:
1. Ensure you're running the backend from the Me4BrAIn project directory
2. Verify `ME4BRAIN_DEBUG=true` in `.env`
3. Restart the backend
4. Check logs for `"debug": true`

### ✅ Check 2: No 401 Errors in Gateway Logs

The gateway should not show 401 errors when calling the backend.

### ✅ Check 3: Frontend Loads

Open http://localhost:3020 in your browser.

### ✅ Check 4: Sessions Appear

Open the sidebar and check that sessions are loading correctly.

---

## What Gets Started

### Backend Server
- **URL**: http://localhost:8089
- **Port**: 8089
- **Status**: Logs to `logs/backend.log`
- **Features**:
  - Dev mode authentication bypass enabled
  - UnifiedIntentAnalyzer available
  - Query caching enabled
  - Monitoring enabled

### Gateway Server (PersAn)
- **URL**: http://localhost:3030
- **Port**: 3030
- **Status**: Logs to `logs/gateway.log`
- **Features**:
  - Session persistence via Redis
  - SSE streaming for chat
  - WebSocket support

### Frontend Server (PersAn)
- **URL**: http://localhost:3020
- **Port**: 3020
- **Status**: Logs to `logs/frontend.log`
- **Features**:
  - Next.js web app
  - Real-time chat interface
  - Session management

### Monitoring Dashboard
- **Status**: Terminal-based dashboard
- **Logs**: `logs/monitor.log`
- **Features**:
  - Real-time metrics
  - Query volume tracking
  - Accuracy monitoring
  - Latency tracking

---

## Testing the System

### 1. Open Web UI
```
http://localhost:3020
```

### 2. Send Weather Query
```
Che tempo fa a Caltanissetta?
```

### 3. Expected Result
System should:
1. Classify query as TOOL_REQUIRED + geo_weather
2. Retrieve actual weather data
3. Respond with real weather information

### 4. Monitor Metrics
Check the monitoring dashboard (Terminal 3) for:
- Query classification
- Latency
- Cache hit rate
- Error rate

---

## Configuration

### Environment Variables

The system uses these settings (from `.env`):

```bash
# Feature Flag
USE_UNIFIED_INTENT_ANALYZER=true
UNIFIED_INTENT_ROLLOUT_PHASE=disabled
UNIFIED_INTENT_TRAFFIC_PERCENTAGE=0

# Intent Analysis
INTENT_ANALYSIS_TIMEOUT=5.0
INTENT_ANALYSIS_MODEL=model_routing
INTENT_CACHE_TTL=300

# Cache
INTENT_CACHE_MAX_SIZE=10000

# Batch Processing
INTENT_BATCH_SIZE=10
INTENT_BATCH_TIMEOUT_MS=100
```

### Dev Mode Configuration

For development mode (authentication bypass), ensure these are set in `.env`:

```bash
# Enable dev mode (bypasses JWT authentication)
ME4BRAIN_DEBUG=true

# OR use the legacy env var (also works)
ME4BRAIN_DEV_MODE=true
```

**IMPORTANT**: If neither is set, the backend will require valid JWT tokens for authentication, resulting in 401 Unauthorized errors.

### Modify Configuration

Edit `.env` file and restart services:

```bash
# Edit .env
nano .env

# Restart backend
# (Stop current process and run start_dev.sh again)
```

---

## Common Issues

### Issue: 401 Unauthorized on API calls

**Cause**: Debug mode is not enabled (`.env` not loaded correctly)

**Symptoms**:
- All API calls return 401 Unauthorized
- Gateway logs show `Me4BrAInError: 401 Unauthorized`

**Solution**:
1. Ensure you're running the backend from the **Me4BrAIn project directory**
   ```bash
   cd /path/to/Me4BrAIn
   .venv/bin/uvicorn me4brain.api.main:app --host 0.0.0.0 --port 8089
   ```
2. Verify `ME4BRAIN_DEBUG=true` in `.env`
3. Restart the backend
4. Check logs for `"debug": true`

### Issue: Neo4j Connection Refused

**Cause**: Neo4j is not running

**Symptoms**:
- Backend logs show `ConnectionRefusedError`
- Semantic memory initialization fails

**Solution**: Start Neo4j or use Docker:
```bash
# Start Neo4j
docker run -d -p 7474:7687:7474
# Or via Docker
docker-compose up -d neo4j
```

### Issue: Redis Connection Refused

**Cause**: Redis is not running

**Symptoms**:
- Session persistence fails
- Cache operations fail

**Solution**: Start Redis
```bash
# Start Redis
redis-server
# Or via Docker
docker-compose up -d redis
```

---

## Recommended Ports
| Service | Port | Description |
| -------- | ------ | ------------- |
| Me4BrAIn Backend | 8089 | Main API server |
| PersAn Gateway | 3030 | API Gateway for frontend |
| PersAn Frontend | 3020 | Next.js web app |
| Redis | 6379 | Session persistence |
| Neo4j | 7687 | Knowledge graph |
| Qdrant | 6333 | Vector store |
| MLX/LM Studio | 1234 | Local LLM inference |

---

## Full Stack Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    PersAn Frontend (3020)                          │
│                           │                                     │
│                    PersAn Gateway (3030)                          │
│                           │                                     │
│                    Me4BrAIn Backend (8089)                          │
│                           │                                     │
│         ┌─────────────────────────────────────────────────────────────────────┐
│         │                Redis (6379)                │
│         │                Neo4j (7687)                │
│         │               Qdrant (6333)                │
│         │             MLX Server (1234)               │
│         └─────────────────────────────────────────────────────────────────────┘
```
                                        (optional: PostgreSQL, LM Studio)

---

## Related Files
- `CHANGELog.md` - This file
- `RECENT_CHANGES.md` - Recent changes
- `ProjectStatus.md` - Project status
- `docs/deployment/` - Deployment docs

---

**Last Updated**: 2026-03-13
