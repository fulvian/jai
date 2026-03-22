#!/bin/bash
# ============================================================
# deploy-all.sh — PersAn & Me4Brain Unified Deployment
# ============================================================
# Usage: ./deploy-all.sh
# ============================================================
set -euo pipefail

# --- Configuration ---
DEPLOY_ROOT="/home/fulvio/persan_me4brain"
ME4BRAIN_DIR="$DEPLOY_ROOT/me4brain"
PERSAN_DIR="$DEPLOY_ROOT/persan"

# --- Colors ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
err()  { echo -e "${RED}❌ $1${NC}"; }
info() { echo -e "${CYAN}🚀 $1${NC}"; }

echo "============================================================"
info "STARTING UNIFIED DEPLOY — $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

# 0. Prepare Directories
info "Step 0: Preparing directories..."
mkdir -p "$DEPLOY_ROOT/me4brain/data" "$DEPLOY_ROOT/me4brain/models" "$DEPLOY_ROOT/persan_data/redis"
log "Directories prepared."

# 1. Update Repositories
mkdir -p "$DEPLOY_ROOT"
cd "$DEPLOY_ROOT"

if [ ! -d "me4brain" ]; then
    git clone git@github.com:fulvian/Me4BrAIn.git me4brain
else
    cd me4brain && git pull origin master && cd ..
fi

if [ ! -d "persan" ]; then
    git clone git@github.com:fulvian/PersAn.git persan
else
    cd persan && git fetch origin && git reset --hard origin/master && cd ..
fi

# 2. Check Envs
info "Step 2: Checking environment files..."
# SOTA 2026: Ensure env files are preserved or created from example
for dir in "$ME4BRAIN_DIR" "$PERSAN_DIR"; do
    if [ ! -f "$dir/.env" ]; then
        if [ -f "$dir/.env.example" ]; then
            warn "Creating $dir/.env from example..."
            cp "$dir/.env.example" "$dir/.env"
        else
            err "Missing .env and .env.example in $dir"
            exit 1
        fi
    fi
done
log "Environment files ready."

# 3. Build & Restart Me4Brain
info "Step 3: Deploying Me4Brain Stack..."
cd "$ME4BRAIN_DIR"
# Usiamo il profilo app per includere l'API e l'infra
docker compose -f docker/docker-compose.yml --profile app up -d --build
log "Me4Brain stack is up."

# 4. Build & Restart PersAn Gateway
info "Step 4: Deploying PersAn Gateway..."
cd "$PERSAN_DIR"
# Override ME4BRAIN_URL per usare Tailscale IP invece di localhost/host.docker.internal
export ME4BRAIN_URL="http://100.99.43.29:8000/v1"
docker compose -f docker/docker-compose.gateway.yml up -d --build
log "PersAn Gateway is up."

# 5. Build & Start PersAn Frontend (as Docker or Static)
info "Step 5: Deploying PersAn Frontend..."
# Installazione dipendenze dal root (per workspaces)
cd "$PERSAN_DIR"
export PATH="/home/fulvio/.nvm/versions/node/v24.13.0/bin:$PATH"
npm install --silent

# Build (Next.js)
cd "$PERSAN_DIR/frontend"
cat <<EOF > .env.local
NEXT_PUBLIC_API_URL=http://100.99.43.29:3030
NEXT_PUBLIC_GATEWAY_URL=ws://100.99.43.29:3030/ws
NEXT_PUBLIC_VAPID_PUBLIC_KEY=BL4oiu3dW48y7DG0O3nuJixDGVaXMjepI4aYvlAI4bbnDRVawfUO3NaAUB7KDpXZ6dO7_HLfD3jxjvpZKb0mrCo
EOF
npm run build

# Riavvio via pm2 o background script (simile a dev ma prod)
pkill -f "next-server" || true
PORT=3020 HOST=0.0.0.0 NEXT_PUBLIC_API_URL=http://100.99.43.29:3030 NEXT_PUBLIC_GATEWAY_URL=ws://100.99.43.29:3030/ws
NEXT_PUBLIC_VAPID_PUBLIC_KEY=BL4oiu3dW48y7DG0O3nuJixDGVaXMjepI4aYvlAI4bbnDRVawfUO3NaAUB7KDpXZ6dO7_HLfD3jxjvpZKb0mrCo nohup npm run start > /tmp/persan-frontend.log 2>&1 &
log "PersAn Frontend is up."

echo "============================================================"
log "DEPLOYMENT COMPLETE!"
info "Dashboard: http://100.99.43.29:3020"
info "Gateway:   http://100.99.43.29:3030"
info "Core API:  http://100.99.43.29:8089"
echo "============================================================"
