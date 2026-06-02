#!/usr/bin/env bash
# ==========================================================================
# BACKUP — Create timestamped backups of postgres DB, n8n data, and the
#          session state (AES-256-CBC encrypted).
#
# Artifacts written to ../backups/:
#   db-YYYYMMDD-HHMMSS.sql.gz          — podcast schema SQL dump
#   n8n-YYYYMMDD-HHMMSS.tar.gz         — n8n data directory
#   session-YYYYMMDD-HHMMSS.tar.gz.enc — encrypted session state
#
# Files older than 7 days are pruned automatically.
# BACKUP_PASSPHRASE must be set in .env (exit 1 if missing).
#
# Usage: ./scripts/backup.sh
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
echo " PODCAST PIPELINE — BACKUP"
echo "=========================================="
echo ""

# --------------------------------------------------------------------------
# Load .env
# --------------------------------------------------------------------------
ENV_FILE="${PROJECT_DIR}/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}[ERROR] ${ENV_FILE} not found. Cannot run backup.${NC}"
    exit 1
fi
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

# --------------------------------------------------------------------------
# Guard: BACKUP_PASSPHRASE must be set and non-empty
# --------------------------------------------------------------------------
if [ -z "${BACKUP_PASSPHRASE:-}" ]; then
    echo -e "${RED}[ERROR] BACKUP_PASSPHRASE is not set in .env. Aborting backup.${NC}"
    exit 1
fi

POSTGRES_USER="${POSTGRES_USER:-podcast}"
POSTGRES_DB="${POSTGRES_DB:-podcast}"

BACKUP_DIR="${PROJECT_DIR}/backups"
mkdir -p "$BACKUP_DIR"

TIMESTAMP="$(date +%Y%m%d-%H%M%S)"

cd "$PROJECT_DIR"

# --------------------------------------------------------------------------
# 1. PostgreSQL dump (podcast schema only)
# --------------------------------------------------------------------------
echo "[INFO] Dumping postgres schema 'podcast'..."
DB_BACKUP="${BACKUP_DIR}/db-${TIMESTAMP}.sql.gz"
docker compose exec -T postgres \
    pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --schema=podcast \
    | gzip > "$DB_BACKUP"
echo -e "${GREEN}[OK] ${DB_BACKUP}${NC}"

# --------------------------------------------------------------------------
# 2. n8n data directory
# --------------------------------------------------------------------------
echo "[INFO] Archiving n8n data..."
N8N_BACKUP="${BACKUP_DIR}/n8n-${TIMESTAMP}.tar.gz"
tar -czf "$N8N_BACKUP" -C "$PROJECT_DIR" data/n8n
echo -e "${GREEN}[OK] ${N8N_BACKUP}${NC}"

# --------------------------------------------------------------------------
# 3. Session state (encrypted)
# --------------------------------------------------------------------------
echo "[INFO] Archiving and encrypting session state..."
SESSION_BACKUP="${BACKUP_DIR}/session-${TIMESTAMP}.tar.gz.enc"
tar -cz -C "$PROJECT_DIR" data/session \
    | openssl enc -aes-256-cbc -pbkdf2 -pass env:BACKUP_PASSPHRASE \
    > "$SESSION_BACKUP"
echo -e "${GREEN}[OK] ${SESSION_BACKUP}${NC}"

# --------------------------------------------------------------------------
# 4. Prune backups older than 7 days
# --------------------------------------------------------------------------
echo "[INFO] Pruning backup files older than 7 days..."
find "$BACKUP_DIR" -type f -mtime +7 -delete
echo -e "${GREEN}[OK] Pruning done.${NC}"

echo ""
echo "=========================================="
echo " Backup complete: ${TIMESTAMP}"
echo "=========================================="
echo ""
