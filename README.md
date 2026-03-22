# JAI - Journeys with AI

**JAI** è un monorepo che unifica due sottoprogetti:
1. **Backend**: Me4BrAIn (hybrid routing LLM engine)
2. **Frontend**: PersAn (conversational AI interface)

## Struttura del Progetto

```
jai/
├── backend/          # Me4BrAIn llm_local branch
│   ├── src/
│   ├── tests/
│   ├── pyproject.toml
│   └── ...
├── frontend/         # PersAn frontend
│   ├── frontend/     # React/Next.js app
│   ├── packages/     # Gateway, shared, client
│   ├── package.json
│   └── ...
├── docs/            # Documentazione condivisa
└── docker-compose.yml
```

## Quick Start

### Prerequisiti
- Python 3.10+ (backend)
- Node.js 18+ (frontend)
- Docker & Docker Compose

### Avviamento Locale

```bash
# Clona e accedi al repo
cd jai

# Opzione 1: Docker Compose (consigliato)
docker-compose up

# Opzione 2: Manuale
# Terminal 1 - Backend
cd backend
python -m venv venv
source venv/bin/activate
pip install -e .
python -m me4brain.api

# Terminal 2 - Frontend
cd frontend
npm install
npm run dev
```

**Endpoint**:
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`

## Configurazione

### Backend (.env)
```bash
cd backend
cp .env.example .env
# Modifica API keys, LLM settings, etc.
```

### Frontend (.env)
```bash
cd frontend
cp .env.example .env.local
# Modifica API endpoints, AI settings
```

## Testing

### Backend (143 unit + integration + e2e tests)
```bash
cd backend
pytest tests/ -v --cov
```

### Frontend
```bash
cd frontend
npm test
```

## Documentazione

- **Backend**: Vedi `backend/README.md` per dettagli su hybrid routing, domain classifier, odds API
- **Frontend**: Vedi `frontend/README.md` per architettura React, UI components, WebSocket setup
- **Design Docs**: Vedi `docs/` per diagrammi architetturali

## Sviluppo

### Commit Workflow
```bash
# Backend changes
cd backend
git add .
git commit -m "feat: [domain] description"

# Frontend changes
cd frontend
git add .
git commit -m "feat: [component] description"

# Root monorepo changes
git add .
git commit -m "chore: [monorepo] description"
```

### Branch Strategy
- `main`: Production-ready code (both backend + frontend)
- `develop`: Integration branch
- `feature/*`: Feature branches

## Deployment

Vedi `docker-compose.yml` per production stack (Nginx reverse proxy, Redis cache, PostgreSQL).

## Support

Problemi o domande? Leggi:
- Backend debugging: `docs/reports/NBA_HYBRID_ROUTING_DEEP_DEBUG_PLAN_*.md`
- Frontend issues: `frontend/docs/`

---

**Repository**: https://github.com/fulvian/jai  
**Last Updated**: 2026-03-22
