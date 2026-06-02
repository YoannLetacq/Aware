#!/usr/bin/env bash
# ==========================================================================
# RESTART — Stop then start the podcast pipeline stack.
#
# Delegates to stop.sh and start.sh in the same scripts directory so all
# preflight checks defined in start.sh are re-executed on the way up.
#
# Usage: ./scripts/restart.sh
# ==========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --------------------------------------------------------------------------
# Color helpers
# --------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "=========================================="
echo " PODCAST PIPELINE — RESTART"
echo "=========================================="
echo ""

"${SCRIPT_DIR}/stop.sh"
"${SCRIPT_DIR}/start.sh"
