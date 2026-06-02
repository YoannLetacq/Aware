#!/usr/bin/env bash
# ==========================================================================
# STOP — Bring down the podcast pipeline stack (preserves volumes/data).
#
# Runs `docker compose down` without -v so persistent data in ./data/ and
# named volumes are kept intact.
#
# Usage: ./scripts/stop.sh
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

echo ""
echo "=========================================="
echo " PODCAST PIPELINE — STOP"
echo "=========================================="
echo ""

cd "$PROJECT_DIR"

echo "[INFO] Stopping all services (data volumes preserved)..."
docker compose down

echo ""
echo -e "${GREEN}[OK] Stack stopped.${NC}"
echo -e "${YELLOW}[INFO] Persistent data is retained in ./data/.${NC}"
echo "  To restart: ./scripts/start.sh"
echo ""
