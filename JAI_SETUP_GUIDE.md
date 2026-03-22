# JAI Monorepo - Setup Instructions

**Status**: Monorepo structure ready. Files staged locally but require GitHub setup.

## What Was Created

Located at: `/Users/fulvio/coding/jai/`

### Directory Structure
```
jai/
├── backend/              (Me4BrAIn llm_local content - 4.2GB)
│   ├── src/
│   ├── tests/
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── ...
├── frontend/             (PersAn content - 4.8GB)
│   ├── frontend/
│   ├── packages/
│   ├── package.json
│   ├── docker/
│   └── ...
├── docs/                 (Shared documentation)
├── .github/workflows/
│   └── ci.yml           (Test & Build CI/CD pipeline)
├── .gitignore           (Monorepo-wide ignore rules)
├── docker-compose.yml   (Full stack local dev environment)
└── README.md            (Quick start guide)
```

### Docker Compose Services (Ready to Use)
- **Backend**: FastAPI on port 8000
- **Frontend**: React/Next.js on port 3000
- **PostgreSQL**: Database on port 5432
- **Redis**: Cache on port 6379
- **Qdrant**: Vector DB on port 6333

### CI/CD Pipeline (GitHub Actions)
- Python 3.10 + 3.11 testing
- Node.js 18 testing
- Docker image builds
- Automated linting + coverage

## Next Steps

### Option 1: Create GitHub Repository via Web UI (Recommended)

1. Go to https://github.com/new
2. Fill in:
   - **Repository name**: `jai`
   - **Description**: "JAI - Journeys with AI: Unified Me4BrAIn + PersAn monorepo"
   - **Public**: ✓ Checked
   - **Initialize with README**: ✗ Unchecked (we have one)
3. Click "Create repository"

4. Then push locally:
```bash
cd /Users/fulvio/coding/jai
git init
git config user.email "fulvio@example.com"
git config user.name "Fulvio"

# Add remote
git remote add origin https://github.com/fulvian/jai.git

# Stage and commit (may take 5-10 minutes due to ~9GB of data)
git add .
git commit -m "Initial commit: JAI monorepo with Me4BrAIn + PersAn"

# Push to GitHub
git branch -M main
git push -u origin main
```

**⚠️ Warning**: This will push ~9GB to GitHub. May take 10-20 minutes depending on internet.

### Option 2: Use Git LFS for Large Files (Better for Large Data)

If you have many large files:

```bash
cd /Users/fulvio/coding/jai
git lfs install
git lfs track "*.pth" "*.bin" "*.pkl"
git add .gitattributes
git add .
git commit -m "Initial commit with LFS"
git push -u origin main
```

### Option 3: Shallow Clone (Smallest Repository)

```bash
# Create lightweight repo for GitHub
mkdir jai-minimal
cd jai-minimal
git init

# Copy only essential files (skip backend/frontend node_modules, venv, etc)
cp -r ../jai/docs .
cp ../jai/README.md .
cp ../jai/docker-compose.yml .
cp ../jai/.gitignore .
cp -r ../jai/.github .

# Then push as above
```

## Current Status

| Item | Status |
|------|--------|
| ✅ Monorepo structure | Created locally |
| ✅ Backend integration | Me4BrAIn (llm_local) copied |
| ✅ Frontend integration | PersAn copied |
| ✅ docker-compose.yml | Ready (services: backend, frontend, db, cache, vector) |
| ✅ CI/CD workflow | GitHub Actions configured |
| ✅ Documentation | README.md + setup guides |
| ⏳ GitHub repository | Awaiting user creation |
| ⏳ Initial push | Ready to execute once repo exists |

## Testing Monorepo Locally

Before pushing to GitHub, test everything locally:

```bash
cd /Users/fulvio/coding/jai

# Test structure
ls -la backend/{src,tests,pyproject.toml}
ls -la frontend/{frontend,packages,package.json}

# Test Docker Compose (optional - full stack)
docker-compose up -d
docker-compose logs -f
docker-compose down

# Test backend tests
cd backend
pytest tests/ --co  # Collect tests without running
cd ..

# Test frontend build
cd frontend
npm install
npm run build
cd ..
```

## Important Notes

1. **Master Branch Protection**: Original Me4BrAIn `master` branch remains untouched
2. **llm_local Branch**: Lives in `/Users/fulvio/coding/Me4BrAIn` on branch `local_llm`
3. **PersAn Original**: Lives in `/Users/fulvio/coding/PersAn` (unchanged)
4. **JAI is Independent**: This monorepo is a unified snapshot, not linked to originals

## Questions?

- Backend questions: See `backend/README.md`
- Frontend questions: See `frontend/README.md`
- Architecture questions: See `docs/reports/`

---

**Created**: 2026-03-22  
**Repository Path**: `/Users/fulvio/coding/jai`  
**GitHub URL**: https://github.com/fulvian/jai (once created)
