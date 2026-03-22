#!/bin/bash
# =============================================================================
# PersAn - Start Script (Development Mode)
# =============================================================================
# Avvia Gateway + Frontend come processi background persistenti.
# I log vengono scritti in /tmp/persan-*.log
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# SOTA 2026: Auto-load NVM/Node if present (needed for non-interactive SSH)
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh" 
export PATH="$NVM_DIR/versions/node/v24.13.0/bin:$HOME/bin:/usr/local/bin:$PATH"

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║              PERSAN - DEV STARTUP SCRIPT                  ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"

# =============================================================================
# 1. Termina processi precedenti
# =============================================================================
echo -e "\n${YELLOW}[1/4] Verifico processi esistenti...${NC}"

# Gateway
if pgrep -f "tsx.*gateway" > /dev/null 2>&1; then
    echo -e "${YELLOW}  → Gateway attivo, termino...${NC}"
    pkill -f "tsx.*gateway" || true
    sleep 1
fi

# Frontend  
if pgrep -f "next.*3020" > /dev/null 2>&1; then
    echo -e "${YELLOW}  → Frontend attivo, termino...${NC}"
    pkill -f "next.*3020" || true
    sleep 1
fi

# Pulisci porte
if lsof -ti :3030 > /dev/null 2>&1; then
    echo -e "${YELLOW}  → Porta 3030 occupata, libero...${NC}"
    lsof -ti :3030 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

if lsof -ti :3020 > /dev/null 2>&1; then
    echo -e "${YELLOW}  → Porta 3020 occupata, libero...${NC}"
    lsof -ti :3020 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

echo -e "${GREEN}  ✓ Processi precedenti terminati${NC}"

# =============================================================================
# 2. Verifica prerequisiti
# =============================================================================
echo -e "\n${YELLOW}[2/4] Verifico prerequisiti...${NC}"

# Verifica Me4BrAIn
if curl -s --connect-timeout 3 http://localhost:8089/health > /dev/null 2>&1; then
    echo -e "${GREEN}  ✓ Me4BrAIn API raggiungibile (porta 8089)${NC}"
    echo -e "${RED}  ⚠ Me4BrAIn API NON raggiungibile su :8089${NC}"
    echo -e "${RED}    Avvia prima: bash /Users/fulvio/coding/Me4BrAIn/scripts/start.sh${NC}"
fi

# Verifica .env
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "${RED}  ✗ File .env non trovato in $PROJECT_DIR${NC}"
    exit 1
fi
echo -e "${GREEN}  ✓ File .env trovato${NC}"

# =============================================================================
# 3. Avvia Gateway (background)
# =============================================================================
echo -e "\n${YELLOW}[3/4] Avvio Gateway...${NC}"

# SOTA 2026: Use user-specific log files to avoid permission issues
LOG_SUFFIX="$(whoami)-$(date +%s)"
GATEWAY_LOG="/tmp/persan-gateway-${LOG_SUFFIX}.log"
# Symlink for easier tailing
ln -sf "$GATEWAY_LOG" /tmp/persan-gateway.log || true

cd "$PROJECT_DIR/packages/gateway"

# Avvio in background con nohup, redirigendo output al log
nohup npx tsx --env-file=../../.env src/index.ts > "$GATEWAY_LOG" 2>&1 &
GATEWAY_PID=$!
disown $GATEWAY_PID

echo -e "${YELLOW}  → Gateway PID: $GATEWAY_PID${NC}"

# Attendi che sia pronto
echo -e "${YELLOW}  → Attendo avvio Gateway...${NC}"
for i in $(seq 1 15); do
    if curl -s --connect-timeout 1 http://localhost:3030/health > /dev/null 2>&1; then
        echo -e "${GREEN}  ✓ Gateway pronto su http://localhost:3030${NC}"
        break
    fi
    if ! kill -0 $GATEWAY_PID 2>/dev/null; then
        echo -e "${RED}  ✗ Gateway crashato! Log:${NC}"
        tail -20 "$GATEWAY_LOG"
        exit 1
    fi
    sleep 1
done

# Verifica finale
if ! curl -s --connect-timeout 2 http://localhost:3030/health > /dev/null 2>&1; then
    echo -e "${RED}  ✗ Gateway non risponde dopo 15s. Log:${NC}"
    tail -20 "$GATEWAY_LOG"
    exit 1
fi

# =============================================================================
# 4. Avvia Frontend (background)
# =============================================================================
echo -e "\n${YELLOW}[4/4] Avvio Frontend...${NC}"

FRONTEND_LOG="/tmp/persan-frontend-${LOG_SUFFIX}.log"
ln -sf "$FRONTEND_LOG" /tmp/persan-frontend.log || true

cd "$PROJECT_DIR/frontend"

# Pulisci cache Next.js per evitare errori di permessi da build precedenti
# Usa find -delete che bypassa i permessi root
echo -e "${YELLOW}  → Pulendo cache Next.js...${NC}"
find .next .turbo -type f -delete 2>/dev/null || true
find .next .turbo -type d -delete 2>/dev/null || true

# Avvio in background con nohup
nohup npm run dev -- -H 0.0.0.0 > "$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!
disown $FRONTEND_PID

echo -e "${YELLOW}  → Frontend PID: $FRONTEND_PID${NC}"

# Attendi che sia pronto (Next.js può impiegare qualche secondo)
echo -e "${YELLOW}  → Attendo avvio Frontend...${NC}"
for i in $(seq 1 20); do
    if curl -s --connect-timeout 1 http://localhost:3020 > /dev/null 2>&1; then
        echo -e "${GREEN}  ✓ Frontend pronto su http://localhost:3020${NC}"
        break
    fi
    if ! kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${RED}  ✗ Frontend crashato! Log:${NC}"
        tail -20 "$FRONTEND_LOG"
        exit 1
    fi
    sleep 1
done

# =============================================================================
# Summary
# =============================================================================
echo -e "\n${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  PersAn Dev Stack avviato!${NC}"
echo -e "${GREEN}  ────────────────────────────────────────────────────────${NC}"
echo -e "${GREEN}  Frontend:  http://localhost:3020  (PID: $FRONTEND_PID)${NC}"
echo -e "${GREEN}  Gateway:   http://localhost:3030  (PID: $GATEWAY_PID)${NC}"
echo -e "${GREEN}  ────────────────────────────────────────────────────────${NC}"
echo -e "${CYAN}  Log Gateway:  tail -f $GATEWAY_LOG${NC}"
echo -e "${CYAN}  Log Frontend: tail -f $FRONTEND_LOG${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "\n${YELLOW}Per stoppare: bash $SCRIPT_DIR/stop.sh${NC}"
