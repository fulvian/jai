#!/bin/bash

################################################################################
# JAI Development Setup Script
#
# This script sets up the hybrid development environment:
# - Starts Docker containers for PostgreSQL, Redis, Qdrant
# - Guides you through backend and frontend setup
#
# Usage:
#   ./dev-setup.sh
#   ./dev-setup.sh --clean    (remove old containers and volumes)
#
# After running this, follow the printed instructions to start backend/frontend
################################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║           JAI Development Environment Setup                     ║${NC}"
echo -e "${BLUE}║           (Hybrid Mode: Dependencies in Docker)               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker is not installed or not in PATH${NC}"
    echo "  Please install Docker Desktop for Mac: https://docs.docker.com/desktop/install/mac-install/"
    exit 1
fi

echo -e "${GREEN}✓ Docker is installed${NC}"

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}✗ Docker daemon is not running${NC}"
    echo "  Please start Docker Desktop"
    exit 1
fi

echo -e "${GREEN}✓ Docker daemon is running${NC}"

# Check if we should clean
CLEAN=false
if [[ "$1" == "--clean" ]]; then
    CLEAN=true
    echo -e "${YELLOW}⚠ Cleaning mode enabled${NC}"
fi

# Cleanup old containers if requested
if [ "$CLEAN" = true ]; then
    echo -e "${YELLOW}Stopping and removing old containers...${NC}"
    docker-compose -f "$PROJECT_ROOT/docker-compose.dev.yml" down -v 2>/dev/null || true
    echo -e "${GREEN}✓ Cleanup complete${NC}"
fi

# Start Docker containers
echo ""
echo -e "${BLUE}Starting Docker containers (PostgreSQL, Redis, Qdrant)...${NC}"

cd "$PROJECT_ROOT"
docker-compose -f docker-compose.dev.yml up -d

# Wait for containers to be ready
echo -e "${YELLOW}Waiting for services to be healthy...${NC}"

# Wait for PostgreSQL
echo -n "  Checking PostgreSQL... "
for i in {1..30}; do
    if docker-compose -f docker-compose.dev.yml exec -T postgres pg_isready -U jai_user &> /dev/null; then
        echo -e "${GREEN}✓${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ (timeout)${NC}"
        exit 1
    fi
    sleep 1
done

# Wait for Redis
echo -n "  Checking Redis... "
for i in {1..30}; do
    if docker-compose -f docker-compose.dev.yml exec -T redis redis-cli ping &> /dev/null; then
        echo -e "${GREEN}✓${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ (timeout)${NC}"
        exit 1
    fi
    sleep 1
done

# Wait for Qdrant
echo -n "  Checking Qdrant... "
for i in {1..30}; do
    if curl -s http://localhost:6333/health &> /dev/null; then
        echo -e "${GREEN}✓${NC}"
        break
    fi
    if [ $i -eq 30 ]; then
        echo -e "${RED}✗ (timeout)${NC}"
        exit 1
    fi
    sleep 1
done

echo ""
echo -e "${GREEN}✓ All Docker containers are healthy${NC}"

# Setup environment files
echo ""
echo -e "${BLUE}Setting up environment files...${NC}"

# Backend
if [ ! -f "$PROJECT_ROOT/backend/.env" ]; then
    cp "$PROJECT_ROOT/.env.development" "$PROJECT_ROOT/backend/.env"
    echo -e "${GREEN}✓ Created backend/.env from .env.development${NC}"
else
    echo -e "${YELLOW}⚠ backend/.env already exists (skipped)${NC}"
fi

# Frontend
if [ ! -f "$PROJECT_ROOT/frontend/.env.local" ]; then
    cp "$PROJECT_ROOT/.env.development" "$PROJECT_ROOT/frontend/.env.local"
    echo -e "${GREEN}✓ Created frontend/.env.local from .env.development${NC}"
else
    echo -e "${YELLOW}⚠ frontend/.env.local already exists (skipped)${NC}"
fi

# Print connection details
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              Docker Dependencies Ready for Use                  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}Service Connection Details:${NC}"
echo "  PostgreSQL:   localhost:5432"
echo "  Redis:        localhost:6379"
echo "  Qdrant:       localhost:6333"
echo ""

# Show next steps
echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                        Next Steps                               ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}1. In a NEW terminal, start the Backend (Python FastAPI):${NC}"
echo "   cd $PROJECT_ROOT/backend"
echo "   python -m venv venv"
echo "   source venv/bin/activate"
echo "   pip install -e ."
echo "   fastapi run"
echo ""
echo -e "${YELLOW}2. In ANOTHER NEW terminal, start the Frontend (React):${NC}"
echo "   cd $PROJECT_ROOT/frontend"
echo "   npm install"
echo "   npm run dev"
echo ""
echo -e "${YELLOW}3. Access the applications:${NC}"
echo "   Frontend:  http://localhost:3000"
echo "   Backend:   http://localhost:8000"
echo "   API Docs:  http://localhost:8000/docs"
echo ""
echo -e "${YELLOW}4. To stop Docker services:${NC}"
echo "   docker-compose -f docker-compose.dev.yml down"
echo ""
echo -e "${YELLOW}5. To view logs from Docker services:${NC}"
echo "   docker-compose -f docker-compose.dev.yml logs -f"
echo ""
