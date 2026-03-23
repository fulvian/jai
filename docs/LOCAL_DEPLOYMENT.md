# JAI - Local Development Deployment Guide

**Version**: 1.0  
**Date**: 2026-03-23  
**Status**: READY FOR LOCAL DEPLOYMENT

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Service Dependencies](#service-dependencies)
5. [Setup Procedures](#setup-procedures)
   - [Step 1: Docker Services](#step-1-docker-services)
   - [Step 2: Environment Configuration](#step-2-environment-configuration)
   - [Step 3: Backend Setup](#step-3-backend-setup)
   - [Step 4: Frontend Setup](#step-4-frontend-setup)
6. [Startup Procedures](#startup-procedures)
   - [Starting Backend](#starting-backend)
   - [Starting Frontend](#starting-frontend)
   - [Using Helper Scripts](#using-helper-scripts)
7. [Health Verification](#health-verification)
8. [Service Ports](#service-ports)
9. [Troubleshooting](#troubleshooting)
10. [Daily Development Workflow](#daily-development-workflow)

---

## Overview

This guide covers the complete local development deployment for JAI (Me4BrAIn + PersAn) using the **Hybrid Development Mode**:

- **Backend** (Me4BrAIn): Runs natively on your machine for faster hot reload and better debugging
- **Frontend** (PersAn): Runs natively with Next.js hot reload
- **Dependencies**: PostgreSQL, Redis, Qdrant run in Docker for easy management

### Why Hybrid Mode?

| Aspect | Docker Only | Hybrid (Recommended) |
|--------|-------------|---------------------|
| **Hot Reload** | 2-3s | <100ms |
| **RAM Usage** | 6-8GB | 3-4GB |
| **CPU Usage** | 15-25% | 5-10% |
| **Debugging** | Harder | Easy (breakpoints work) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Local Machine                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │              PersAn Frontend (Next.js)                      │   │
│   │              Port: 3000                                     │   │
│   │              URL: http://localhost:3000                     │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              │ HTTP / WebSocket                     │
│                              ▼                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │              Gateway (Fastify) ⚠️ MUST CONNECT TO :8000    │   │
│   │              Port: 3030                                     │   │
│   │              ME4BRAIN_URL=http://localhost:8000            │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              │ HTTP / SSE                           │
│                              ▼                                      │
│   ┌─────────────────────────────────────────────────────────────┐   │
│   │              Me4BrAIn Backend (FastAPI)                     │   │
│   │              Port: 8000                                     │   │
│   │              URL: http://localhost:8000                     │   │
│   │              API Docs: http://localhost:8000/docs           │   │
│   └─────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│         ┌────────────────────┼────────────────────┐                │
│         │                    │                    │                │
│         ▼                    ▼                    ▼                │
│   ┌──────────┐        ┌──────────┐        ┌──────────┐           │
│   │PostgreSQL│        │  Redis   │        │  Qdrant  │           │
│   │  5432    │        │   6379   │        │   6333   │           │
│   └──────────┘        └──────────┘        └──────────┘           │
│   (Docker)            (Docker)            (Docker)                │
│                                                                      │
│   Optional:                                                          │
│   - Neo4j (Graph DB) - if using semantic memory                      │
│   - Ollama (Local LLM) - if using local models                       │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### ⚠️ Important: Gateway → Backend Connection

The Gateway **must** proxy to the backend on **port 8000** (not 8089!).

- Old PersAn projects used port 8089 for Me4BrAIn
- JAI monorepo uses port **8000** for Me4BrAIn backend

Start gateway with: `ME4BRAIN_URL=http://localhost:8000 npm run dev --filter=gateway`

---

## Prerequisites

### Required Software

| Software | Version | Purpose |
|----------|---------|---------|
| Docker Desktop | 24.0+ | Container management |
| Python | 3.12+ | Backend runtime |
| Node.js | 20.0+ | Frontend runtime |
| pip/uv | latest | Python package manager |

### Verify Installations

```bash
# Check Docker
docker --version
docker compose version

# Check Python
python --version  # Should be 3.12+

# Check Node
node --version  # Should be 20+

# Check pip
pip --version
```

---

## Service Dependencies

### Required Services (Docker)

| Service | Image | Port | Purpose | Health |
|---------|-------|------|---------|--------|
| PostgreSQL | postgres:15-alpine | 5432 | Primary database | ✅ |
| Redis | redis:7-alpine | 6379 | Cache & sessions | ✅ |
| Qdrant | qdrant/qdrant:latest | 6333 | Vector search | ⚠️ |

### Optional Services

| Service | Port | Purpose |
|---------|------|---------|
| Neo4j | 7474, 7687 | Graph database (semantic memory) |
| Ollama | 11434 | Local LLM inference |

---

## Setup Procedures

### Step 1: Docker Services

#### Start Docker Dependencies

```bash
# From project root
cd /Users/fulvio/coding/jai

# Start only dependencies (PostgreSQL, Redis, Qdrant)
docker compose -f docker-compose.dev.yml up -d

# Verify services are running
docker compose -f docker-compose.dev.yml ps
```

#### Expected Output

```
NAME          STATUS                    PORTS
jai-postgres  Up (healthy)              0.0.0.0:5432->5432/tcp
jai-redis     Up (healthy)             0.0.0.0:6379->6379/tcp
jai-qdrant    Up (health: starting)    0.0.0.0:6333->6333/tcp
```

#### Wait for Services

```bash
# Wait for PostgreSQL
until docker exec jai-postgres pg_isready -U jai_user; do
  echo "Waiting for PostgreSQL..."
  sleep 1
done

# Wait for Redis
until docker exec jai-redis redis-cli ping | grep -q PONG; do
  echo "Waiting for Redis..."
  sleep 1
done

# Wait for Qdrant (may take 30-60 seconds)
sleep 30
curl -s http://localhost:6333/collections > /dev/null && echo "Qdrant ready"
```

---

### Step 2: Environment Configuration

#### Environment Files Location

```
jai/
├── backend/
│   └── .env                    # Backend environment variables
├── frontend/
│   └── .env.local             # Frontend environment variables
└── .env.development          # Template (DO NOT EDIT)
```

#### Backend .env Configuration

The backend expects environment variables in `backend/.env`. Key settings:

```bash
# Database (Docker)
DB_HOST=localhost
DB_PORT=5432
DB_USER=jai_user
DB_PASSWORD=jai_password
DB_NAME=me4brain
DATABASE_URL=postgresql://jai_user:jai_password@localhost:5432/me4brain

# Redis (Docker)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_URL=redis://localhost:6379/0

# Qdrant (Docker)
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_URL=http://localhost:6333

# Backend Server
PYTHONUNBUFFERED=1
ENVIRONMENT=development
BACKEND_HOST=localhost
BACKEND_PORT=8000
BACKEND_DEBUG=true

# LLM Configuration (Local)
LLM_PRIMARY_MODEL=qwen3.5:9b
LLM_ROUTING_MODEL=qwen3.5:9b
LLM_LOCAL_ONLY=true
USE_LOCAL_TOOL_CALLING=true
LLM_ALLOW_CLOUD_FALLBACK=false

# Ollama (if using local models)
OLLAMA_BASE_URL=http://localhost:11434/v1
OLLAMA_MODEL=qwen3.5:9b

# Feature Flags
ENABLE_HYBRID_ROUTING=true
ENABLE_CACHING=true
ENABLE_VECTOR_SEARCH=true
```

#### Frontend .env.local Configuration

```bash
# API Connection
NEXT_PUBLIC_API_URL=http://localhost:8000

# Debug
NEXT_PUBLIC_DEBUG=true
NODE_ENV=development
```

---

### Step 3: Backend Setup

#### Create Virtual Environment

```bash
cd /Users/fulvio/coding/jai/backend

# Create venv
python -m venv venv

# Activate venv
source venv/bin/activate

# Verify activation
which python  # Should point to venv/bin/python
```

#### Install Dependencies

```bash
# Install the package with all dependencies
pip install -e .

# Or use uv (faster)
uv sync
uv sync --extra dev  # Include dev dependencies
```

#### Verify Installation

```bash
# Check installed packages
pip list | grep -E "fastapi|uvicorn|redis|qdrant"

# Should show:
# fastapi
# uvicorn
# redis
# qdrant-client
```

---

### Step 4: Frontend Setup

#### Install Dependencies

```bash
cd /Users/fulvio/coding/jai/frontend

# Install all workspace dependencies
npm install

# This installs dependencies for:
# - packages/gateway
# - packages/me4brain-client
# - packages/shared
# - apps/frontend
```

#### Verify Installation

```bash
# Check installed packages
ls node_modules | head -20

# Check workspaces
npm run --workspaces --if-present ls 2>/dev/null | head -30
```

---

## Startup Procedures

### Starting Backend

#### Method 1: Using FastAPI CLI (Recommended)

```bash
cd /Users/fulvio/coding/jai/backend
source venv/bin/activate

# Start with hot reload
fastapi run --host 0.0.0.0 --port 8000 --reload

# Or using uvicorn directly
uvicorn me4brain.api.main:app --host 0.0.0.0 --port 8000 --reload
```

#### Method 2: Using Python Module

```bash
cd /Users/fulvio/coding/jai/backend
source venv/bin/activate

python -m me4brain.api
```

#### Expected Backend Output

```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000
```

---

### Starting Frontend

#### Method 1: Using Turbo (Recommended)

```bash
cd /Users/fulvio/coding/jai/frontend

# Start all workspaces (gateway, client, frontend)
npm run dev
```

#### Method 2: Individual Services

```bash
cd /Users/fulvio/coding/jai/frontend

# Terminal 1: Start Gateway
cd packages/gateway
npm run dev

# Terminal 2: Start Frontend
cd apps/frontend
npm run dev
```

#### Expected Frontend Output

```
▲ Next.js 15.x.x
- Local:        http://localhost:3000
- Ready in XXXms
```

---

### ⚠️ CRITICAL: Gateway ME4BRAIN_URL Configuration

The Gateway **must** know where the backend (Me4BrAIn) is running. This is configured via the `ME4BRAIN_URL` environment variable.

#### Default Ports

| Service | Port | URL |
|---------|------|-----|
| **Backend (Me4BrAIn)** | 8000 | `http://localhost:8000` |
| **Gateway** | 3030 | `http://localhost:3030` |
| **Frontend (Next.js)** | 3000 | `http://localhost:3000` |

#### Starting Gateway with Correct Backend URL

```bash
# From project root (or frontend/ directory)
cd /Users/fulvio/coding/jai

# Method 1: Set env var inline (recommended for development)
ME4BRAIN_URL=http://localhost:8000 npm run dev --filter=gateway

# Method 2: Create .env file in frontend/ directory
echo "ME4BRAIN_URL=http://localhost:8000" > frontend/.env
cd frontend && npm run dev --filter=gateway

# Method 3: Using the default .env file (must exist at frontend/.env)
cd frontend/packages/gateway && npm run dev
# (assumes .env in frontend/ is already configured)
```

#### Common Issue: 404 Not Found from Gateway

**Symptom**: Gateway returns `{"detail":"Not Found"}` when calling backend endpoints (e.g., `/api/config/llm/reset-config`).

**Cause**: Gateway is configured with wrong `ME4BRAIN_URL` pointing to an old backend instance or wrong port.

**Diagnosis**:
```bash
# Check what's running on port 8089 (old PersAn port)
lsof -i :8089

# Check what's running on port 8000 (JAI backend port)
lsof -i :8000

# Test backend directly
curl http://localhost:8000/v1/config/llm/current

# Test through gateway (if gateway is on 3030)
curl http://localhost:3030/api/config/llm/current
```

**Fix**:
1. Kill any old processes on port 8089: `kill $(lsof -t -i :8089)`
2. Ensure JAI backend is running on port 8000
3. Restart gateway with correct `ME4BRAIN_URL=http://localhost:8000`

#### Verify Gateway Configuration

```bash
# Check what URL gateway is using (in gateway logs on startup)
# You should see: "📡 Me4BrAIn URL: http://localhost:8000"

# Test the reset endpoint through gateway
curl -X POST http://localhost:3030/api/config/llm/reset-config
# Should return: {"status":"reset","message":"Configurazione ripristinata ai valori predefiniti",...}
```

---

### Using Helper Scripts

The project includes convenience scripts:

#### Start All Services

```bash
cd /Users/fulvio/coding/jai

# Terminal 1: Docker services (already running)
docker compose -f docker-compose.dev.yml start

# Terminal 2: Backend
./dev-backend.sh

# Terminal 3: Frontend
./dev-frontend.sh
```

#### Quick Status Check

```bash
# Check Docker services
docker compose -f docker-compose.dev.yml ps

# Check running ports
lsof -i :8000 -i :3000 -i :5432 -i :6379 -i :6333
```

---

## Health Verification

### Backend Health

```bash
# Liveness probe
curl http://localhost:8000/health/live

# Readiness probe
curl http://localhost:8000/health/ready

# Full health with components
curl http://localhost:8000/health
```

#### Expected Response

```json
{
  "status": "healthy",
  "components": {
    "database": "connected",
    "redis": "connected",
    "qdrant": "connected"
  }
}
```

### Frontend Health

```bash
# Check if frontend is responding
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000
# Expected: 200
```

### API Documentation

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

---

## Service Ports

| Service | Port | URL | Status Check |
|---------|------|-----|--------------|
| Frontend | 3000 | http://localhost:3000 | `curl localhost:3000` |
| Backend API | 8000 | http://localhost:8000 | `curl localhost:8000/docs` |
| PostgreSQL | 5432 | localhost:5432 | `pg_isready` |
| Redis | 6379 | localhost:6379 | `redis-cli ping` |
| Qdrant | 6333 | localhost:6333 | `curl localhost:6333/collections` |
| Qdrant UI | 6333 | http://localhost:6333/dashboard | Browser |
| Neo4j (opt) | 7474 | http://localhost:7474 | Browser |

---

## Troubleshooting

### Issue: Backend Won't Start

**Symptoms**: `Connection refused` or import errors

**Solutions**:

```bash
# 1. Verify venv is activated
source venv/bin/activate

# 2. Check dependencies installed
pip list

# 3. Verify environment
echo $DATABASE_URL

# 4. Check PostgreSQL is running
docker exec jai-postgres pg_isready -U jai_user
```

### Issue: 401 Unauthorized Errors

**Symptoms**: API calls return 401 Unauthorized

**Cause**: `ME4BRAIN_DEBUG` not set

**Solution**:

```bash
# In backend/.env, ensure:
ME4BRAIN_DEBUG=true
# OR
ME4BRAIN_DEV_MODE=true

# Restart backend
```

### Issue: Qdrant Collections Not Found

**Symptoms**: Vector search returns empty results

**Solution**:

```bash
# Check Qdrant is running
curl http://localhost:6333/collections

# List collections
curl http://localhost:6333/collections/me4brain_capabilities/points/count

# Recreate if needed (WARNING: data loss)
curl -X DELETE http://localhost:6333/collections/me4brain_capabilities
```

### Issue: Redis Connection Refused

**Symptoms**: Session errors, cache failures

**Solution**:

```bash
# Check Redis is running
docker exec jai-redis redis-cli ping

# If not running, restart
docker restart jai-redis

# Verify local Redis (if running locally, not in Docker)
redis-cli ping
```

### Issue: Frontend 500 Errors

**Symptoms**: Pages load but show 500 errors

**Solutions**:

```bash
# 1. Check backend is running
curl http://localhost:8000/health

# 2. Verify API URL in frontend
grep NEXT_PUBLIC_API_URL frontend/.env.local

# 3. Check CORS settings in backend
grep CORS_ORIGINS backend/.env
```

### Issue: Gateway Returns 404 When Calling Backend

**Symptoms**: API calls through gateway (e.g., `/api/config/llm/reset-config`) return `{"detail":"Not Found"}` but calling backend directly works.

**Diagnosis**:
```bash
# Test backend directly - should work
curl http://localhost:8000/v1/config/llm/current

# Test through gateway - returns 404
curl http://localhost:3030/api/config/llm/current

# Check what ports are in use
lsof -i :8000 -i :8089 | grep LISTEN
```

**Cause**: Gateway has `ME4BRAIN_URL` pointing to wrong port (e.g., old PersAn on 8089 instead of JAI backend on 8000).

**Solution**:
```bash
# 1. Kill old process on 8089
kill $(lsof -t -i :8089)

# 2. Verify backend is on 8000
curl http://localhost:8000/health

# 3. Restart gateway with correct URL
ME4BRAIN_URL=http://localhost:8000 npm run dev --filter=gateway
```

---

### Issue: Hot Reload Not Working

**Symptoms**: Changes don't reflect

**Solutions**:

```bash
# Backend: Restart uvicorn (Ctrl+C then restart)

# Frontend: Clear .next cache
cd frontend
rm -rf apps/frontend/.next
npm run dev

# If still not working, full clean
npm run clean
npm install
npm run dev
```

---

## Known Issues & Fixes

### Neo4j Health Check Shows "Not Initialized"

**Issue**: Health check reports `Neo4j driver not initialized` even though Neo4j is running.

**Cause**: Bug in health check - it creates a new SemanticMemory instance instead of using the singleton.

**Status**: This is a **cosmetic issue only**. Neo4j is properly initialized and functional. The system works correctly despite the health check showing an error.

**Workaround**: Ignore the neo4j status in health check. The actual functionality works.

### Ollama Model Not Found

**Issue**: Backend logs show `startup_llm_check_failed: HTTP 404 - required_model: qwen3.5:9b`

**Cause**: Ollama is not running or the model is not downloaded.

**Solution**: 
```bash
# Install Ollama and pull the model
brew install ollama
ollama pull qwen3.5:9b

# Or use LM Studio instead
# Update .env with LM Studio URL
```

### Frontend .env Location

**Issue**: Gateway fails with `../../.env: not found`

**Cause**: The gateway package.json expects `.env` in the `frontend/` directory, not project root.

**Fix**: Copy `.env.development` to both locations:
```bash
cp .env.development frontend/.env
cp .env.development .env
```

### LOG_LEVEL Case Sensitivity

**Issue**: Gateway fails with `Invalid enum value. Expected 'debug' | 'info' | 'warn' | 'error', received 'DEBUG'`

**Cause**: LOG_LEVEL must be lowercase in gateway config.

**Fix**: Ensure `.env` has `LOG_LEVEL=debug` (not `LOG_LEVEL=DEBUG`).

---

## Daily Development Workflow

### Morning Start

```bash
# 1. Start Docker services
cd /Users/fulvio/coding/jai
docker compose -f docker-compose.dev.yml start

# 2. Wait for services
sleep 10

# 3. Start backend
cd backend
source venv/bin/activate
fastapi dev --port 8000

# 4. In new terminal, start frontend
cd frontend
npm run dev
```

### Verify Everything Works

```bash
# Test backend
curl http://localhost:8000/docs > /dev/null && echo "✅ Backend OK"

# Test frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 | \
  grep -q "200" && echo "✅ Frontend OK"

# Test API
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"test"}]}' \
  2>/dev/null | grep -q "content" && echo "✅ API OK"
```

### Evening Shutdown

```bash
# Stop backend (Ctrl+C in terminal)

# Stop frontend (Ctrl+C in terminal)

# Docker services can keep running overnight
# OR stop them:
docker compose -f docker-compose.dev.yml stop
```

---

## File Structure Reference

```
jai/
├── backend/
│   ├── src/me4brain/
│   │   ├── api/              # FastAPI routes
│   │   ├── config/           # Settings
│   │   ├── llm/              # LLM providers
│   │   ├── memory/           # Memory systems
│   │   └── ...
│   ├── tests/
│   ├── .env                  # Environment variables
│   ├── pyproject.toml
│   └── venv/                 # Virtual environment (create with: python -m venv venv)
│
├── frontend/
│   ├── apps/frontend/        # Next.js UI
│   ├── packages/
│   │   ├── gateway/          # Fastify gateway
│   │   ├── shared/           # Shared types
│   │   └── me4brain-client/  # API client
│   ├── .env.local
│   └── package.json
│
├── docker-compose.dev.yml    # Docker dependencies only
├── docker-compose.yml        # Full stack
├── dev-setup.sh             # Initial setup
├── dev-backend.sh           # Backend startup
└── dev-frontend.sh          # Frontend startup
```

---

## Additional Resources

- [HYBRID_DEVELOPMENT.md](./HYBRID_DEVELOPMENT.md) - Detailed development guide
- [JAI_SETUP_GUIDE.md](./JAI_SETUP_GUIDE.md) - Full setup documentation
- [PHASE_10_DEPLOYMENT_GUIDE.md](./.workflow/PHASE_10_DEPLOYMENT_GUIDE.md) - Production deployment

---

**Last Updated**: 2026-03-23
**Maintained By**: JAI Development Team
