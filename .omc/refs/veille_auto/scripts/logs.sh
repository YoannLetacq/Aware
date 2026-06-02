#!/bin/bash
# ==========================================
# AFFICHER LES LOGS
# ==========================================

# Résoudre le répertoire du projet
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

SERVICE=${1:-n8n}

echo "📋 Logs du service: $SERVICE"
echo "===================================="
echo ""
echo "💡 Ctrl+C pour quitter"
echo ""

if [ "$SERVICE" == "all" ]; then
    docker compose logs -f --tail=100
else
    docker compose logs -f --tail=100 $SERVICE
fi
