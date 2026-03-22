#!/bin/bash

################################################################################
# JAI Development Utilities
#
# Manages Docker services and provides helpful commands
#
# Usage:
#   ./dev-utils.sh logs                  Show Docker service logs
#   ./dev-utils.sh stop                  Stop all Docker services
#   ./dev-utils.sh restart               Restart all Docker services
#   ./dev-utils.sh clean                 Remove containers and volumes
#   ./dev-utils.sh status                Show service health status
#   ./dev-utils.sh db-shell              Connect to PostgreSQL shell
#   ./dev-utils.sh redis-shell           Connect to Redis CLI
#
################################################################################

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

show_help() {
    echo -e "${BLUE}JAI Development Utilities${NC}"
    echo ""
    echo "Usage: $0 <command>"
    echo ""
    echo "Commands:"
    echo "  logs              Show Docker service logs (live)"
    echo "  stop              Stop all Docker services"
    echo "  restart           Restart all Docker services"
    echo "  clean             Remove containers and volumes (data loss!)"
    echo "  status            Show service health status"
    echo "  db-shell          Connect to PostgreSQL shell"
    echo "  redis-shell       Connect to Redis CLI"
    echo "  qdrant-shell      Open Qdrant web console"
    echo ""
}

case "$1" in
    logs)
        echo -e "${BLUE}Showing Docker service logs...${NC}"
        docker-compose -f "$PROJECT_ROOT/docker-compose.dev.yml" logs -f
        ;;
    stop)
        echo -e "${YELLOW}Stopping Docker services...${NC}"
        docker-compose -f "$PROJECT_ROOT/docker-compose.dev.yml" stop
        echo -e "${GREEN}✓ Services stopped${NC}"
        ;;
    restart)
        echo -e "${YELLOW}Restarting Docker services...${NC}"
        docker-compose -f "$PROJECT_ROOT/docker-compose.dev.yml" restart
        echo -e "${GREEN}✓ Services restarted${NC}"
        ;;
    clean)
        echo -e "${RED}⚠ This will REMOVE all containers and data!${NC}"
        read -p "Are you sure? (yes/no): " -r
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker-compose -f "$PROJECT_ROOT/docker-compose.dev.yml" down -v
            echo -e "${GREEN}✓ Cleanup complete${NC}"
        else
            echo "Cancelled"
        fi
        ;;
    status)
        echo -e "${BLUE}Service Health Status:${NC}"
        docker-compose -f "$PROJECT_ROOT/docker-compose.dev.yml" ps
        ;;
    db-shell)
        echo -e "${BLUE}Connecting to PostgreSQL...${NC}"
        docker-compose -f "$PROJECT_ROOT/docker-compose.dev.yml" exec postgres psql -U jai_user -d me4brain
        ;;
    redis-shell)
        echo -e "${BLUE}Connecting to Redis CLI...${NC}"
        docker-compose -f "$PROJECT_ROOT/docker-compose.dev.yml" exec redis redis-cli
        ;;
    qdrant-shell)
        echo -e "${BLUE}Opening Qdrant web console...${NC}"
        echo "Qdrant Web UI: http://localhost:6333/dashboard"
        if command -v open &> /dev/null; then
            open http://localhost:6333/dashboard
        elif command -v xdg-open &> /dev/null; then
            xdg-open http://localhost:6333/dashboard
        else
            echo "Please open the URL in your browser"
        fi
        ;;
    *)
        show_help
        exit 1
        ;;
esac
