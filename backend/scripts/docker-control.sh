#!/bin/bash
# =============================================================================
# Me4BrAIn Docker Control Script
# =============================================================================
# Usage: ./docker-control.sh [command] [profile]
#
# Commands:
#   start [profile]   - Start containers
#   stop              - Stop all containers
#   restart [profile] - Restart containers
#   logs [service]    - Show logs
#   status            - Show container status
#   clean             - Remove volumes and containers
#
# Profiles:
#   infra      - Solo infrastruttura (default)
#   app        - Infrastruttura + API
#   full       - Stack completo + Keycloak
#   monitoring - + Prometheus/Grafana
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="$SCRIPT_DIR/../docker/docker-compose.yml"
ENV_FILE="$SCRIPT_DIR/../.env"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check Docker is running
check_docker() {
    if ! docker info > /dev/null 2>&1; then
        log_error "Docker is not running. Please start Docker first."
        exit 1
    fi
}

# Start containers
start() {
    local profile="${1:-infra}"
    
    check_docker
    log_info "Starting Me4BrAIn with profile: $profile"
    
    case $profile in
        infra)
            docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d
            ;;
        app)
            docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" --profile app up -d
            ;;
        full)
            docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" --profile full up -d
            ;;
        monitoring)
            docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" --profile monitoring up -d
            ;;
        all)
            docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" --profile full --profile monitoring up -d
            ;;
        *)
            log_error "Unknown profile: $profile"
            echo "Available profiles: infra, app, full, monitoring, all"
            exit 1
            ;;
    esac

    
    log_info "Waiting for services to be healthy..."
    sleep 5
    status
}

# Stop containers
stop() {
    check_docker
    log_info "Stopping all Me4BrAIn containers..."
    docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" --profile app --profile full --profile monitoring --profile auth down
}

# Restart containers
restart() {
    stop
    start "${1:-infra}"
}

# Show logs
logs() {
    local service="${1:-}"
    
    if [ -z "$service" ]; then
        docker compose -f "$COMPOSE_FILE" logs -f --tail=100
    else
        docker compose -f "$COMPOSE_FILE" logs -f --tail=100 "$service"
    fi
}

# Show status
status() {
    echo ""
    echo "=== Me4BrAIn Container Status ==="
    echo ""
    docker compose -f "$COMPOSE_FILE" ps
    echo ""
    echo "=== Resource Usage ==="
    echo ""
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | grep me4brain || true
}

# Clean everything
clean() {
    log_warn "This will remove all containers and volumes!"
    read -p "Are you sure? (y/N): " confirm
    
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        stop 2>/dev/null || true
        log_info "Removing volumes..."
        docker compose -f "$COMPOSE_FILE" down -v
        log_info "Cleanup complete."
    else
        log_info "Cancelled."
    fi
}

# Health check
health() {
    echo ""
    echo "=== Service Health Checks ==="
    echo ""
    
    # PostgreSQL
    if docker exec me4brain-postgres pg_isready -U me4brain > /dev/null 2>&1; then
        echo -e "PostgreSQL: ${GREEN}✓ Healthy${NC}"
    else
        echo -e "PostgreSQL: ${RED}✗ Unhealthy${NC}"
    fi
    
    # Redis
    if docker exec me4brain-redis redis-cli ping > /dev/null 2>&1; then
        echo -e "Redis:      ${GREEN}✓ Healthy${NC}"
    else
        echo -e "Redis:      ${RED}✗ Unhealthy${NC}"
    fi
    
    # Qdrant
    if curl -sf http://localhost:6334/readyz > /dev/null 2>&1; then
        echo -e "Qdrant:     ${GREEN}✓ Healthy${NC}"
    else
        echo -e "Qdrant:     ${RED}✗ Unhealthy${NC}"
    fi
    
    # Neo4j
    if curl -sf http://localhost:7478 > /dev/null 2>&1; then
        echo -e "Neo4j:      ${GREEN}✓ Healthy${NC}"
    else
        echo -e "Neo4j:      ${RED}✗ Unhealthy${NC}"
    fi
    
    # API (se in profile app)
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "Me4BrAIn:   ${GREEN}✓ Healthy${NC}"
    else
        echo -e "Me4BrAIn:   ${YELLOW}○ Not running${NC}"
    fi
    
    echo ""
}

# Print usage
usage() {
    echo "Usage: $0 [command] [options]"
    echo ""
    echo "Commands:"
    echo "  start [profile]   Start containers (default: infra)"
    echo "  stop              Stop all containers"
    echo "  restart [profile] Restart containers"
    echo "  logs [service]    Show logs (optional: specific service)"
    echo "  status            Show container status"
    echo "  health            Check service health"
    echo "  clean             Remove containers and volumes"
    echo ""
    echo "Profiles:"
    echo "  infra      Only infrastructure (postgres, redis, qdrant, neo4j)"
    echo "  app        Infrastructure + Me4BrAIn API"
    echo "  full       Complete stack + Keycloak"
    echo "  monitoring Add Prometheus/Grafana"
    echo "  all        Everything"
}

# Main
case "${1:-help}" in
    start)
        start "${2:-infra}"
        ;;
    stop)
        stop
        ;;
    restart)
        restart "${2:-infra}"
        ;;
    logs)
        logs "$2"
        ;;
    status)
        status
        ;;
    health)
        health
        ;;
    clean)
        clean
        ;;
    help|--help|-h)
        usage
        ;;
    *)
        log_error "Unknown command: $1"
        usage
        exit 1
        ;;
esac
