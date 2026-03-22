#!/bin/bash

# ============================================
# PersAn Development Startup Script
# ============================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🤖 PersAn Development Environment${NC}"
echo "========================================"

# Check if .env exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠️  No .env file found. Copying from .env.example...${NC}"
    cp .env.example .env
fi

# Load ME4BRAIN_URL from .env
ME4BRAIN_URL=$(grep -E '^ME4BRAIN_URL=' .env | cut -d'=' -f2- | tr -d '\r')
ME4BRAIN_URL=${ME4BRAIN_URL:-"http://localhost:8000"}

# Check if Me4BrAIn is running
check_me4brain() {
    echo -e "${BLUE}📡 Checking Me4BrAIn connection...${NC}"
    if curl -s "${ME4BRAIN_URL}/health" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Me4BrAIn is running on ${ME4BRAIN_URL}${NC}"
        return 0
    else
        echo -e "${RED}❌ Me4BrAIn is NOT running on ${ME4BRAIN_URL}${NC}"
        echo -e "${YELLOW}   Please start Me4BrAIn Docker stack:${NC}"
        echo -e "${YELLOW}   cd /Users/fulvioventura/me4brain && docker compose -f docker/docker-compose.yml --profile full up -d${NC}"
        return 1
    fi
}

# Start backend
start_backend() {
    echo -e "${BLUE}🔧 Starting Backend (FastAPI)...${NC}"
    cd "$SCRIPT_DIR"
    uv run uvicorn backend.main:app --host 0.0.0.0 --port 8888 --reload --reload-exclude 'frontend/*' --reload-exclude 'node_modules/*' &
    BACKEND_PID=$!
    echo $BACKEND_PID > backend.pid
    echo -e "${GREEN}✅ Backend started (PID: $BACKEND_PID) on http://localhost:8888${NC}"
}

# Start frontend
start_frontend() {
    echo -e "${BLUE}🎨 Starting Frontend (Next.js)...${NC}"
    cd "$SCRIPT_DIR/frontend"
    
    # Install deps if needed
    if [ ! -d "node_modules" ]; then
        echo -e "${YELLOW}   Installing npm dependencies...${NC}"
        npm install
    fi
    
    npm run dev &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > ../frontend.pid
    echo -e "${GREEN}✅ Frontend started (PID: $FRONTEND_PID) on http://localhost:3020${NC}"
    cd "$SCRIPT_DIR"
}

# Cleanup function
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down...${NC}"
    
    if [ -f "backend.pid" ]; then
        kill $(cat backend.pid) 2>/dev/null || true
        rm backend.pid
    fi
    
    if [ -f "frontend.pid" ]; then
        kill $(cat frontend.pid) 2>/dev/null || true
        rm frontend.pid
    fi
    
    echo -e "${GREEN}👋 Goodbye!${NC}"
    exit 0
}

# Trap Ctrl+C
trap cleanup SIGINT SIGTERM

# Main
main() {
    # Check Me4BrAIn first
    if ! check_me4brain; then
        exit 1
    fi
    
    echo ""
    start_backend
    sleep 2
    start_frontend
    
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}🚀 PersAn is running!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo -e "   Frontend:  ${BLUE}http://localhost:3020${NC}"
    echo -e "   Backend:   ${BLUE}http://localhost:8888${NC}"
    echo -e "   Health:    ${BLUE}http://localhost:8888/api/health${NC}"
    echo -e "   Me4BrAIn: ${BLUE}${ME4BRAIN_URL}${NC}"
    echo ""
    echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
    
    # Wait for processes
    wait
}

main "$@"
