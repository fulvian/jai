#!/bin/bash
# =============================================================================
# PersAn - Stop Script
# =============================================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}Stoppando PersAn...${NC}"

# Gateway
if pgrep -f "tsx.*gateway\|tsx.*index.ts" > /dev/null 2>&1; then
    echo -e "${YELLOW}  → Termino Gateway...${NC}"
    pkill -f "tsx.*gateway" 2>/dev/null || true
    pkill -f "tsx.*index.ts" 2>/dev/null || true
fi

# Frontend
if pgrep -f "next.*3020\|next-server.*persan" > /dev/null 2>&1; then
    echo -e "${YELLOW}  → Termino Frontend...${NC}"
    pkill -f "next.*3020" 2>/dev/null || true
fi

# Kill by port as fallback
for PORT in 3020 3030; do
    if lsof -ti :$PORT > /dev/null 2>&1; then
        echo -e "${YELLOW}  → Libero porta $PORT...${NC}"
        lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
    fi
done

sleep 1

echo -e "${GREEN}  ✓ PersAn stoppato${NC}"
