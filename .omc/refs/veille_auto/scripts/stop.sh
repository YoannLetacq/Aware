#!/bin/bash
# ==========================================
# ARRÊTER LE SYSTÈME DE VEILLE IA
# ==========================================

# Résoudre le répertoire du projet
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "🛑 Arrêt du Système de Veille IA..."
echo ""

docker compose down

echo ""
echo "✅ Système arrêté !"
echo ""
echo "ℹ️  Les données sont conservées dans ./data/"
echo "🔄 Pour redémarrer: ./scripts/start.sh"
echo ""
