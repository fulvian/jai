#!/bin/bash

# Unified Intent Analysis Deployment Script
# This script automates the deployment process for real-world testing

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_ROOT/.env"
LOG_FILE="$PROJECT_ROOT/logs/deployment.log"

# Ensure logs directory exists
mkdir -p "$PROJECT_ROOT/logs"

# Logging function
log() {
    echo -e "${BLUE}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

# Check prerequisites
check_prerequisites() {
    log "Checking prerequisites..."
    
    # Check Python
    if ! command -v python &> /dev/null; then
        error "Python is not installed"
    fi
    log "✓ Python found: $(python --version)"
    
    # Check pytest
    if ! python -m pytest --version &> /dev/null; then
        error "pytest is not installed"
    fi
    log "✓ pytest found"
    
    # Check .env file
    if [ ! -f "$ENV_FILE" ]; then
        error ".env file not found at $ENV_FILE"
    fi
    log "✓ .env file found"
}

# Run tests
run_tests() {
    log "Running test suite..."
    
    cd "$PROJECT_ROOT"
    
    # Run unit tests
    log "Running unit tests..."
    if ! python -m pytest tests/engine/test_unified_intent_analyzer.py -v --tb=short; then
        error "Unit tests failed"
    fi
    success "Unit tests passed"
    
    # Run property-based tests
    log "Running property-based tests..."
    if ! python -m pytest tests/engine/test_unified_intent_properties.py -v --tb=short; then
        error "Property-based tests failed"
    fi
    success "Property-based tests passed"
    
    # Run integration tests
    log "Running integration tests..."
    if ! python -m pytest tests/engine/test_unified_intent_integration.py -v --tb=short; then
        error "Integration tests failed"
    fi
    success "Integration tests passed"
    
    # Run feature flag tests
    log "Running feature flag tests..."
    if ! python -m pytest tests/engine/test_feature_flags.py -v --tb=short; then
        error "Feature flag tests failed"
    fi
    success "Feature flag tests passed"
    
    # Run cache tests
    log "Running cache tests..."
    if ! python -m pytest tests/engine/test_intent_cache.py -v --tb=short; then
        error "Cache tests failed"
    fi
    success "Cache tests passed"
}

# Configure environment
configure_environment() {
    local phase=$1
    local traffic=$2
    
    log "Configuring environment for phase: $phase, traffic: $traffic%"
    
    # Backup current .env
    cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%s)"
    
    # Update .env file
    if grep -q "USE_UNIFIED_INTENT_ANALYZER" "$ENV_FILE"; then
        sed -i.bak "s/USE_UNIFIED_INTENT_ANALYZER=.*/USE_UNIFIED_INTENT_ANALYZER=true/" "$ENV_FILE"
    else
        echo "USE_UNIFIED_INTENT_ANALYZER=true" >> "$ENV_FILE"
    fi
    
    if grep -q "UNIFIED_INTENT_ROLLOUT_PHASE" "$ENV_FILE"; then
        sed -i.bak "s/UNIFIED_INTENT_ROLLOUT_PHASE=.*/UNIFIED_INTENT_ROLLOUT_PHASE=$phase/" "$ENV_FILE"
    else
        echo "UNIFIED_INTENT_ROLLOUT_PHASE=$phase" >> "$ENV_FILE"
    fi
    
    if grep -q "UNIFIED_INTENT_TRAFFIC_PERCENTAGE" "$ENV_FILE"; then
        sed -i.bak "s/UNIFIED_INTENT_TRAFFIC_PERCENTAGE=.*/UNIFIED_INTENT_TRAFFIC_PERCENTAGE=$traffic/" "$ENV_FILE"
    else
        echo "UNIFIED_INTENT_TRAFFIC_PERCENTAGE=$traffic" >> "$ENV_FILE"
    fi
    
    success "Environment configured"
}

