#!/bin/bash
# ============================================================
# deploy_geekcom_fast.sh — Fast Dev Mode Deploy to GeekCom
# ============================================================
# Usage: bash deploy_geekcom_fast.sh
# ============================================================
set -euo pipefail

# --- Configuration ---
REMOTE_USER="fulvio"
REMOTE_HOST="100.99.43.29"
DEPLOY_ROOT="/home/fulvio/persan_me4brain"
ME4BRAIN_DIR="$DEPLOY_ROOT/me4brain"
PERSAN_DIR="$DEPLOY_ROOT/persan"

# Local directories
ME4BRAIN_LOCAL="/Users/fulvio/coding/Me4BrAIn"
PERSAN_LOCAL="/Users/fulvio/coding/PersAn"

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
info "FAST DEV MODE DEPLOY — $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"

# 1. Sync Environment Files (Push local .env to remote if exists)
info "Step 1: Syncing environment files..."
if [ -f "$ME4BRAIN_LOCAL/.env" ]; then
  rsync -avz "$ME4BRAIN_LOCAL/.env" "$REMOTE_USER@$REMOTE_HOST:$ME4BRAIN_DIR/"
fi
rsync -avz "$ME4BRAIN_LOCAL/.env.example" "$REMOTE_USER@$REMOTE_HOST:$ME4BRAIN_DIR/"

if [ -f "$PERSAN_LOCAL/.env" ]; then
  rsync -avz "$PERSAN_LOCAL/.env" "$REMOTE_USER@$REMOTE_HOST:$PERSAN_DIR/"
fi
rsync -avz "$PERSAN_LOCAL/.env.example" "$REMOTE_USER@$REMOTE_HOST:$PERSAN_DIR/"
log "Environment files synced."

# 2. Update Code in Bind Mount (Source of Truth)
info "Step 2: Updating code in bind mount..."
ssh -o ConnectTimeout=10 "$REMOTE_USER@$REMOTE_HOST" \
  "sudo -n bash -c 'cd /root/persan_me4brain/me4brain && git fetch origin master && git reset --hard origin/master && git status'" \
  || warn "Git update in bind mount failed (may need password)"
log "Code updated in bind mount."

# 3. Kill Old Processes (Graceful)
info "Step 3: Stopping old processes..."
ssh -o ConnectTimeout=10 "$REMOTE_USER@$REMOTE_HOST" \
  "sudo -n bash -c 'docker stop me4brain-api me4brain-gateway me4brain-backend me4brain-frontend' || true" \
  || true
ssh -o ConnectTimeout=10 "$REMOTE_USER@$REMOTE_HOST" "pkill -f 'uvicorn.*me4brain' || true" || true
ssh -o ConnectTimeout=10 "$REMOTE_USER@$REMOTE_HOST" "bash $PERSAN_DIR/scripts/stop.sh || true" || true
sleep 2
log "Old processes stopped."

# 3. Start Me4Brain (Background, nohup)
info "Step 3: Starting Me4Brain (background)..."
ssh -o ConnectTimeout=10 "$REMOTE_USER@$REMOTE_HOST" "nohup bash $ME4BRAIN_DIR/scripts/start.sh > /tmp/me4brain_deploy.log 2>&1 &" || err "Failed to start Me4Brain"
log "Me4Brain started (check /tmp/me4brain_deploy.log)"

# 4. Wait for Me4Brain Health
info "Step 4: Waiting for Me4Brain to be healthy..."
for i in {1..30}; do
  HEALTH=$(ssh -o ConnectTimeout=10 "$REMOTE_USER@$REMOTE_HOST" "curl -s http://localhost:8089/health 2>/dev/null | grep -o 'healthy' || echo 'not_ready'" || echo "not_ready")
  if [ "$HEALTH" = "healthy" ]; then
    log "Me4Brain is healthy!"
    break
  fi
  echo "  Attempt $i/30... waiting..."
  sleep 2
done

# 5. Start PersAn (Background, nohup)
info "Step 5: Starting PersAn (background)..."
ssh -o ConnectTimeout=10 "$REMOTE_USER@$REMOTE_HOST" "nohup bash $PERSAN_DIR/scripts/start.sh > /tmp/persan_deploy.log 2>&1 &" || err "Failed to start PersAn"
log "PersAn started (check /tmp/persan_deploy.log)"

# 6. Verify Services
info "Step 6: Verifying services..."
sleep 3
ssh -o ConnectTimeout=10 "$REMOTE_USER@$REMOTE_HOST" "docker ps -a --format 'table {{.Names}}\t{{.Status}}' | grep me4brain" || warn "Docker containers check failed"
log "Services verification complete."

echo "============================================================"
log "FAST DEPLOY COMPLETE!"
info "Me4Brain API:  http://100.99.43.29:8089/v1"
info "PersAn Gateway: http://100.99.43.29:3030"
info "PersAn Frontend: http://100.99.43.29:3020"
info "Logs:"
info "  Me4Brain: ssh $REMOTE_USER@$REMOTE_HOST 'tail -f /tmp/me4brain_deploy.log'"
info "  PersAn:   ssh $REMOTE_USER@$REMOTE_HOST 'tail -f /tmp/persan_deploy.log'"
echo "============================================================"
