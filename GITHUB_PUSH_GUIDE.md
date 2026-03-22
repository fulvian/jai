# JAI GitHub Push Guide

## ✅ Status: Ready for Push

Your JAI monorepo is now fully prepared for GitHub:

```
📊 Size: 968 MB (models excluded)
📝 Files: 2,580 code/config files
✓ Commits: 2 (initial + models setup)
✓ Tests: 143 backend tests ready
✓ CI/CD: GitHub Actions workflow configured
```

## Step 1: Create GitHub Repository

1. Go to https://github.com/new
2. Fill in:
   - **Repository name**: `jai`
   - **Description**: "Journeys with AI - Unified Me4BrAIn + PersAn monorepo"
   - **Public**: ✓ (checked)
   - **Initialize with**: None (leave unchecked)
3. Click **"Create repository"**

**Expected URL**: https://github.com/fulvian/jai

## Step 2: Configure Remote & Push

Run these commands from `/Users/fulvio/coding/jai/`:

```bash
# Add remote origin
git remote add origin https://github.com/fulvian/jai.git

# Ensure we're on main branch
git branch -M main

# Push to GitHub
git push -u origin main
```

**First push** may take 3-5 minutes (968 MB transfer).

## Step 3: Verify on GitHub

After push completes:

1. Check **https://github.com/fulvian/jai**
2. Verify all files are present:
   - ✓ `backend/` directory with Phase A-F code
   - ✓ `frontend/` directory with React/Next.js
   - ✓ `docker-compose.yml`
   - ✓ `.github/workflows/ci.yml`
   - ✓ `MODELS.md` with setup guide

3. GitHub Actions should trigger automatically
   - Check **Actions** tab for CI/CD status
   - Backend pytest should run (143 tests)
   - Frontend npm build should run

## Step 4: Monitor CI/CD

Navigate to **Actions** tab and watch:

```
✓ Linting (ruff)
✓ Backend tests (pytest)
✓ Frontend build (npm)
✓ Docker builds
```

Expected total time: 10-15 minutes

## Troubleshooting

### Push fails with "fatal: remote origin already exists"

```bash
git remote remove origin
# Then re-run the git remote add command
```

### Push times out

```bash
# Increase git buffer
git config http.postBuffer 524288000

# Try push again
git push -u origin main
```

### CI/CD pipeline fails

Check the specific action output:

1. Click the failed job in Actions tab
2. Look for the specific step that failed
3. Common issues:
   - Python version mismatch → update `.github/workflows/ci.yml`
   - Missing dependencies → check `pyproject.toml` or `package.json`
   - Model download timeout → models are optional, tests should still pass

## Post-Push Steps (Optional)

### 1. Add Branch Protection

```bash
# Require PRs before merging to main
# Settings → Branches → Add rule for 'main'
```

### 2. Enable GitHub Pages

```bash
# Settings → Pages → Source: /docs directory
# Serves documentation from root `docs/` folder
```

### 3. Add Topics

On GitHub repository page:
- Add topics: `ai`, `llm`, `hybrid-routing`, `conversational-ai`

### 4. Update Pinned Repositories

Pin `jai` to your profile as featured project.

## Next Steps After GitHub

### Local Development

```bash
# Clone for development
git clone https://github.com/fulvian/jai.git
cd jai

# Set up local environment
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# Start with Docker Compose
docker-compose up -d
```

### Model Downloads

First time running will download models (~2.2GB):

```bash
# Models download automatically on container start
docker-compose logs backend | grep "Downloading"

# Or manually
cd backend
python scripts/download_models.py
```

### Running Tests Locally

```bash
# Backend tests
cd backend
pytest tests/ -v --cov=src/me4brain

# Frontend tests
cd frontend
npm test
```

## Project Links

- **Repository**: https://github.com/fulvian/jai
- **Issues**: https://github.com/fulvian/jai/issues
- **Discussions**: https://github.com/fulvian/jai/discussions (enable in Settings)
- **CI/CD**: https://github.com/fulvian/jai/actions

## Original Sources (Reference Only)

These remain on your local machine, unmodified:

- Me4BrAIn: `/Users/fulvio/coding/Me4BrAIn` (branch: `local_llm`)
- PersAn: `/Users/fulvio/coding/PersAn` (branch: `main`)

JAI is a **standalone snapshot** and independent fork.

---

**Ready to push?** Execute the commands in **Step 2** above.