# Verify configuration
verify_configuration() {
    log "Verifying configuration..."
    
    cd "$PROJECT_ROOT"
    
    python << 'EOF'
from me4brain.llm.config import get_llm_config
from me4brain.engine.feature_flags import get_feature_flag_manager

config = get_llm_config()
ffm = get_feature_flag_manager()

print(f"✓ USE_UNIFIED_INTENT_ANALYZER: {config.use_unified_intent_analyzer}")
print(f"✓ UNIFIED_INTENT_ROLLOUT_PHASE: {ffm.current_phase}")
print(f"✓ UNIFIED_INTENT_TRAFFIC_PERCENTAGE: {ffm.traffic_percentage}%")
print(f"✓ INTENT_ANALYSIS_TIMEOUT: {config.intent_analysis_timeout}s")
print(f"✓ INTENT_CACHE_TTL: {config.intent_cache_ttl}s")
print(f"✓ INTENT_ANALYSIS_MODEL: {config.intent_analysis_model}")
EOF
    
    success "Configuration verified"
}

# Display deployment status
display_status() {
    log "Deployment Status"
    echo ""
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║         Unified Intent Analysis Deployment Status         ║"
    echo "╠════════════════════════════════════════════════════════════╣"
    
    cd "$PROJECT_ROOT"
    
    python << 'EOF'
from me4brain.llm.config import get_llm_config
from me4brain.engine.feature_flags import get_feature_flag_manager
from me4brain.engine.intent_cache import get_intent_cache
from me4brain.engine.intent_monitoring import get_intent_monitor

config = get_llm_config()
ffm = get_feature_flag_manager()
cache = get_intent_cache()
monitor = get_intent_monitor()

print(f"║ Feature Flag Enabled:        {str(config.use_unified_intent_analyzer):40} ║")
print(f"║ Rollout Phase:               {str(ffm.current_phase.value):40} ║")
print(f"║ Traffic Percentage:          {str(f'{ffm.traffic_percentage}%'):40} ║")
print(f"║ Intent Analysis Timeout:     {str(f'{config.intent_analysis_timeout}s'):40} ║")
print(f"║ Cache TTL:                   {str(f'{config.intent_cache_ttl}s'):40} ║")
print(f"║ Cache Max Size:              {str('10000'):40} ║")

cache_stats = cache.get_stats()
print(f"║ Cache Hit Rate:              {str(f'{cache_stats.hit_rate:.1%}'):40} ║")
print(f"║ Cache Size:                  {str(f'{cache_stats.size} entries'):40} ║")

metrics = monitor.get_metrics()
print(f"║ Total Queries:               {str(metrics.get('total_queries', 0)):40} ║")
print(f"║ Error Rate:                  {str(f'{metrics.get(\"error_rate\", 0):.1%}'):40} ║")
print(f"║ Avg Latency:                 {str(f'{metrics.get(\"avg_latency_ms\", 0):.1f}ms'):40} ║")

print("╚════════════════════════════════════════════════════════════╝")
EOF
    
    echo ""
}

# Main deployment flow
main() {
    log "Starting Unified Intent Analysis Deployment"
    echo ""
    
    # Check prerequisites
    check_prerequisites
    echo ""
    
    # Run tests
    run_tests
    echo ""
    
    # Ask for deployment phase
    echo "Select deployment phase:"
    echo "1) Phase 1: Disabled (0% traffic)"
    echo "2) Phase 2: Canary (10% traffic)"
    echo "3) Phase 3: Beta (50% traffic)"
    echo "4) Phase 4: Production (100% traffic)"
    echo ""
    read -p "Enter choice (1-4): " choice
    
    case $choice in
        1)
            configure_environment "disabled" "0"
            ;;
        2)
            configure_environment "canary" "10"
            ;;
        3)
            configure_environment "beta" "50"
            ;;
        4)
            configure_environment "production" "100"
            ;;
        *)
            error "Invalid choice"
            ;;
    esac
    
    echo ""
    
    # Verify configuration
    verify_configuration
    echo ""
    
    # Display status
    display_status
    
    success "Deployment completed successfully!"
    log "Next steps:"
    log "1. Start the application: python -m me4brain.main"
    log "2. Monitor metrics using: python scripts/monitor_intent.py"
    log "3. Test with sample queries"
    log "4. Check logs in: logs/deployment.log"
}

# Run main function
main "$@"
