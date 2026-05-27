#!/usr/bin/env bash
# ==========================================================================
# SETUP — Idempotent environment initialisation for the podcast pipeline.
#
# Generates ../.env from ../env.template (skips if .env already exists),
# substitutes auto-generated secrets, creates data directories, and
# verifies Docker prerequisites.
#
# Usage: ./scripts/setup.sh
# ==========================================================================

set -euo pipefail

# --------------------------------------------------------------------------
# Resolve project root (one level above this script)
# --------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# --------------------------------------------------------------------------
# Color helpers
# --------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# --------------------------------------------------------------------------
# Verify Docker prerequisites
# --------------------------------------------------------------------------
echo ""
echo "=========================================="
echo " PODCAST PIPELINE — SETUP"
echo "=========================================="
echo ""

if ! command -v docker &>/dev/null; then
    echo -e "${RED}[ERROR] docker not found in PATH. Please install Docker.${NC}"
    exit 1
fi

if ! docker compose version &>/dev/null; then
    echo -e "${RED}[ERROR] 'docker compose' plugin not found. Please install docker-compose-plugin.${NC}"
    exit 1
fi

echo -e "${GREEN}[OK] docker and docker compose found.${NC}"

# --------------------------------------------------------------------------
# Generate .env (idempotent: skip if already present)
# --------------------------------------------------------------------------
ENV_FILE="${PROJECT_DIR}/.env"
TEMPLATE_FILE="${PROJECT_DIR}/env.template"

if [ -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}[SKIP] ${ENV_FILE} already exists — not overwriting.${NC}"
else
    if [ ! -f "$TEMPLATE_FILE" ]; then
        echo -e "${RED}[ERROR] ${TEMPLATE_FILE} not found. Cannot generate .env.${NC}"
        exit 1
    fi

    echo "[INFO] Generating ${ENV_FILE} from template..."
    cp "$TEMPLATE_FILE" "$ENV_FILE"

    # Generate secrets
    POSTGRES_PASSWORD="$(openssl rand -base64 32)"
    N8N_ENCRYPTION_KEY="$(openssl rand -hex 32)"
    N8N_API_KEY="$(openssl rand -hex 32)"
    REDIS_PASSWORD="$(openssl rand -base64 32)"
    WORKER_SHARED_TOKEN="$(openssl rand -base64 32)"
    BACKUP_PASSPHRASE="$(openssl rand -base64 32)"

    # Substitute placeholders (use | as delimiter to avoid clashing with base64 / chars)
    sed -i "s|POSTGRES_PASSWORD=.*CHANGEME.*|POSTGRES_PASSWORD=${POSTGRES_PASSWORD}|" "$ENV_FILE"
    sed -i "s|N8N_ENCRYPTION_KEY=.*CHANGEME.*|N8N_ENCRYPTION_KEY=${N8N_ENCRYPTION_KEY}|" "$ENV_FILE"
    sed -i "s|N8N_API_KEY=.*CHANGEME.*|N8N_API_KEY=${N8N_API_KEY}|" "$ENV_FILE"
    sed -i "s|REDIS_PASSWORD=.*CHANGEME.*|REDIS_PASSWORD=${REDIS_PASSWORD}|" "$ENV_FILE"
    sed -i "s|WORKER_SHARED_TOKEN=.*CHANGEME.*|WORKER_SHARED_TOKEN=${WORKER_SHARED_TOKEN}|" "$ENV_FILE"
    sed -i "s|BACKUP_PASSPHRASE=.*CHANGEME.*|BACKUP_PASSPHRASE=${BACKUP_PASSPHRASE}|" "$ENV_FILE"

    # Restrict permissions
    chmod 600 "$ENV_FILE"

    echo -e "${GREEN}[OK] ${ENV_FILE} created and secured (chmod 600).${NC}"
    echo -e "${YELLOW}[ACTION REQUIRED] Edit ${ENV_FILE} and fill in:${NC}"
    echo "         DISCORD_BOT_TOKEN, DISCORD_APP_ID, DISCORD_PUBLIC_KEY,"
    echo "         GEMINI_API_KEY, GOOGLE_BURNER_EMAIL, GOOGLE_BURNER_PASSWORD, TOTP_SEED"
fi

# --------------------------------------------------------------------------
# Create data directories
# --------------------------------------------------------------------------
echo "[INFO] Creating data directories..."

DATA_DIR="${PROJECT_DIR}/data"

mkdir -p "${DATA_DIR}/postgres"
mkdir -p "${DATA_DIR}/redis"
mkdir -p "${DATA_DIR}/n8n"
mkdir -p "${DATA_DIR}/artifacts"
mkdir -p "${DATA_DIR}/debug"
chmod 755 "${DATA_DIR}/postgres" "${DATA_DIR}/redis" "${DATA_DIR}/n8n" \
          "${DATA_DIR}/artifacts" "${DATA_DIR}/debug"

# session directory requires stricter permissions (H4)
mkdir -p "${DATA_DIR}/session"
chmod 700 "${DATA_DIR}/session"

# Ensure storageState.json placeholder exists with restricted mode
SESSION_FILE="${DATA_DIR}/session/storageState.json"
if [ ! -f "$SESSION_FILE" ]; then
    touch "$SESSION_FILE"
    chmod 600 "$SESSION_FILE"
    echo -e "${GREEN}[OK] Created ${SESSION_FILE} (chmod 600).${NC}"
else
    echo -e "${YELLOW}[SKIP] ${SESSION_FILE} already exists.${NC}"
fi

# Ensure backups directory exists
mkdir -p "${PROJECT_DIR}/backups"

echo -e "${GREEN}[OK] Data directories ready.${NC}"
echo ""
echo "=========================================="
echo " Setup complete. Next steps:"
echo "   1. Fill in secrets in .env"
echo "   2. Run: ./scripts/start.sh"
echo "=========================================="
echo ""
