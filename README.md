# JAI - Journeys with AI

**JAI** è un monorepo che unifica due sottoprogetti:
1. **Backend**: Me4BrAIn (hybrid routing LLM engine)
2. **Frontend**: PersAn (conversational AI interface)

## Struttura del Progetto

```
jai/
├── backend/              # Me4BrAIn LLM engine
│   ├── src/              # Source code
│   ├── tests/            # 143 unit/integration/e2e tests
│   ├── pyproject.toml
│   └── ...
├── frontend/             # PersAn React app
│   ├── frontend/         # React/Next.js UI
│   ├── packages/         # Gateway, shared, client
│   ├── package.json
│   └── ...
├── docker-compose.yml         # Full stack (production)
├── docker-compose.dev.yml     # Dependencies only (development)
├── dev-setup.sh              # Initialize dev environment
├── dev-backend.sh            # Start backend
├── dev-frontend.sh           # Start frontend
├── dev-utils.sh              # Manage Docker services
├── .env.development          # Template for env vars
├── HYBRID_DEVELOPMENT.md     # Development guide ⭐
├── docs/                     # Shared documentation
└── ...
```

## 🚀 Quick Start (Recommended: Hybrid Mode)

**Hybrid Mode** runs dependencies in Docker while you develop natively for faster hot reload and easier debugging.

### Prerequisites
- Docker Desktop (with Docker Compose)
- Python 3.9+
- Node.js 18+

### Setup (5-35 minutes)

```bash
# 1. Initialize Docker services (PostgreSQL, Redis, Qdrant)
./dev-setup.sh

# 2. Copy large pre-built files (models, data, node_modules)
#    This is 15-30x faster than re-downloading!
#    Total: ~9.8GB in 15-30 minutes
#    Options: all | backend | frontend | models-only | data-only
./copy-large-files.sh all

# 3. Start Backend (in Terminal 1)
./dev-backend.sh

# 4. Start Frontend (in Terminal 2)
./dev-frontend.sh

# 5. Access the app
open http://localhost:3000
```

**Note on Step 2**: Copying large files (`copy-large-files.sh`) is optional but **strongly recommended**. It copies pre-built models and dependencies from source repos instead of re-downloading them, saving 20-40 minutes. See [COPY_LARGE_FILES.md](./COPY_LARGE_FILES.md) for details.

**Endpoints**:
- 🎨 Frontend: `http://localhost:3000`
- 🔌 Backend API: `http://localhost:8000`
- 📚 API Docs: `http://localhost:8000/docs`

### Useful Commands

```bash
# View Docker service logs
./dev-utils.sh logs

# Check service health
./dev-utils.sh status

# Connect to PostgreSQL
./dev-utils.sh db-shell

# Stop Docker services
./dev-utils.sh stop
```

See [HYBRID_DEVELOPMENT.md](./HYBRID_DEVELOPMENT.md) for detailed development guide.

---

## Alternative: Full Docker Stack

If you prefer everything in Docker:

```bash
docker-compose up
```

This runs backend + frontend + all dependencies in containers.


## Testing

### Backend (30 unit + integration + e2e tests across Phases 1-5)
```bash
./dev-backend.sh --test
./dev-backend.sh --coverage
```

### Frontend
```bash
./dev-frontend.sh --test
```


## Documentation

### Project Status
- **Latest Phase**: Phase 5 ✅ COMPLETE - Prometheus Metrics & Diagnostics (30/30 tests passing)
- **Implementation Plan**: [.workflow/JAI_IMPLEMENTATION_PLAN.md](./.workflow/JAI_IMPLEMENTATION_PLAN.md) - Phases 1-5 implemented
- **Phase 5 Details**: [.workflow/PHASE_5_STATE.md](./.workflow/PHASE_5_STATE.md) - Monitoring & observability implementation
- **Phase 5 Usage Guide**: [PHASE_5_USAGE_GUIDE.md](./PHASE_5_USAGE_GUIDE.md) - Production monitoring setup

