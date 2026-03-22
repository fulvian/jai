#!/bin/bash
#
# Telegram Health Check Script
# Monitors the gateway and restarts it if Telegram stops responding.
#
# Usage: ./telegram-health-check.sh
# Install as LaunchAgent for automatic execution every 5 minutes.
#

set -euo pipefail

# === Configuration ===
GATEWAY_URL="http://localhost:3030"
GATEWAY_DIR="/Users/fulvioventura/persan/packages/gateway"
ENV_FILE="/Users/fulvioventura/persan/.env"
LOG_FILE="/tmp/telegram-health-check.log"
PID_FILE="/tmp/gateway.pid"
MAX_RESTART_ATTEMPTS=3
HEALTH_TIMEOUT=10

# === Logging ===
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ❌ ERROR: $1" | tee -a "$LOG_FILE" >&2
}

# === Health Checks ===
check_gateway_health() {
    local response
    response=$(curl -s --max-time "$HEALTH_TIMEOUT" "${GATEWAY_URL}/health" 2>/dev/null || echo "FAILED")
    
    if [[ "$response" == "FAILED" ]]; then
        log_error "Gateway health endpoint not responding"
        return 1
    fi
    
    # Check if response contains healthy status
    if echo "$response" | grep -q '"status":"healthy"'; then
        return 0
    else
        log_error "Gateway health check returned unhealthy: $response"
        return 1
    fi
}

check_telegram_bot() {
    # Load Telegram token from .env
    local token
    token=$(grep "TELEGRAM_BOT_TOKEN" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 | tr -d '"' | tr -d "'")
    
    if [[ -z "$token" ]]; then
        log "⚠️  TELEGRAM_BOT_TOKEN not found in .env, skipping bot check"
        return 0
    fi
    
    # Call Telegram getMe to verify bot is valid
    local response
    response=$(curl -s --max-time "$HEALTH_TIMEOUT" "https://api.telegram.org/bot${token}/getMe" 2>/dev/null || echo "FAILED")
    
    if [[ "$response" == "FAILED" ]]; then
        log_error "Cannot reach Telegram API"
        return 1
    fi
    
    if echo "$response" | grep -q '"ok":true'; then
        local username
        username=$(echo "$response" | grep -o '"username":"[^"]*"' | cut -d'"' -f4)
        log "✅ Telegram bot @${username} is valid"
        return 0
    else
        log_error "Telegram bot check failed: $response"
        return 1
    fi
}

check_gateway_process() {
    if pgrep -f "gateway.*src/index.ts" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# === Gateway Management ===
get_gateway_pid() {
    pgrep -f "gateway.*src/index.ts" 2>/dev/null | head -1 || echo ""
}

stop_gateway() {
    log "🛑 Stopping gateway..."
    local pid
    pid=$(get_gateway_pid)
    
    if [[ -n "$pid" ]]; then
        kill "$pid" 2>/dev/null || true
        sleep 2
        
        # Force kill if still running
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
            sleep 1
        fi
        log "Gateway stopped (PID: $pid)"
    else
        log "Gateway was not running"
    fi
}

start_gateway() {
    log "🚀 Starting gateway..."
    
    cd "$GATEWAY_DIR"
    
    # Start gateway in background
    nohup npx tsx --env-file="$ENV_FILE" src/index.ts > /tmp/gateway.log 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$PID_FILE"
    
    # Wait for startup
    sleep 5
    
    if check_gateway_health; then
        log "✅ Gateway started successfully (PID: $new_pid)"
        return 0
    else
        log_error "Gateway failed to start properly"
        return 1
    fi
}

restart_gateway() {
    log "🔄 Restarting gateway..."
    stop_gateway
    start_gateway
}

# === Main Logic ===
main() {
    log "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    log "Starting Telegram Health Check"
    
    local needs_restart=false
    local restart_reason=""
    
    # Check 1: Gateway process running?
    if ! check_gateway_process; then
        needs_restart=true
        restart_reason="Gateway process not running"
    fi
    
    # Check 2: Gateway health endpoint responding?
    if [[ "$needs_restart" == "false" ]] && ! check_gateway_health; then
        needs_restart=true
        restart_reason="Gateway health check failed"
    fi
    
    # Check 3: Telegram bot valid? (just informational, won't trigger restart)
    check_telegram_bot || true
    
    # Restart if needed
    if [[ "$needs_restart" == "true" ]]; then
        log_error "Restart needed: $restart_reason"
        
        local attempt=1
        while [[ $attempt -le $MAX_RESTART_ATTEMPTS ]]; do
            log "Restart attempt $attempt of $MAX_RESTART_ATTEMPTS..."
            
            if restart_gateway; then
                log "✅ Gateway successfully restarted!"
                break
            else
                log_error "Restart attempt $attempt failed"
                ((attempt++))
                sleep 5
            fi
        done
        
        if [[ $attempt -gt $MAX_RESTART_ATTEMPTS ]]; then
            log_error "CRITICAL: Failed to restart gateway after $MAX_RESTART_ATTEMPTS attempts!"
            exit 1
        fi
    else
        log "✅ All health checks passed - gateway is healthy"
    fi
    
    log "Health check complete"
}

# Run main
main "$@"
