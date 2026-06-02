#!/usr/bin/env bash
# ==========================================================================
# RESTORE — Restore a backup artifact produced by backup.sh.
#
# Accepts a single backup file path as argv[1]. Prompts for [y/N]
# confirmation before any destructive action. Branches on filename:
#
#   db-*.sql.gz             — gunzip | psql into postgres
#   n8n-*.tar.gz            — tar extract into ./data/
#   session-*.tar.gz.enc    — openssl decrypt | tar extract into ./data/
#
# Usage: ./scripts/restore.sh <backup-file>
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
echo " PODCAST PIPELINE — RESTORE"
echo "=========================================="
echo ""

# --------------------------------------------------------------------------
# Load .env
# --------------------------------------------------------------------------
ENV_FILE="${PROJECT_DIR}/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}[ERROR] ${ENV_FILE} not found. Cannot run restore.${NC}"
    exit 1
fi
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

POSTGRES_USER="${POSTGRES_USER:-podcast}"
POSTGRES_DB="${POSTGRES_DB:-podcast}"

# --------------------------------------------------------------------------
# Validate argument
# --------------------------------------------------------------------------
if [ $# -lt 1 ] || [ -z "${1:-}" ]; then
    echo -e "${RED}[ERROR] Usage: $0 <backup-file>${NC}"
    echo ""
    echo "Available backups:"
    ls -lht "${PROJECT_DIR}/backups/" 2>/dev/null | tail -n +2 | head -20 \
        | awk '{print "  " $0}' || echo "  (no backups found)"
    exit 1
fi

BACKUP_FILE="$1"

if [ ! -f "$BACKUP_FILE" ]; then
    echo -e "${RED}[ERROR] File not found: ${BACKUP_FILE}${NC}"
    exit 1
fi

# --------------------------------------------------------------------------
# Confirmation prompt
# --------------------------------------------------------------------------
echo -e "${YELLOW}[WARN] This will overwrite current data with: ${BACKUP_FILE}${NC}"
printf "Proceed? [y/N] "
read -r CONFIRM
if [ "${CONFIRM}" != "y" ] && [ "${CONFIRM}" != "Y" ]; then
    echo "[INFO] Restore cancelled."
    exit 0
fi

cd "$PROJECT_DIR"

# --------------------------------------------------------------------------
# Branch on filename pattern
# --------------------------------------------------------------------------
BASENAME="$(basename "$BACKUP_FILE")"

case "$BASENAME" in
    db-*.sql.gz)
        echo "[INFO] Restoring postgres dump..."
        gunzip -c "$BACKUP_FILE" \
            | docker compose exec -T postgres \
                psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
        echo -e "${GREEN}[OK] Postgres restore complete.${NC}"
        ;;

    n8n-*.tar.gz)
        echo "[INFO] Restoring n8n data directory..."
        tar -xzf "$BACKUP_FILE" -C "$PROJECT_DIR"
        echo -e "${GREEN}[OK] n8n restore complete.${NC}"
        ;;

    session-*.tar.gz.enc)
        if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
            echo -e "${RED}[ERROR] BACKUP_PASSPHRASE is not set in .env. Cannot decrypt session backup.${NC}"
            exit 1
        fi
        echo "[INFO] Decrypting and restoring session state..."
        openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE \
            -in "$BACKUP_FILE" \
            | tar -xz -C "$PROJECT_DIR"
        # Re-apply strict permissions on restored session files
        chmod 700 "${PROJECT_DIR}/data/session" 2>/dev/null || true
        chmod 600 "${PROJECT_DIR}/data/session/storageState.json" 2>/dev/null || true
        echo -e "${GREEN}[OK] Session restore complete.${NC}"
        ;;

    *)
        echo -e "${RED}[ERROR] Unrecognised backup filename pattern: ${BASENAME}${NC}"
        echo "  Expected: db-*.sql.gz | n8n-*.tar.gz | session-*.tar.gz.enc"
        exit 1
        ;;
esac

echo ""
echo "=========================================="
echo " Restore complete."
echo "=========================================="
echo ""
