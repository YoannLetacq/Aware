#!/usr/bin/env bash
# ==========================================================================
# STATUS — Show container states and podcast.jobs statistics.
#
# Prints docker compose ps output, then queries podcast.jobs for a status
# breakdown. The SQL query is silently skipped if postgres is not running.
#
# Usage: ./scripts/status.sh
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
echo " PODCAST PIPELINE — STATUS"
echo "=========================================="
echo ""

cd "$PROJECT_DIR"

# --------------------------------------------------------------------------
# Load .env for DB credentials
# --------------------------------------------------------------------------
ENV_FILE="${PROJECT_DIR}/.env"
if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck source=/dev/null
    source "$ENV_FILE"
    set +a
else
    echo -e "${YELLOW}[WARN] ${ENV_FILE} not found; DB query will be skipped.${NC}"
fi

POSTGRES_USER="${POSTGRES_USER:-podcast}"
POSTGRES_DB="${POSTGRES_DB:-podcast}"

# --------------------------------------------------------------------------
# Container status
# --------------------------------------------------------------------------
echo "--- Containers ---"
docker compose ps
echo ""

# --------------------------------------------------------------------------
# podcast.jobs statistics (silently skip if postgres not up)
# --------------------------------------------------------------------------
echo "--- podcast.jobs by status ---"
if docker compose exec -T postgres \
       psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
       -c "SELECT status, COUNT(*) FROM podcast.jobs GROUP BY status ORDER BY 1;" \
       2>/dev/null; then
    : # query succeeded
else
    echo -e "${YELLOW}[SKIP] postgres not available — skipping DB query.${NC}"
fi

echo ""
echo "=========================================="
echo ""
