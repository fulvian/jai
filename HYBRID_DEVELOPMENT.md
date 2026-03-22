# JAI Hybrid Development Setup Guide

This guide explains how to set up JAI for optimal development on your Mac using a hybrid approach: Docker for dependencies, native execution for code.

## Why Hybrid?

| Aspect | Docker Full | Hybrid (This) | Native |
|--------|------------|---------------|---------|
| **Performance** | ~0.8-0.9x | Native speed | Native speed |
| **Hot Reload** | 2-3 seconds | <100ms | <100ms |
| **RAM Usage** | 6-8GB | 3-4GB | 2GB |
| **Debugging** | Harder | ✅ Easy | Easy |
| **Prod Parity** | ✅ Perfect | ✅ Perfect | ⚠️ Risky |

## Quick Start (5 minutes)

### 1. Prerequisites

```bash
# Check if Docker is installed
docker --version

# Check if Node.js 18+ is installed
node --version

# Check if Python 3.9+ is installed
python3 --version
```

### 2. Initialize Development Environment

```bash
cd /Users/fulvio/coding/jai

# Start Docker services (PostgreSQL, Redis, Qdrant)
./dev-setup.sh
```

This script:
- ✅ Starts PostgreSQL, Redis, Qdrant in Docker
- ✅ Creates `.env` files for backend and frontend
- ✅ Waits for services to be healthy
- ✅ Prints connection details

### 3. Start Backend (in Terminal 1)

```bash
./dev-backend.sh
```

This will:
- Create Python virtual environment (first run)
- Install dependencies
- Start FastAPI with hot reload on `http://localhost:8000`

API docs available at: `http://localhost:8000/docs`

### 4. Start Frontend (in Terminal 2)

```bash
./dev-frontend.sh
```

This will:
- Install Node dependencies (first run)
- Start Next.js dev server on `http://localhost:3000`

### 5. Verify Everything Works

```bash
# Check backend
curl http://localhost:8000/health

# Check frontend
open http://localhost:3000

# Check Docker services
./dev-utils.sh status
```

---

## Detailed Commands

### Development Scripts

#### `dev-setup.sh`
Initialize Docker dependencies

```bash
# Standard setup
./dev-setup.sh

# Clean and recreate containers
./dev-setup.sh --clean
```

#### `dev-backend.sh`
Manage backend development

```bash
# Start dev server with hot reload
./dev-backend.sh

# Run tests
./dev-backend.sh --test

# Run tests with coverage report
./dev-backend.sh --coverage
```

#### `dev-frontend.sh`
Manage frontend development

```bash
# Start dev server with hot reload
./dev-frontend.sh

# Build for production
./dev-frontend.sh --build

# Run tests
./dev-frontend.sh --test
```

#### `dev-utils.sh`
Manage Docker services

```bash
# View live logs
./dev-utils.sh logs

# View service health
./dev-utils.sh status

# Stop services
./dev-utils.sh stop

# Restart services
./dev-utils.sh restart

# Remove containers and volumes (data loss!)
./dev-utils.sh clean

# Connect to PostgreSQL
./dev-utils.sh db-shell

# Connect to Redis
./dev-utils.sh redis-shell

# Open Qdrant web UI
./dev-utils.sh qdrant-shell
```

---

## Docker Service Details

### PostgreSQL
- **Host**: `localhost`
- **Port**: `5432`
- **User**: `jai_user`
- **Password**: `jai_password`
- **Database**: `me4brain`
- **URL**: `postgresql://jai_user:jai_password@localhost:5432/me4brain`

### Redis
- **Host**: `localhost`
- **Port**: `6379`
- **URL**: `redis://localhost:6379/0`

### Qdrant
- **Host**: `localhost`
- **Port**: `6333`
- **URL**: `http://localhost:6333`
- **Web UI**: `http://localhost:6333/dashboard`

---

## Environment Configuration

Configuration is in `.env.development` template. After running `dev-setup.sh`, it's copied to:
- `backend/.env`
- `frontend/.env.local`

Key variables:
```bash
# Database
DB_HOST=localhost
DB_PORT=5432
DB_USER=jai_user
DB_PASSWORD=jai_password

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333

# LLM
DEFAULT_LLM_PROVIDER=local
OLLAMA_MODEL=mistral
```

---

## Troubleshooting

### Docker Container Won't Start

```bash
# Check Docker is running
docker info

# View container logs
./dev-utils.sh logs

# Restart services
./dev-utils.sh restart

# Clean and start fresh
./dev-utils.sh clean
./dev-setup.sh
```

### Backend Port Already in Use

```bash
# Find what's using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>

# Or use different port
cd backend && fastapi run --port 8001
```

### Frontend Port Already in Use

```bash
# Find what's using port 3000
lsof -i :3000

# Kill the process
kill -9 <PID>

# Or use different port
cd frontend && npm run dev -- --port 3001
```

### Database Connection Error

```bash
# Verify PostgreSQL is healthy
docker-compose -f docker-compose.dev.yml exec postgres pg_isready -U jai_user

# View PostgreSQL logs
docker-compose -f docker-compose.dev.yml logs postgres

# Reset database
docker-compose -f docker-compose.dev.yml exec postgres psql -U jai_user -d me4brain -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
```

### Hot Reload Not Working

```bash
# Backend: FastAPI should auto-reload on file changes
# If not, check file watching limits:
cat /proc/sys/fs/inotify/max_user_watches

# Frontend: Vite should auto-reload
# If not, try clearing cache:
cd frontend && rm -rf .next node_modules && npm install
```

---

## Full Stack Mode (Testing Integration)

If you need to test the full stack in Docker before deployment:

```bash
# Stop native servers (Ctrl+C in their terminals)

# Run everything in Docker
docker-compose up

# Access:
# Frontend: http://localhost:3000
# Backend: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

---

## Performance Tips

### For Faster Development

1. **Use Hybrid Mode** (this setup)
   - Native execution for code you're editing
   - Docker for unchanging dependencies

2. **Optimize VSCode Settings**
   ```json
   {
     "files.watcherExclude": {
       "**/.git/objects/**": true,
       "**/.git/subtree-cache/**": true,
       "**/node_modules/*/**": true,
       "**/.pytest_cache/**": true
     }
   }
   ```

3. **Keep Docker Services Healthy**
   ```bash
   ./dev-utils.sh status
   ```

### For Faster Testing

```bash
# Backend: Run specific test file
pytest tests/test_specific.py -v

# Frontend: Run specific test
npm run test -- specific.test.tsx
```

---

## Production Deployment Checklist

Before deploying:

```bash
# 1. Test with full Docker Compose
docker-compose down
docker-compose up

# 2. Run all tests
./dev-backend.sh --coverage
./dev-frontend.sh --test

# 3. Build frontend
./dev-frontend.sh --build

# 4. Check for hardcoded values
grep -r "localhost" backend frontend
grep -r "dev_secret_key" .

# 5. Verify environment variables
cat .env.development
```

---

## Next Steps

- 📚 Read [JAI_SETUP_GUIDE.md](./JAI_SETUP_GUIDE.md) for detailed architecture
- 🚀 Read [GITHUB_PUSH_GUIDE.md](./GITHUB_PUSH_GUIDE.md) for deployment
- 📋 Check [MODELS.md](./MODELS.md) for LLM model setup

