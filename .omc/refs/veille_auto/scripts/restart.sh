#!/bin/bash
# ==========================================
# REDÉMARRER LE SYSTÈME DE VEILLE IA
# ==========================================

# Résoudre le répertoire du projet
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "🔄 Redémarrage du Système de Veille IA..."
echo ""

docker compose restart

echo ""
echo "⏳ Attente de la reconnexion (10 secondes)..."
sleep 10

# Vérifier le statut
echo ""
echo "📊 Statut des services:"
docker compose ps

echo ""
echo "✅ Système redémarré !"
echo ""
