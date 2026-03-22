#!/bin/bash

# Development Mode Startup Script
# Starts Me4BrAIn backend and monitoring in dev mode
#
# IMPORTANT: This script MUST be run from the Me4BrAIn project directory
# or the .env file will not be loaded correctly.

set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Configuration - Always use absolute paths
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$PROJECT_ROOT/logs"
ENV_FILE="$PROJECT_ROOT/.env"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"

# Create logs directory
mkdir -p "$LOG_DIR"

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║         Me4BrAIn Development Mode Startup                 ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "Project root: ${YELLOW}$PROJECT_ROOT${NC}"
echo ""

# Check .env file exists
echo -e "${YELLOW}[1/5]${NC} Checking environment configuration..."
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: .env file not found at $ENV_FILE${NC}"
    echo -e "${YELLOW}Please create a .env file from .env.example${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} .env file found"
echo ""

# Check Python virtual environment
echo -e "${YELLOW}[2/5]${NC} Checking Python virtual environment..."
if [ ! -f "$VENV_PYTHON" ]; then
    echo -e "${RED}Error: Virtual environment not found at $PROJECT_ROOT/.venv${NC}"
    echo -e "${YELLOW}Run: python -m venv .venv && source .venv/bin/activate && pip install -e .${NC}"
    exit 1
fi
PYTHON_VERSION=$($VENV_PYTHON --version 2>&1)
echo -e "${GREEN}✓${NC} $PYTHON_VERSION (venv)"
echo ""

# Check dependencies
echo -e "${YELLOW}[3/5]${NC} Checking dependencies..."
if ! $VENV_PYTHON -c "import me4brain" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    cd "$PROJECT_ROOT" && $VENV_PYTHON -m pip install -e . > /dev/null 2>&1
fi
echo -e "${GREEN}✓${NC} Dependencies ready"
echo ""

# Verify debug mode is enabled
echo -e "${YELLOW}[4/5]${NC} Verifying debug mode..."
cd "$PROJECT_ROOT"
DEBUG_STATUS=$($VENV_PYTHON -c "
from me4brain.config import get_settings
settings = get_settings()
print('ENABLED' if settings.debug else 'DISABLED')
" 2>&1)

if [ "$DEBUG_STATUS" = "ENABLED" ]; then
    echo -e "${GREEN}✓${NC} Debug mode: ${GREEN}ENABLED${NC}"
else
    echo -e "${RED}✗${NC} Debug mode: ${RED}DISABLED${NC}"
    echo -e "${YELLOW}Warning: Authentication will require valid JWT tokens!${NC}"
    echo -e "${YELLOW}Set ME4BRAIN_DEBUG=true in .env to enable dev mode.${NC}"
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi
echo ""

# Display key configuration
echo -e "${YELLOW}[5/5]${NC} Key configuration:"
$VENV_PYTHON << 'EOF'
from me4brain.config import get_settings
settings = get_settings()
print(f"  Host: {settings.host}")
print(f"  Port: {settings.port}")
print(f"  Debug: {settings.debug}")
print(f"  Log Level: {settings.log_level}")
print(f"  Default Tenant: {settings.default_tenant_id}")
print(f"  Redis: {settings.redis_host}:{settings.redis_port}")
EOF
echo ""

echo -e "${GREEN}✓${NC} All checks passed"
echo ""

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║              Starting Me4BrAIn Backend                     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}Starting backend server...${NC}"
echo "Logs: $LOG_DIR/backend.log"
echo "URL: http://localhost:8089"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
echo ""

# Change to project root to ensure .env is loaded
cd "$PROJECT_ROOT"
export PYTHONPATH=$PYTHONPATH:$PROJECT_ROOT/src

# Run uvicorn from the venv
exec "$PROJECT_ROOT/.venv/bin/uvicorn" me4brain.api.main:app --host 0.0.0.0 --port 8089 2>&1 | tee "$LOG_DIR/backend.log"
