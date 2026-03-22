#!/bin/bash

# Master Development Mode Startup Script
# Starts all services: Backend, Frontend, Monitoring

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$(cd "$BACKEND_DIR/../PersAn" && pwd)"
LOG_DIR="$BACKEND_DIR/logs"

# Create logs directory
mkdir -p "$LOG_DIR"

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down services...${NC}"
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    kill $MONITOR_PID 2>/dev/null || true
    echo -e "${GREEN}✓${NC} All services stopped"
    exit 0
}

# Trap Ctrl+C
trap cleanup SIGINT SIGTERM

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    Me4BrAIn + PersAn Development Mode - All Services      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Start Backend
echo -e "${YELLOW}[1/3]${NC} Starting Backend Server..."
cd "$BACKEND_DIR"
python -m me4brain.main > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo -e "${GREEN}✓${NC} Backend started (PID: $BACKEND_PID)"
echo "    Logs: $LOG_DIR/backend.log"
sleep 2
echo ""

# Start Frontend
echo -e "${YELLOW}[2/3]${NC} Starting Frontend Server..."
cd "$FRONTEND_DIR"
npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo -e "${GREEN}✓${NC} Frontend started (PID: $FRONTEND_PID)"
echo "    Logs: $LOG_DIR/frontend.log"
echo "    URL: http://localhost:3000"
sleep 2
echo ""

# Start Monitoring
echo -e "${YELLOW}[3/3]${NC} Starting Monitoring Dashboard..."
cd "$BACKEND_DIR"
python scripts/monitor_intent.py > "$LOG_DIR/monitor.log" 2>&1 &
MONITOR_PID=$!
echo -e "${GREEN}✓${NC} Monitoring started (PID: $MONITOR_PID)"
echo "    Logs: $LOG_DIR/monitor.log"
echo ""

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                   All Services Running                     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${GREEN}Services:${NC}"
echo "  Backend:    http://localhost:8000 (PID: $BACKEND_PID)"
echo "  Frontend:   http://localhost:3000 (PID: $FRONTEND_PID)"
echo "  Monitoring: Dashboard (PID: $MONITOR_PID)"
echo ""

echo -e "${YELLOW}Logs:${NC}"
echo "  Backend:    $LOG_DIR/backend.log"
echo "  Frontend:   $LOG_DIR/frontend.log"
echo "  Monitoring: $LOG_DIR/monitor.log"
echo ""

echo -e "${YELLOW}Test Query:${NC}"
echo "  Send: 'Che tempo fa a Caltanissetta?'"
echo "  Expected: System retrieves actual weather data"
echo ""

echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# Wait for all processes
wait
