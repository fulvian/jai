#!/bin/bash
# =============================================================================
# Me4BrAIn Core - Start Script
# =============================================================================
# Avvia l'intero stack Me4BrAIn in modo sicuro
#
# Usage:
#   bash start.sh              # Foreground (default, logs to stdout)
#   bash start.sh --background # Background (nohup + disown, logs to /tmp/me4brain.log)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
LOG_FILE="/tmp/me4brain.log"

# Parse arguments
BACKGROUND=false
for arg in "$@"; do
    case "$arg" in
        --background|-bg)
            BACKGROUND=true
            ;;
    esac
done

# Colori
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║           ME4BRAIN CORE - STARTUP SCRIPT                  ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"

if [ "$BACKGROUND" = true ]; then
    echo -e "${YELLOW}  Modalità: BACKGROUND (nohup + disown)${NC}"
    echo -e "${YELLOW}  Log file: ${LOG_FILE}${NC}"
fi

# -----------------------------------------------------------------------------
# 1. Verifica e termina processi vecchi
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[1/4] Verifico processi esistenti...${NC}"

# Termina eventuali istanze Me4BrAIn precedenti
if pgrep -f "uvicorn.*me4brain" > /dev/null 2>&1; then
    echo -e "${YELLOW}  → Trovato processo Me4BrAIn attivo, termino...${NC}"
    pkill -f "uvicorn.*me4brain" || true
    sleep 2
fi

# Libera la porta 8089 se ancora occupata
if lsof -ti :8089 > /dev/null 2>&1; then
    echo -e "${YELLOW}  → Porta 8089 ancora occupata, forzo chiusura...${NC}"
    lsof -ti :8089 | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# [2/4] Verifica containers Docker (SALTATO - MODALITÀ NATIVA)
echo -e "\n${YELLOW}[2/4] Verifica servizi locali (Native Mode)...${NC}"

# Verifica se i servizi principali sono in ascolto
for port in 6379 6333 7687 5432; do
    if ! lsof -i :$port > /dev/null 2>&1; then
        echo -e "${RED}  ✗ Servizio sulla porta $port non trovato. Assicurati che Redis, Qdrant, Neo4j e Postgres siano attivi.${NC}"
        # Non esco, i servizi potrebbero avere porte diverse o essere pigri
    else
        echo -e "${GREEN}  ✓ Porta $port attiva${NC}"
    fi
done

echo -e "${YELLOW}  → Servizi locali verificati.${NC}"
sleep 2

# -----------------------------------------------------------------------------
# 3. Verifica ambiente Python
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[3/4] Verifico ambiente Python...${NC}"

if ! command -v uv &> /dev/null; then
    echo -e "${RED}  ✗ 'uv' non trovato. Installalo con: curl -LsSf https://astral.sh/uv/install.sh | sh${NC}"
    exit 1
fi

# Sync dipendenze
echo -e "${YELLOW}  → Sync dipendenze...${NC}"
uv sync

# -----------------------------------------------------------------------------
# 4. Avvia API server
# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}[4/4] Avvio API server...${NC}"

# Copia .env se non esiste
if [ ! -f "$PROJECT_DIR/.env" ]; then
    echo -e "${YELLOW}  → Creo .env da .env.example...${NC}"
    cp "$PROJECT_DIR/.env.example" "$PROJECT_DIR/.env"
fi

cd "$PROJECT_DIR"

if [ "$BACKGROUND" = true ]; then
    # Background mode: nohup + disown, sopravvive alla chiusura del terminale
    nohup uv run python -m me4brain.api.main > "$LOG_FILE" 2>&1 &
    disown
    ME4BRAIN_PID=$!

    # Attendi che il server sia pronto
    echo -e "${YELLOW}  → Attendo avvio API server...${NC}"
    for i in $(seq 1 30); do
        if curl -s http://localhost:8089/health > /dev/null 2>&1; then
            break
        fi
        sleep 2
    done

    if curl -s http://localhost:8089/health > /dev/null 2>&1; then
        echo -e "\n${GREEN}════════════════════════════════════════════════════════════${NC}"
        echo -e "${GREEN}  Me4BrAIn Core avviato in BACKGROUND${NC}"
        echo -e "${GREEN}  ────────────────────────────────────────────────────────${NC}"
        echo -e "${GREEN}  API:  http://localhost:8089     (PID: ${ME4BRAIN_PID})${NC}"
        echo -e "${GREEN}  Docs: http://localhost:8089/docs${NC}"
        echo -e "${GREEN}  Log:  tail -f ${LOG_FILE}${NC}"
        echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
        echo -e "\nPer stoppare: pkill -f 'uvicorn.*me4brain'"
        echo -e "\n${YELLOW}⚠️  RICORDA: Se usi PersAn (frontend), riavvialo separatamente:${NC}"
        echo -e "${YELLOW}   bash ~/persan/scripts/start.sh${NC}"
    else
        echo -e "${RED}  ✗ Me4BrAIn non risponde dopo 60s. Controlla log: ${LOG_FILE}${NC}"
        exit 1
    fi
else
    # Foreground mode (default): logs a stdout, ideale per debug
    echo -e "\n${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Me4BrAIn Core in avvio su http://localhost:8089${NC}"
    echo -e "${GREEN}  Docs: http://localhost:8089/docs${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
    echo -e "\n${YELLOW}⚠️  RICORDA: Se usi PersAn (frontend), riavvialo separatamente:${NC}"
    echo -e "${YELLOW}   bash ~/persan/scripts/start.sh${NC}\n"

    uv run python -m me4brain.api.main
fi

