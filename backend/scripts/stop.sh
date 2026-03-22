#!/bin/bash
# =============================================================================
# Me4BrAIn Core - Stop Script
# =============================================================================
# Ferma l'intero stack Me4BrAIn in modo sicuro e pulito
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${RED}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${RED}║           ME4BRAIN CORE - SHUTDOWN SCRIPT                 ║${NC}"
echo -e "${RED}╚════════════════════════════════════════════════════════════╝${NC}"

# -----------------------------------------------------------------------------
# 1. Termina processi Python
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[1/2] Termino processi Me4BrAIn...${NC}"

if pgrep -f "uvicorn.*me4brain" > /dev/null 2>&1; then
    echo -e "${YELLOW}  → Invio SIGTERM a processi uvicorn...${NC}"
    pkill -TERM -f "uvicorn.*me4brain" || true
    sleep 2
    
    # Forza kill se ancora attivi
    if pgrep -f "uvicorn.*me4brain" > /dev/null 2>&1; then
        echo -e "${YELLOW}  → Forzo terminazione...${NC}"
        pkill -KILL -f "uvicorn.*me4brain" || true
    fi
    echo -e "${GREEN}  ✓ Processi terminati${NC}"
else
    echo -e "${GREEN}  ✓ Nessun processo attivo${NC}"
fi

# -----------------------------------------------------------------------------
# 2. Ferma Docker containers
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[2/2] Fermo containers Docker...${NC}"

cd "$PROJECT_DIR"

if docker compose -f docker/docker-compose.yml ps -q 2>/dev/null | grep -q .; then
    echo -e "${YELLOW}  → Stop containers...${NC}"
    docker compose -f docker/docker-compose.yml stop
    echo -e "${GREEN}  ✓ Containers fermati${NC}"
else
    echo -e "${GREEN}  ✓ Nessun container attivo${NC}"
fi

# -----------------------------------------------------------------------------
# Completato
# -----------------------------------------------------------------------------
echo -e "\n${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Me4BrAIn Core fermato correttamente.${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}\n"

# Opzionale: rimuovi containers (decommentare se necessario)
# echo -e "${YELLOW}Per rimuovere i containers: docker compose -f docker/docker-compose.yml down${NC}"
# echo -e "${YELLOW}Per rimuovere anche i volumi: docker compose -f docker/docker-compose.yml down -v${NC}"
