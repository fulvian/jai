#!/bin/bash
# =============================================================================
# Setup Docker Auto-Maintenance Crontab
# =============================================================================
# Configura pulizia automatica Docker alle 3am ogni giorno
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MAINTENANCE_SCRIPT="$SCRIPT_DIR/docker-maintenance.sh"
LOG_FILE="/tmp/docker-maintenance.log"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}Setting up Docker auto-maintenance crontab...${NC}"

# Check script exists
if [ ! -f "$MAINTENANCE_SCRIPT" ]; then
    echo -e "${YELLOW}Error: docker-maintenance.sh not found at $MAINTENANCE_SCRIPT${NC}"
    exit 1
fi

# Make sure it's executable
chmod +x "$MAINTENANCE_SCRIPT"

# Add crontab entry (remove old ones first)
(crontab -l 2>/dev/null | grep -v "docker-maintenance" || true; \
 echo "0 3 * * * $MAINTENANCE_SCRIPT auto >> $LOG_FILE 2>&1") | crontab -

echo -e "${GREEN}✅ Crontab configured successfully!${NC}"
echo ""
echo "Scheduled task:"
crontab -l 2>/dev/null | grep docker-maintenance || echo "  (none found)"
echo ""
echo "Log file: $LOG_FILE"
echo ""
echo "To test manually: $MAINTENANCE_SCRIPT auto"
