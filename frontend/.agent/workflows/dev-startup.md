---
description: How to start the full Me4BrAIn + PersAn development stack (uvicorn local mode)
---

# Full Development Stack Startup

## ⚠️ CRITICAL: Read This First

- **Me4BrAIn runs locally via uvicorn** (NOT inside Docker container)
- Docker is used ONLY for infrastructure services (Qdrant, Redis, Neo4j, Postgres)
- **PersAn** is a separate project at `/Users/fulvioventura/persan`
- Both projects have **official startup scripts** that handle everything

---

## Architecture Overview

```
┌─────────────────────────────────────────────────┐
│                   PersAn                        │
│  Frontend (Next.js :3020) ←→ Gateway (:3030)    │
└──────────────────────┬──────────────────────────┘
                       │ HTTP/SSE
                       ▼
┌─────────────────────────────────────────────────┐
│         Me4BrAIn API (:8089/v1/...)             │
│         uvicorn local (uv run python)           │
└──────────────────────┬──────────────────────────┘
                       │
    ┌──────────┬───────┴───────┬──────────┐
    ▼          ▼               ▼          ▼
 Qdrant    Redis           Neo4j     Postgres
 :6334     :6389           :7697     :5489
 (Docker)  (Docker)        (Docker)  (Docker)
```

---

## Port Map

| Service             | Port | Type                         |
| ------------------- | ---- | ---------------------------- |
| Me4BrAIn API        | 8089 | uvicorn local                |
| Me4BrAIn Docker API | 8000 | Docker (legacy, ignore)      |
| PersAn Frontend     | 3020 | Next.js dev                  |
| PersAn Gateway      | 3030 | tsx (nohup background)       |
| Endogram Frontend   | 3100 | Next.js dev (altro progetto) |
| Qdrant              | 6334 | Docker                       |
| Redis               | 6389 | Docker                       |
| Neo4j Browser       | 7478 | Docker                       |
| Neo4j Bolt          | 7697 | Docker                       |
| Postgres            | 5489 | Docker                       |

> **IMPORTANTE**: Me4BrAIn API espone tutte le route con prefix `/v1`.
> Esempio: `http://localhost:8089/v1/engine/query`
> L'unica eccezione è `/health` che è senza prefix.

---

## Step 1: Start Me4BrAIn (Script Ufficiale)

Me4BrAIn **DEVE** essere avviato in un terminale dedicato (foreground):

// turbo
```bash
bash /Users/fulvioventura/me4brain/scripts/start.sh
```

This script automatically:
1. Kills any existing uvicorn processes
2. Starts Docker infrastructure (Qdrant, Redis, Neo4j, Postgres)
3. Syncs Python dependencies (`uv sync`)
4. Starts uvicorn on **port 8089** with reload enabled

### Verify Me4BrAIn is healthy:
// turbo
```bash
curl -s http://localhost:8089/health | jq .
```

Expected: `{"status": "healthy", ...}`

> **NOTE**: BGE-M3 model takes ~30-60s to load. Health check shows `"loading"` initially.
> Wait until `curl http://localhost:8089/health/models` returns `"ready": true`.

---

## Step 2: Start PersAn (Script Ufficiale)

PersAn Gateway + Frontend vengono avviati come **processi background persistenti** (nohup + disown):

// turbo
```bash
bash /Users/fulvioventura/persan/scripts/start.sh
```

This script automatically:
1. Kills any existing Gateway/Frontend processes
2. Frees occupied ports (3020, 3030)
3. Verifies Me4BrAIn is reachable
4. Starts Gateway on **port 3030** (background, nohup)
5. Starts Frontend on **port 3020** (background, nohup)
6. Reports PIDs and log file locations

### Log Files:
```bash
tail -f /tmp/persan-gateway.log   # Gateway logs
tail -f /tmp/persan-frontend.log  # Frontend logs
```

### Access PersAn:
Open http://localhost:3020 in browser.

---

## Key Configuration Files

| File                                              | Purpose                                                       |
| ------------------------------------------------- | ------------------------------------------------------------- |
| `/Users/fulvioventura/me4brain/.env`              | Me4BrAIn env vars (DB URLs, API keys, ports)                  |
| `/Users/fulvioventura/persan/.env`                | Gateway config (`ME4BRAIN_URL=http://localhost:8089`)         |
| `/Users/fulvioventura/persan/frontend/.env.local` | Frontend config (`NEXT_PUBLIC_API_URL=http://localhost:3030`) |

### URL Resolution Chain:
```
Frontend (.env.local)
  NEXT_PUBLIC_API_URL=http://localhost:3030
    → Gateway (.env)
      ME4BRAIN_URL=http://localhost:8089
        → Me4BrAIn Client adds /v1 automatically
          → Final: http://localhost:8089/v1/engine/query
```

---

## Stop Everything

### Stop PersAn (Gateway + Frontend):
```bash
bash /Users/fulvioventura/persan/scripts/stop.sh
```

### Stop Me4BrAIn API (uvicorn):
```bash
pkill -f "uvicorn.*me4brain"
```
Or just Ctrl+C the terminal where start.sh is running.

### Stop Docker infrastructure:
```bash
cd /Users/fulvioventura/me4brain && docker compose -f docker/docker-compose.yml down
```

---

## Full Restart (Nuclear)

```bash
# 1. Stop everything
pkill -f "uvicorn.*me4brain" 2>/dev/null
bash /Users/fulvioventura/persan/scripts/stop.sh

# 2. Wait
sleep 3

# 3. Start Me4BrAIn (in a dedicated terminal)
bash /Users/fulvioventura/me4brain/scripts/start.sh

# 4. Wait for Me4BrAIn to be ready (check health)
# curl http://localhost:8089/health/models  → "ready": true

# 5. Start PersAn
bash /Users/fulvioventura/persan/scripts/start.sh
```

---

## Common Issues

### Me4BrAIn: `loop_factory` TypeError
**Cause**: `nest_asyncio` conflicts with uvicorn 0.40+
**Fix**: Already patched in `src/me4brain/api/main.py`

### BGE-M3 shows "loading" forever
**Cause**: Health check was checking wrong attribute name (`_model` vs `model`)
**Fix**: Corrected in `health.py` — now checks `emb.model` (without underscore)

### PersAn processes die immediately
**Cause**: Processes started without nohup/disown get terminated when shell exits
**Fix**: Use `bash /Users/fulvioventura/persan/scripts/start.sh` (uses nohup + disown)

### PersAn: `Failed to fetch` when creating sessions
**Cause**: Gateway not running on port 3030
**Fix**: Start PersAn with `bash /Users/fulvioventura/persan/scripts/start.sh`

### Me4BrAIn Docker container on port 8000
**Note**: Docker compose also starts a `me4brain-api` container on port 8000.
This is the **Docker version** and NOT the local development server.
For development, always use the **local uvicorn on port 8089**.

### Tools re-indexing
**Command**: Run locally (NOT in Docker):
```bash
cd /Users/fulvioventura/me4brain && .venv/bin/python scripts/reindex_tools.py
```
