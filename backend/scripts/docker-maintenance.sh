#!/bin/bash
# =============================================================================
# Docker Maintenance Script - Pulizia Automatica e Monitoraggio
# =============================================================================
# Installazione:
#   chmod +x scripts/docker-maintenance.sh
#   crontab -e -> 0 3 * * * /path/to/scripts/docker-maintenance.sh cleanup >> /var/log/docker-maintenance.log 2>&1
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="${SCRIPT_DIR}/../logs/docker-maintenance.log"
DISK_THRESHOLD=80  # Percentuale di utilizzo disco per alert
MEMORY_THRESHOLD=80  # Percentuale RAM container per warning

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
    log "INFO: $1" >> "$LOG_FILE" 2>/dev/null || true
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
    log "WARN: $1" >> "$LOG_FILE" 2>/dev/null || true
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
    log "ERROR: $1" >> "$LOG_FILE" 2>/dev/null || true
}

# =============================================================================
# CLEANUP FUNCTIONS
# =============================================================================

cleanup_light() {
    log_info "Starting light cleanup..."
    
    # Remove stopped containers
    local containers=$(docker container prune -f 2>/dev/null | grep "Total reclaimed space" || echo "0B")
    log_info "Containers cleanup: $containers"
    
    # Remove dangling images
    local images=$(docker image prune -f 2>/dev/null | grep "Total reclaimed space" || echo "0B")
    log_info "Dangling images cleanup: $images"
    
    # Remove build cache older than 24h (prevents 45GB+ accumulation)
    local cache=$(docker builder prune -f --filter "until=24h" 2>/dev/null | grep "Total reclaimed space" || echo "0B")
    log_info "Build cache cleanup: $cache"
    
    # Remove unused networks
    docker network prune -f 2>/dev/null || true
    log_info "Networks pruned"
}

cleanup_medium() {
    log_info "Starting medium cleanup..."
    cleanup_light
    
    # Remove images older than 7 days
    docker image prune -af --filter "until=168h" 2>/dev/null || true
    log_info "Old images (7+ days) removed"
    
    # Clean build cache
    local cache=$(docker builder prune -f 2>/dev/null | grep "Total reclaimed space" || echo "0B")
    log_info "Build cache cleanup: $cache"
}

cleanup_aggressive() {
    log_warn "Starting aggressive cleanup (removes ALL unused resources)..."
    
    # Full system prune with volumes
    local total=$(docker system prune -af --volumes 2>/dev/null | grep "Total reclaimed space" || echo "0B")
    log_info "Aggressive cleanup complete: $total"
}

# =============================================================================
# MONITORING FUNCTIONS
# =============================================================================

check_disk_usage() {
    log_info "=== Docker Disk Usage ==="
    
    # Docker disk usage
    docker system df
    
    # Check if disk is above threshold
    if command -v df &> /dev/null; then
        local docker_disk=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo "/var/lib/docker")
        local usage=$(df -h "$docker_disk" 2>/dev/null | awk 'NR==2 {print $5}' | tr -d '%' || echo "0")
        
        if [ "$usage" -gt "$DISK_THRESHOLD" ]; then
            log_warn "Disk usage at ${usage}% (threshold: ${DISK_THRESHOLD}%)"
            log_warn "Consider running: $0 cleanup-medium"
            return 1
        else
            log_info "Disk usage OK: ${usage}%"
        fi
    fi
}

check_container_resources() {
    log_info "=== Container Resource Usage ==="
    
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" | grep me4brain || true
    
    # Check for high memory containers
    docker stats --no-stream --format "{{.Name}}\t{{.MemPerc}}" 2>/dev/null | while read line; do
        local name=$(echo "$line" | cut -f1)
        local mem=$(echo "$line" | cut -f2 | tr -d '%' | cut -d'.' -f1)
        
        if [ -n "$mem" ] && [ "$mem" -gt "$MEMORY_THRESHOLD" ]; then
            log_warn "Container $name using ${mem}% memory"
        fi
    done
}

check_container_health() {
    log_info "=== Container Health Status ==="
    
    docker ps --format "table {{.Names}}\t{{.Status}}" | grep me4brain || true
    
    # Check for unhealthy containers
    local unhealthy=$(docker ps --filter "health=unhealthy" --format "{{.Names}}" 2>/dev/null | grep me4brain || true)
    
    if [ -n "$unhealthy" ]; then
        log_warn "Unhealthy containers: $unhealthy"
    else
        log_info "All containers healthy"
    fi
}

show_summary() {
    echo ""
    echo "=================================="
    echo "   Me4BrAIn Docker Status"
    echo "=================================="
    echo ""
    check_disk_usage
    echo ""
    check_container_resources
    echo ""
    check_container_health
}

# =============================================================================
# AUTO-MAINTENANCE (for cron)
# =============================================================================

auto_maintenance() {
    log_info "=== Auto-maintenance started ==="
    
    # Check disk usage
    local docker_disk=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo "/var/lib/docker")
    local usage=0
    
    if command -v df &> /dev/null; then
        usage=$(df "$docker_disk" 2>/dev/null | awk 'NR==2 {print $5}' | tr -d '%' || echo "0")
    fi
    
    log_info "Current disk usage: ${usage}%"
    
    if [ "$usage" -gt 90 ]; then
        log_warn "Disk > 90%, running aggressive cleanup"
        cleanup_aggressive
    elif [ "$usage" -gt 75 ]; then
        log_warn "Disk > 75%, running medium cleanup"
        cleanup_medium
    elif [ "$usage" -gt 60 ]; then
        log_info "Disk > 60%, running light cleanup"
        cleanup_light
    else
        log_info "Disk usage OK, skipping cleanup"
    fi
    
    log_info "=== Auto-maintenance complete ==="
}

# =============================================================================
# USAGE
# =============================================================================

usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  status            Show full system status"
    echo "  cleanup-light     Remove stopped containers and dangling images"
    echo "  cleanup-medium    Light + old images + build cache"
    echo "  cleanup-aggressive Remove ALL unused resources (careful!)"
    echo "  auto              Automatic cleanup based on disk usage"
    echo "  disk              Show disk usage only"
    echo "  resources         Show container resource usage"
    echo "  health            Check container health"
    echo ""
    echo "Cron example (daily at 3am):"
    echo "  0 3 * * * $0 auto >> /var/log/docker-maintenance.log 2>&1"
}

# =============================================================================
# MAIN
# =============================================================================

# Create logs directory
mkdir -p "${SCRIPT_DIR}/../logs" 2>/dev/null || true

case "${1:-status}" in
    status)
        show_summary
        ;;
    cleanup-light)
        cleanup_light
        ;;
    cleanup-medium)
        cleanup_medium
        ;;
    cleanup-aggressive)
        cleanup_aggressive
        ;;
    auto)
        auto_maintenance
        ;;
    disk)
        check_disk_usage
        ;;
    resources)
        check_container_resources
        ;;
    health)
        check_container_health
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
