# JAI - Copia Modelli e File Grandi da Repository Originali

Questa guida ti mostra come copiare modelli pre-scaricati, dati e file grandi dai repository originali (Me4BrAIn e PersAn) invece di scaricarli di nuovo.

## 📊 File Grandi Disponibili

### Backend (Me4BrAIn)
```
/Users/fulvio/coding/Me4BrAIn/
├── models/           4.3GB  (BAAI embeddings, LLM weights)
├── data/             497MB  (test data, fixtures)
├── storage/          227MB  (qdrant indexes, caches)
└── logs/             21MB   (development logs)
```

### Frontend (PersAn)
```
/Users/fulvio/coding/PersAn/
├── models/           4.3GB  (pre-trained embeddings, tokenizers)
├── node_modules/     616MB  (npm dependencies)
└── logs/             4.8MB  (development logs)
```

## ⚡ Quick Copy Script (Recommended)

```bash
cd /Users/fulvio/coding/jai

# Run the copy script
./copy-large-files.sh

# Or copy specific components
./copy-large-files.sh backend    # Copy backend models/data
./copy-large-files.sh frontend   # Copy frontend models/node_modules
./copy-large-files.sh all        # Copy everything
```

## 📋 Manual Copy Instructions

### Option 1: Copy Everything (Fastest)

```bash
cd /Users/fulvio/coding/jai

# Backend models and data
rsync -av --progress \
  /Users/fulvio/coding/Me4BrAIn/models \
  /Users/fulvio/coding/Me4BrAIn/data \
  /Users/fulvio/coding/Me4BrAIn/storage \
  backend/

# Frontend models and node_modules
rsync -av --progress \
  /Users/fulvio/coding/PersAn/models \
  /Users/fulvio/coding/PersAn/node_modules \
  frontend/
```

### Option 2: Copy Selectively

#### Backend Models Only (4.3GB)
```bash
rsync -av --progress \
  /Users/fulvio/coding/Me4BrAIn/models/ \
  /Users/fulvio/coding/jai/backend/models/
```

#### Backend Data Only (497MB)
```bash
rsync -av --progress \
  /Users/fulvio/coding/Me4BrAIn/data/ \
  /Users/fulvio/coding/jai/backend/data/
```

#### Backend Storage Only (227MB)
```bash
rsync -av --progress \
  /Users/fulvio/coding/Me4BrAIn/storage/ \
  /Users/fulvio/coding/jai/backend/storage/
```

#### Frontend Models Only (4.3GB)
```bash
rsync -av --progress \
  /Users/fulvio/coding/PersAn/models/ \
  /Users/fulvio/coding/jai/frontend/models/
```

#### Frontend node_modules Only (616MB)
```bash
rsync -av --progress \
  /Users/fulvio/coding/PersAn/node_modules/ \
  /Users/fulvio/coding/jai/frontend/node_modules/
```

## 🎯 Copy Strategy by Use Case

### Scenario 1: I want to start developing immediately

**Copy only what's essential** (~5GB):
```bash
# Backend: models (4.3GB) for LLM inference
rsync -av --progress \
  /Users/fulvio/coding/Me4BrAIn/models/ \
  /Users/fulvio/coding/jai/backend/models/

# Frontend: node_modules (616MB) to avoid npm install
rsync -av --progress \
  /Users/fulvio/coding/PersAn/node_modules/ \
  /Users/fulvio/coding/jai/frontend/node_modules/

# Then run dev-setup.sh
./dev-setup.sh
./dev-backend.sh
./dev-frontend.sh
```

**Benefits**:
- ✅ No waiting for `npm install` (5-10 minutes)
- ✅ LLM models already available locally
- ✅ Fast hot reload setup
- ⏱️ Total copy time: ~20-30 minutes (depends on disk speed)

### Scenario 2: I want everything (full backup + development)

**Copy absolutely everything** (~13.5GB):
```bash
./copy-large-files.sh all
```

**Benefits**:
- ✅ Identical setup to original repos
- ✅ No network dependency for models/data
- ✅ Ready for offline development
- ⏱️ Total copy time: ~45-60 minutes

### Scenario 3: I'll download models myself

**Don't copy anything, let the system download**:
```bash
# Just initialize Docker
./dev-setup.sh

# Backend will auto-download BAAI embeddings
./dev-backend.sh

# Frontend will auto-download tokenizers
./dev-frontend.sh

# Or manually download models (see MODELS.md)
```

**Pros**: Less disk space used initially  
**Cons**: Slower first startup (10-20 minutes)

## 📁 Directory Structure After Copy

```
jai/
├── backend/
│   ├── src/
│   ├── tests/
│   ├── models/              ← Copied from Me4BrAIn (4.3GB)
│   │   └── models--BAAI--bge-m3/
│   ├── data/                ← Copied from Me4BrAIn (497MB)
│   ├── storage/             ← Copied from Me4BrAIn (227MB)
│   └── ...
├── frontend/
│   ├── frontend/
│   ├── packages/
│   ├── models/              ← Copied from PersAn (4.3GB)
│   ├── node_modules/        ← Copied from PersAn (616MB)
│   └── ...
└── ...
```

## ⚙️ Automated Copy Script