### Roadmap & Future Work
- **Strategic Roadmap (Phases 6-10)**: [.workflow/ROADMAP_PHASES_6_TO_10.md](./.workflow/ROADMAP_PHASES_6_TO_10.md) ⭐ **NEW**
  - Phase 6: Intelligent Query Caching (12-16h)
  - Phase 7: Persistent Conversation Memory (16-20h)
  - Phase 8: Horizontal Scaling & Distributed Tracing (20-24h)
  - Phase 9: Advanced Security & RBAC (16-20h)
  - Phase 10: Production Deployment & Optimization (16-20h)
- **Handoff to minimax 2.7**: [.workflow/HANDOFF_TO_MINIMAX_2.7.md](./.workflow/HANDOFF_TO_MINIMAX_2.7.md) ⭐ **NEW**

### Development & Setup
- **Quick Copy Guide**: [COPY_LARGE_FILES.md](./COPY_LARGE_FILES.md) - Copy models and data (15-30x faster than re-download)
- **Development Setup**: Read [HYBRID_DEVELOPMENT.md](./HYBRID_DEVELOPMENT.md) ⭐ for hybrid dev guide
- **Full Architecture**: [JAI_SETUP_GUIDE.md](./JAI_SETUP_GUIDE.md)
- **GitHub Deployment**: [GITHUB_PUSH_GUIDE.md](./GITHUB_PUSH_GUIDE.md)
- **ML Models**: [MODELS.md](./MODELS.md)
- **Backend Details**: `backend/README.md`
- **Frontend Details**: `frontend/README.md`

## Development Tips

### Performance Comparison

| Aspect | Docker Only | Hybrid (Recommended) | Native Only |
|--------|------------|----------------------|------------|
| **Hot Reload** | 2-3s | <100ms ✅ | <100ms |
| **RAM Usage** | 6-8GB | 3-4GB ✅ | 2GB |
| **CPU Usage** | 15-25% | 5-10% ✅ | <5% |
| **Prod Parity** | Perfect ✅ | Perfect ✅ | Risky ⚠️ |
| **Debugging** | Harder | Easy ✅ | Easy |

### Common Workflows

```bash
# Check what's running
./dev-utils.sh status

# View live logs
./dev-utils.sh logs

# Stop all services
./dev-utils.sh stop

# Restart services
./dev-utils.sh restart

# Clean up everything (careful: data loss!)
./dev-utils.sh clean
```

## Deployment

### Pre-Deployment Checklist

```bash
# 1. Run all tests
./dev-backend.sh --coverage
./dev-frontend.sh --test

# 2. Build frontend
./dev-frontend.sh --build

# 3. Test full stack in Docker
docker-compose down
docker-compose up

# 4. Check for hardcoded values
grep -r "localhost" backend frontend
grep -r "dev_secret_key" .
```

See [GITHUB_PUSH_GUIDE.md](./GITHUB_PUSH_GUIDE.md) for production deployment.

## Troubleshooting

### Redis Connection Issues (ECONNREFUSED)
If sessions disappear after refresh, check Redis port:
```bash
# Verify Redis is running on correct port (6379)
redis-cli ping
lsof -i :6379

# Check gateway REDIS_URL
grep REDIS_URL frontend/.env
```

### Port Already in Use
```bash
# Find process using port 8000
lsof -i :8000

# Kill it
kill -9 <PID>
```

### Docker Issues
```bash
# View logs
./dev-utils.sh logs

# Restart services
./dev-utils.sh restart

# Full reset
./dev-utils.sh clean
./dev-setup.sh
```

### Backend Won't Start
```bash
# Check PostgreSQL is healthy
./dev-utils.sh status

# Connect to DB
./dev-utils.sh db-shell
```

---

**Repository**: https://github.com/fulvian/jai  
**Last Updated**: 2026-03-23  
**Current Phase**: Phase 5 - Prometheus Metrics & Diagnostics ✅ COMPLETE  
**Feature**: Auto Session Title Generation ✅ IMPLEMENTED  
**Test Coverage**: 1151 unit tests + 22 integration tests (all passing)  
**Next Phase**: Phase 6 - Intelligent Query Caching (Ready for implementation)
