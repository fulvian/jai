#!/bin/bash

################################################################################
# JAI Frontend Development Script
#
# Starts the React/Next.js frontend with hot reload enabled
#
# Prerequisites:
#   - Node.js 18+ installed
#   - Docker containers must be running (run dev-setup.sh first)
#
# Usage:
#   ./dev-frontend.sh
#   ./dev-frontend.sh --build            (build for production)
#   ./dev-frontend.sh --test             (run tests)
#
################################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$SCRIPT_DIR/frontend"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           JAI Frontend Development Server (React/Next.js)       ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if frontend directory exists
if [ ! -d "$FRONTEND_DIR" ]; then
    echo -e "${RED}✗ Frontend directory not found at $FRONTEND_DIR${NC}"
    exit 1
fi

cd "$FRONTEND_DIR"

# Check Node.js version
if ! command -v node &> /dev/null; then
    echo -e "${RED}✗ Node.js is not installed${NC}"
    echo "  Please install Node.js 18+: https://nodejs.org/"
    exit 1
fi

NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo -e "${RED}✗ Node.js 18+ is required (you have v$(node --version))${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Node.js $(node --version) detected${NC}"

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    npm install
    echo -e "${GREEN}✓ Dependencies installed${NC}"
fi

echo ""

# Check what to run
case "$1" in
    --build)
        echo -e "${BLUE}Building for production...${NC}"
        npm run build
        echo -e "${GREEN}✓ Build complete. Output in .next/${NC}"
        ;;
    --test)
        echo -e "${BLUE}Running tests...${NC}"
        npm run test
        ;;
    *)
        echo -e "${BLUE}Starting Next.js development server...${NC}"
        echo ""
        echo -e "${GREEN}Server Details:${NC}"
        echo "  URL:       http://localhost:3000"
        echo "  API URL:   http://localhost:8000 (backend)"
        echo ""
        echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
        echo ""
        
        # Run Next.js with hot reload
        npm run dev
        ;;
esac
