#!/bin/bash
# ==========================================
# DÉMARRER LE SYSTÈME DE VEILLE IA
# ==========================================

set -e

# Résoudre le répertoire du projet
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "🚀 Démarrage du Système de Veille IA..."
echo ""

# Vérifier que .env existe
if [ ! -f .env ]; then
    echo "❌ Fichier .env introuvable !"
    echo "   Lancez d'abord: ./scripts/setup.sh"
    exit 1
fi

# Vérifier que Discord webhook est configuré
if grep -q "YOUR_WEBHOOK_ID" .env; then
    echo "⚠️  WARNING: DISCORD_WEBHOOK_URL n'est pas configuré dans .env"
    echo "   Les notifications Discord ne fonctionneront pas."
    echo ""
    read -p "Continuer quand même ? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Démarrer les services
echo "🐳 Démarrage des containers Docker..."
docker compose up -d

echo ""
echo "⏳ Attente de l'initialisation (30 secondes)..."
sleep 30

# Vérifier le statut
echo ""
echo "📊 Statut des services:"
docker compose ps

echo ""
echo "✅ Système démarré !"
echo ""
echo "🔗 URLs d'accès:"
echo "   n8n Interface: http://localhost:5678"
echo "   RSSHub: http://localhost:1200"
echo ""
echo "🔐 n8n Login:"
echo "   Première fois: Créez votre compte sur la page /setup"
echo "   Ensuite: Utilisez votre email/mot de passe personnel"
echo ""
echo "📝 Voir les logs: ./scripts/logs.sh [service]"
echo "📊 Voir le status: ./scripts/status.sh"
echo ""
