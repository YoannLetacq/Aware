#!/bin/bash
# ==========================================
# VÉRIFIER LE STATUT DU SYSTÈME
# ==========================================

# Résoudre le répertoire du projet
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Charger les variables d'environnement
if [ -f .env ]; then
    set -a
    source .env
    set +a
else
    echo "❌ Fichier .env introuvable !"
    exit 1
fi

echo "📊 STATUT DU SYSTÈME DE VEILLE IA"
echo "===================================="
echo ""

# Statut des containers
echo "🐳 Containers Docker:"
docker compose ps
echo ""

# Statistiques BDD
echo "📈 Statistiques Base de Données:"
docker compose exec -T postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB" << EOF
SELECT
    '📝 Total articles' as stat, COUNT(*)::text as valeur
FROM rss_articles
UNION ALL
SELECT
    '✅ Articles envoyés', COUNT(*)::text
FROM rss_articles WHERE sent_at IS NOT NULL
UNION ALL
SELECT
    '🕐 Dernières 24h', COUNT(*)::text
FROM rss_articles WHERE sent_at > NOW() - INTERVAL '24 hours'
UNION ALL
SELECT
    '📅 Derniers 7 jours', COUNT(*)::text
FROM rss_articles WHERE sent_at > NOW() - INTERVAL '7 days'
UNION ALL
SELECT
    '📰 Sources distinctes', COUNT(DISTINCT source)::text
FROM rss_articles
UNION ALL
SELECT
    '🏷️  Catégories distinctes', COUNT(DISTINCT category)::text
FROM rss_articles WHERE category IS NOT NULL;
EOF

echo ""

# Utilisation disque
echo "💾 Utilisation Disque:"
du -sh data/* 2>/dev/null | sed 's/data\//  /'
echo ""

# Derniers logs
echo "📋 Derniers logs (5 lignes):"
echo "  PostgreSQL:"
docker compose logs --tail=5 postgres 2>/dev/null | tail -5 | sed 's/^/    /'
echo ""
echo "  n8n:"
docker compose logs --tail=5 n8n 2>/dev/null | tail -5 | sed 's/^/    /'
echo ""

echo "✅ Status check terminé"
echo ""
echo "💡 Commandes utiles:"
echo "   Logs détaillés: ./scripts/logs.sh [postgres|n8n|rsshub]"
echo "   Backup: ./scripts/backup.sh"
echo "   Redémarrer: ./scripts/restart.sh"
echo ""