Create `/Users/fulvio/coding/jai/copy-large-files.sh`:

```bash
#!/bin/bash

# JAI - Copy Large Files from Source Repos
# Usage: ./copy-large-files.sh [backend|frontend|all]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ME4BRAIN_SRC="/Users/fulvio/coding/Me4BrAIn"
PERSAN_SRC="/Users/fulvio/coding/PersAn"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     JAI - Copy Large Files from Source Repositories       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function to copy with progress
copy_files() {
    local src="$1"
    local dest="$2"
    local name="$3"
    
    if [ ! -d "$src" ]; then
        echo -e "${RED}✗ Source not found: $src${NC}"
        return 1
    fi
    
    mkdir -p "$dest"
    echo -e "${YELLOW}Copying $name...${NC}"
    rsync -av --progress "$src/" "$dest/"
    echo -e "${GREEN}✓ $name copied${NC}"
}

# Get target
TARGET="${1:-all}"

# Copy backend files
if [[ "$TARGET" == "backend" || "$TARGET" == "all" ]]; then
    echo -e "${BLUE}Backend Files:${NC}"
    copy_files "$ME4BRAIN_SRC/models" "$SCRIPT_DIR/backend/models" "Backend Models (4.3GB)"
    copy_files "$ME4BRAIN_SRC/data" "$SCRIPT_DIR/backend/data" "Backend Data (497MB)"
    copy_files "$ME4BRAIN_SRC/storage" "$SCRIPT_DIR/backend/storage" "Backend Storage (227MB)"
    echo ""
fi

# Copy frontend files
if [[ "$TARGET" == "frontend" || "$TARGET" == "all" ]]; then
    echo -e "${BLUE}Frontend Files:${NC}"
    copy_files "$PERSAN_SRC/models" "$SCRIPT_DIR/frontend/models" "Frontend Models (4.3GB)"
    copy_files "$PERSAN_SRC/node_modules" "$SCRIPT_DIR/frontend/node_modules" "Frontend node_modules (616MB)"
    echo ""
fi

echo -e "${GREEN}✓ Copy complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. Run: ./dev-setup.sh"
echo "  2. Run: ./dev-backend.sh"
echo "  3. Run: ./dev-frontend.sh"
echo ""
```

## 🔍 Verify Copies

After copying, verify everything is in place:

```bash
# Check backend files
ls -lh backend/models
ls -lh backend/data
ls -lh backend/storage

# Check frontend files
ls -lh frontend/models
ls -lh frontend/node_modules

# Check file counts
echo "Backend models: $(find backend/models -type f | wc -l) files"
echo "Frontend node_modules: $(find frontend/node_modules -type f | wc -l) files"
```

## 🚨 Troubleshooting

### Copy is slow
```bash
# Use faster options
rsync -av --progress --ignore-existing \
  /Users/fulvio/coding/Me4BrAIn/models/ \
  /Users/fulvio/coding/jai/backend/models/
```

### Out of disk space
```bash
# Check available space
df -h /

# Only copy essential files
rsync -av --progress \
  /Users/fulvio/coding/Me4BrAIn/models/ \
  /Users/fulvio/coding/jai/backend/models/
```

### Permission errors
```bash
# Ensure permissions are correct
chmod -R u+w /Users/fulvio/coding/jai/backend
chmod -R u+w /Users/fulvio/coding/jai/frontend
```

### Resume interrupted copy
```bash
# rsync automatically resumes, just run again
rsync -av --progress \
  /Users/fulvio/coding/Me4BrAIn/models/ \
  /Users/fulvio/coding/jai/backend/models/
```

## 📊 Copy Time Estimates

| Component | Size | Copy Time (SSD) | Notes |
|-----------|------|-----------------|-------|
| Backend Models | 4.3GB | 5-10 min | BAAI embeddings |
| Backend Data | 497MB | 1 min | Test fixtures |
| Backend Storage | 227MB | 1 min | Qdrant indexes |
| Frontend Models | 4.3GB | 5-10 min | Tokenizers |
| Frontend node_modules | 616MB | 2-3 min | Dependencies |
| **Total** | **13.5GB** | **15-30 min** | All components |

## 🎯 Recommended Workflow

```bash
# 1. Copy essential files (skip data/storage initially)
rsync -av --progress \
  /Users/fulvio/coding/Me4BrAIn/models/ \
  /Users/fulvio/coding/jai/backend/models/

rsync -av --progress \
  /Users/fulvio/coding/PersAn/node_modules/ \
  /Users/fulvio/coding/jai/frontend/node_modules/

# 2. Initialize development environment
./dev-setup.sh

# 3. Start developing
./dev-backend.sh &
./dev-frontend.sh &

# 4. Copy data/storage later if needed
rsync -av --progress \
  /Users/fulvio/coding/Me4BrAIn/data/ \
  /Users/fulvio/coding/jai/backend/data/
```

## 📝 Notes

- **Don't commit these files to Git** - They're in `.gitignore`
- **Models are large** - Keep local copies, don't store in VCS
- **node_modules changes** - If you modify dependencies, run `npm install` instead
- **Data is read-only** - For development/testing only
- **Storage can be recreated** - Qdrant will rebuild indexes if needed

