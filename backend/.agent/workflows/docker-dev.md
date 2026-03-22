---
description: How to manage Docker containers for Me4BrAIn development
---

> **NOTE**: For full development stack startup (Me4BrAIn + PersAn), use `/dev-startup` workflow instead.
> This file covers Docker infrastructure ONLY (Qdrant, Redis, Neo4j, Postgres).
> Me4BrAIn API runs locally via uvicorn, NOT in Docker.

# Docker Development Workflow for Me4BrAIn

## ⚠️ CRITICAL RULES

1. **ALWAYS use `docker compose`**, NEVER use `docker run` manually
2. **ALWAYS use the full compose file**: `docker/docker-compose.yml`
3. **Service name is `me4brain`**, container name is `me4brain-api`

---

## Quick Reference

### Start Services (with existing image)
```bash
cd /Users/fulvioventura/me4brain
docker compose -f docker/docker-compose.yml up -d me4brain
```

### Rebuild and Restart (after code changes)
// turbo-all
```bash
cd /Users/fulvioventura/me4brain
docker compose -f docker/docker-compose.yml up -d --build me4brain
```

### Rebuild from Scratch (no cache)
```bash
cd /Users/fulvioventura/me4brain
docker compose -f docker/docker-compose.yml build --no-cache me4brain && \
docker compose -f docker/docker-compose.yml up -d me4brain
```

### View Logs
```bash
docker logs me4brain-api -f --tail 100
```

### Stop API Service
```bash
docker compose -f docker/docker-compose.yml stop me4brain
```

### Restart All Services
```bash
docker compose -f docker/docker-compose.yml restart
```

---

## Why docker compose?

The `docker-compose.yml` file contains **environment variable overrides** that map `localhost` URLs to Docker network hostnames:

| .env (localhost) | compose override (Docker) |
| ---------------- | ------------------------- |
| `localhost:7697` | `neo4j:7687`              |
| `localhost:6334` | `qdrant:6334`             |
| `localhost:6389` | `redis:6379`              |
| `localhost:5489` | `postgres:5432`           |

If you use `docker run` manually, these overrides are NOT applied and the container cannot connect to other services.

---

## Common Issues

### "Connection refused" errors
**Cause**: Container started with `docker run` instead of `docker compose`
**Fix**: Stop container and restart via compose:
```bash
docker rm -f me4brain-api
docker compose -f docker/docker-compose.yml up -d me4brain
```

### Code changes not reflected
**Cause**: Docker using cached image
**Fix**: Rebuild with `--build` flag:
```bash
docker compose -f docker/docker-compose.yml up -d --build me4brain
```

### Pydantic validation errors for Settings
**Cause**: Inline comments in `.env` file (e.g., `mps  # comment`)
**Fix**: Remove inline comments, keep only the value
