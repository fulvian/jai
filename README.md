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

### Setup (5 minutes)

```bash
# 1. Initialize Docker services (PostgreSQL, Redis, Qdrant)
./dev-setup.sh

# 2. Start Backend (in Terminal 1)
./dev-backend.sh

# 3. Start Frontend (in Terminal 2)
./dev-frontend.sh

# 4. Access the app
open http://localhost:3000
```

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

### Backend (143 unit + integration + e2e tests)
```bash
./dev-backend.sh --test
./dev-backend.sh --coverage
```

### Frontend
```bash
./dev-frontend.sh --test
```


## Documentation

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
**Last Updated**: 2026-03-22
