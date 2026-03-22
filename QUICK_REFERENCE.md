# JAI Development Quick Reference Card

## 🚀 Five-Minute Setup

```bash
# Terminal 1: Setup + Backend
./dev-setup.sh                    # Start Docker services
./copy-large-files.sh all         # Optional: Copy 9.8GB (15-30 min)
./dev-backend.sh                  # Start FastAPI + auto-reload

# Terminal 2: Frontend  
./dev-frontend.sh                 # Start Next.js + auto-reload

# Browser
open http://localhost:3000        # App is ready!
```

---

## 📌 Essential Commands

| Task | Command |
|------|---------|
| **Copy files (optional)** | `./copy-large-files.sh all` |
| **View Docker status** | `./dev-utils.sh status` |
| **View logs** | `./dev-utils.sh logs` |
| **Connect to DB** | `./dev-utils.sh db-shell` |
| **Stop services** | `./dev-utils.sh stop` |
| **Backend tests** | `./dev-backend.sh --test` |
| **Coverage report** | `./dev-backend.sh --coverage` |
| **Frontend tests** | `./dev-frontend.sh --test` |
| **Build frontend** | `./dev-frontend.sh --build` |

---

## 🌐 Endpoints

| Service | URL | Purpose |
|---------|-----|---------|
| Frontend | `http://localhost:3000` | React/Next.js app |
| Backend API | `http://localhost:8000` | FastAPI server |
| API Docs | `http://localhost:8000/docs` | Swagger docs |
| PostgreSQL | `localhost:5432` | Database |
| Redis | `localhost:6379` | Cache |
| Qdrant | `http://localhost:6333` | Vector DB |

---

## 🔧 Copy Large Files Options

```bash
./copy-large-files.sh all           # Copy everything (9.8GB)
./copy-large-files.sh backend       # Backend only (4.9GB)
./copy-large-files.sh frontend      # Frontend only (4.9GB)
./copy-large-files.sh models-only   # Just ML models (8.6GB)
./copy-large-files.sh data-only     # Data + dependencies (1.2GB)
./copy-large-files.sh -d all        # Dry-run (see what would copy)
./copy-large-files.sh -h            # Show help
```

**Why copy?** Copying from local repos is 15-30x faster than re-downloading models.

---

## 🐛 Troubleshooting

### Backend won't start
```bash
./dev-utils.sh status              # Check Docker services
./dev-utils.sh logs                # View service logs
./dev-utils.sh restart             # Restart services
```

### Port already in use
```bash
lsof -i :8000                       # Find process on port 8000
kill -9 <PID>                       # Kill it
```

### Models missing
```bash
ls -lh backend/models/              # Check if models exist
./copy-large-files.sh backend       # Copy from source
```

### Fresh start (careful: data loss!)
```bash
./dev-utils.sh clean
./dev-setup.sh
```

---

## 📁 Project Structure

```
jai/
├── backend/                  # FastAPI + Me4BrAIn engine
│   ├── src/me4brain/        # Source code
│   ├── tests/               # 143 tests
│   └── models/              # ML models (copy via script)
├── frontend/                 # React/Next.js + PersAn UI
│   ├── frontend/            # UI components
│   ├── packages/            # Shared packages
│   └── node_modules/        # Dependencies (copy via script)
├── docker-compose.dev.yml   # Dependencies-only stack
├── dev-*.sh                 # Development scripts
└── HYBRID_DEVELOPMENT.md    # Full guide
```

---

## 💡 Performance (Hybrid vs Docker vs Native)

| Metric | Docker | Hybrid ✅ | Native |
|--------|--------|----------|--------|
| Hot Reload | 2-3s | <100ms | <100ms |
| RAM | 6-8GB | 3-4GB | 2GB |
| CPU | 15-25% | 5-10% | <5% |
| Production Parity | ✅ | ✅ | ⚠️ |

**Hybrid = Docker services + native code = best of both worlds**

---

## 📚 Documentation

- **Detailed Dev Guide**: [HYBRID_DEVELOPMENT.md](./HYBRID_DEVELOPMENT.md)
- **Copy Large Files**: [COPY_LARGE_FILES.md](./COPY_LARGE_FILES.md)
- **Full Architecture**: [JAI_SETUP_GUIDE.md](./JAI_SETUP_GUIDE.md)
- **Deployment**: [GITHUB_PUSH_GUIDE.md](./GITHUB_PUSH_GUIDE.md)

---

## 🔗 Links

- **Repository**: https://github.com/fulvian/jai
- **Backend Docs**: `backend/README.md`
- **Frontend Docs**: `frontend/README.md`

---

**Last Updated**: 2026-03-22 | **Hybrid Mode** is the recommended way to develop
