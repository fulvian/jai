#!/bin/bash

################################################################################
# JAI Backend Development Script
#
# Starts the FastAPI backend with hot reload enabled
# 
# Prerequisites:
#   - Docker containers must be running (run dev-setup.sh first)
#   - Python 3.9+ installed
#
# Usage:
#   ./dev-backend.sh
#   ./dev-backend.sh --test              (run tests instead)
#   ./dev-backend.sh --coverage          (run tests with coverage)
#
################################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║             JAI Backend Development Server                      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if backend directory exists
if [ ! -d "$BACKEND_DIR" ]; then
    echo -e "${RED}✗ Backend directory not found at $BACKEND_DIR${NC}"
    exit 1
fi

cd "$BACKEND_DIR"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}Creating Python virtual environment...${NC}"
    python -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

# Activate virtual environment
source venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"

# Install dependencies
echo -e "${YELLOW}Checking and installing dependencies...${NC}"
pip install -q -e .
echo -e "${GREEN}✓ Dependencies installed${NC}"

echo ""

# Check what to run
case "$1" in
    --test)
        echo -e "${BLUE}Running tests...${NC}"
        pytest tests/ -v --tb=short
        ;;
    --coverage)
        echo -e "${BLUE}Running tests with coverage...${NC}"
        pytest tests/ -v --cov=src/me4brain --cov-report=html --cov-report=term
        echo -e "${GREEN}✓ Coverage report generated in htmlcov/index.html${NC}"
        ;;
    *)
        echo -e "${BLUE}Starting FastAPI development server...${NC}"
        echo ""
        echo -e "${GREEN}Server Details:${NC}"
        echo "  URL:       http://localhost:8000"
        echo "  API Docs:  http://localhost:8000/docs"
        echo "  OpenAPI:   http://localhost:8000/openapi.json"
        echo ""
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        echo ""
        
        # Run FastAPI with auto-reload
        fastapi run --host 0.0.0.0 --port 8000 --reload
        ;;
esac
