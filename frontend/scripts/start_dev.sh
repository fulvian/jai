#!/bin/bash

# Development Mode Startup Script
# Starts PersAn frontend in dev mode

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"

# Create logs directory
mkdir -p "$LOG_DIR"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         PersAn Frontend Development Mode Startup          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check Node.js
echo -e "${YELLOW}[1/3]${NC} Checking Node.js..."
if ! command -v node &> /dev/null; then
    echo -e "${RED}Error: Node.js not found${NC}"
    exit 1
fi
NODE_VERSION=$(node --version)
echo -e "${GREEN}✓${NC} $NODE_VERSION"
echo ""

# Check npm
echo -e "${YELLOW}[2/3]${NC} Checking npm..."
if ! command -v npm &> /dev/null; then
    echo -e "${RED}Error: npm not found${NC}"
    exit 1
fi
NPM_VERSION=$(npm --version)
echo -e "${GREEN}✓${NC} npm $NPM_VERSION"
echo ""

# Install dependencies if needed
echo -e "${YELLOW}[3/3]${NC} Checking dependencies..."
if [ ! -d "$PROJECT_ROOT/node_modules" ]; then
    echo -e "${YELLOW}Installing npm dependencies...${NC}"
    npm install > /dev/null 2>&1
fi
echo -e "${GREEN}✓${NC} Dependencies ready"
echo ""

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              Starting PersAn Frontend                      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}Starting frontend server...${NC}"
echo "Logs: $LOG_DIR/frontend.log"
echo "URL: http://localhost:3000"
echo ""

cd "$PROJECT_ROOT"
npm run dev 2>&1 | tee "$LOG_DIR/frontend.log"
