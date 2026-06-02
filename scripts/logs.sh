#!/usr/bin/env bash
# ==========================================================================
# LOGS — Stream logs from all services or a single named service.
#
# Passes an optional service name as $1 to docker compose logs.
# With no argument, streams logs from all services.
#
# Usage: ./scripts/logs.sh [service]
#   Examples:
#     ./scripts/logs.sh            # all services
#     ./scripts/logs.sh postgres
#     ./scripts/logs.sh worker
#     ./scripts/logs.sh n8n
# ==========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# --------------------------------------------------------------------------
# Color helpers
# --------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SERVICE="${1:-}"

echo ""
echo "=========================================="
if [ -n "$SERVICE" ]; then
    echo " PODCAST PIPELINE — LOGS: ${SERVICE}"
else
    echo " PODCAST PIPELINE — LOGS: all services"
fi
echo "=========================================="
echo -e "${YELLOW}[INFO] Press Ctrl+C to stop following.${NC}"
echo ""

cd "$PROJECT_DIR"

# shellcheck disable=SC2086
docker compose logs -f --tail=200 ${SERVICE}
