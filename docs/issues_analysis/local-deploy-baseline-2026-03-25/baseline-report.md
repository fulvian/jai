# Local Deploy Baseline Report - 2026-03-25

## System Information

### Host
- OS: Ubuntu 24.04.4 LTS
- Kernel: 6.17
- User: fulvio
- Groups: fulvio adm cdrom sudo dip video plugdev users render lpadmin

### Toolchain Versions
- Python: 3.12.3
- UV: 0.10.12
- Node: v20.18.0
- npm: 10.8.2
- Docker: 28.2.2

### GPU (ROCm)
- GPU Detected: AMD Ryzen AI 9 HX 370 w/ Radeon 890M (gfx1150)
- VRAM Usage: 94% (alta occupazione)
- GPU Temperature: 39°C
- GPU Power: 39W
- ROCm Runtime: Active

### Port Status
No listeners on: 3020, 3030, 8000, 8089, 5432, 6379, 6333, 7687

---

## Issues Found

### Docker Access
- User `fulvio` is NOT in the `docker` group
- `docker compose` plugin may not be available
- Docker socket: `/var/run/docker.sock` root:docker

### Environment Variables Mismatch
Settings.py expects (`ME4BTHON_*` prefix):
- `ME4BRAIN_PORT` (default 8089)
- `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, etc.
- `REDIS_HOST`, `REDIS_PORT`
- `QDRANT_HOST`, `QDRANT_HTTP_PORT`

But .env files use:
- `BACKEND_PORT=8000`
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`

### Gateway 8089 References
Files with hardcoded 8089 fallback:
1. `frontend/packages/gateway/src/services/session_manager_instance.ts:14`
2. `frontend/packages/gateway/src/routes/config.ts:3`
3. `frontend/packages/gateway/src/routes/providers.ts:3`
4. `frontend/packages/gateway/src/services/graph_session_service.ts:85`
5. `frontend/packages/gateway/src/services/title_generator.ts:9`

### Backend Dependencies
- `backend/pyproject.toml`: No uv.lock file present
- `torch>=2.5` could resolve to CUDA version unintentionally
- `sentence-transformers>=3` depends on torch

---

## Plan Progress

- [ ] Phase 0: Safety baseline (CURRENT)
- [ ] Phase 1: Docker remediation
- [ ] Phase 2: UV + torch deterministic dependencies
- [ ] Phase 3: Environment configuration normalization
- [ ] Phase 4: Data infrastructure startup
- [ ] Phase 5: Backend startup with verification
- [ ] Phase 6: Gateway/Frontend alignment
- [ ] Phase 7: End-to-end verification
- [ ] Phase 8: Hardening and runbook
