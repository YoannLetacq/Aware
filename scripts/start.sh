#!/usr/bin/env bash
# ==========================================================================
# START — Preflight checks then bring up the podcast pipeline stack.
#
# Verifies: .env present, Docker daemon up, required ports free.
# Then starts all services and waits for postgres + redis healthchecks
# using docker inspect --format to read Health.Status directly.
#
# Usage: ./scripts/start.sh
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
echo " PODCAST PIPELINE — START"
echo "=========================================="
echo ""

# --------------------------------------------------------------------------
# Preflight: .env must exist
# --------------------------------------------------------------------------
ENV_FILE="${PROJECT_DIR}/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}[ERROR] ${ENV_FILE} not found. Run ./scripts/setup.sh first.${NC}"
    exit 1
fi

# Load env for port variables
set -a
# shellcheck source=/dev/null
source "$ENV_FILE"
set +a

# --------------------------------------------------------------------------
# Preflight: Docker daemon must be reachable
# --------------------------------------------------------------------------
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}[ERROR] Docker daemon is not running. Start Docker and retry.${NC}"
    exit 1
fi
echo -e "${GREEN}[OK] Docker daemon reachable.${NC}"

# --------------------------------------------------------------------------
# Preflight: check ports are free
# --------------------------------------------------------------------------
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
N8N_PORT="${N8N_PORT:-5678}"
REDIS_PORT="${REDIS_PORT:-6379}"

check_port() {
    local port="$1"
    local label="$2"
    if command -v ss &>/dev/null; then
        if ss -tln 2>/dev/null | grep -qE ":${port}[[:space:]]"; then
            echo -e "${RED}[ERROR] Port ${port} (${label}) is already in use.${NC}"
            return 1
        fi
    elif command -v nc &>/dev/null; then
        if nc -z 127.0.0.1 "$port" 2>/dev/null; then
            echo -e "${RED}[ERROR] Port ${port} (${label}) is already in use.${NC}"
            return 1
        fi
    fi
    echo -e "${GREEN}[OK] Port ${port} (${label}) is free.${NC}"
}

check_port "$POSTGRES_PORT" "postgres"
check_port "$N8N_PORT"      "n8n"
check_port "$REDIS_PORT"    "redis"

# --------------------------------------------------------------------------
# Start services
# --------------------------------------------------------------------------
echo ""
echo "[INFO] Starting services..."
cd "$PROJECT_DIR"
docker compose up -d

# --------------------------------------------------------------------------
# Wait for a container to report healthy via docker inspect
# Args: $1 = service name fragment to match in container name
# --------------------------------------------------------------------------
wait_healthy() {
    local service="$1"
    local retries=30
    local container

    echo "[INFO] Waiting for ${service} to become healthy..."

    # Resolve the full container name from the compose project
    container="$(docker compose ps -q "$service" 2>/dev/null | head -1 || true)"
    if [ -z "$container" ]; then
        echo -e "${YELLOW}[WARN] Could not resolve container for service '${service}'; skipping wait.${NC}"
        return 0
    fi

    while [ "$retries" -gt 0 ]; do
        local status
        status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}' "$container" 2>/dev/null || true)"
        if [ "$status" = "healthy" ] || [ "$status" = "running" ]; then
            echo -e "${GREEN}[OK] ${service} is ${status}.${NC}"
            return 0
        fi
        retries=$((retries - 1))
        sleep 2
    done

    echo -e "${YELLOW}[WARN] ${service} did not reach healthy state within timeout; continuing.${NC}"
}

wait_healthy "postgres"
wait_healthy "redis"

echo ""
echo -e "${GREEN}=========================================="
echo " Stack started successfully."
echo -e "==========================================${NC}"
echo ""
echo "  n8n:      http://localhost:${N8N_PORT}/"
echo "  postgres: localhost:${POSTGRES_PORT}"
echo "  redis:    localhost:${REDIS_PORT}"
echo ""
echo "  Logs:    ./scripts/logs.sh [service]"
echo "  Status:  ./scripts/status.sh"
echo ""
