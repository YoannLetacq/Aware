#!/bin/bash
# ==========================================
# BACKUP DU SYSTÈME
# ==========================================

set -e

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

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)

echo "💾 Backup du Système de Veille IA"
echo "===================================="
echo ""

# Créer le répertoire de backup
mkdir -p $BACKUP_DIR

# Backup PostgreSQL
echo "📦 Backup PostgreSQL..."
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > "$BACKUP_DIR/${POSTGRES_DB}_$DATE.sql"
echo "   ✅ $BACKUP_DIR/${POSTGRES_DB}_$DATE.sql"

# Backup workflows n8n
echo "📦 Backup workflows n8n..."
if [ -d "data/n8n" ]; then
    tar -czf "$BACKUP_DIR/n8n_data_$DATE.tar.gz" -C data n8n
    echo "   ✅ $BACKUP_DIR/n8n_data_$DATE.tar.gz"
fi

# Backup .env
echo "📦 Backup configuration..."
cp .env "$BACKUP_DIR/env_$DATE.bak"
echo "   ✅ $BACKUP_DIR/env_$DATE.bak"

# Taille du backup
BACKUP_SIZE=$(du -sh $BACKUP_DIR | cut -f1)
echo ""
echo "✅ Backup terminé !"
echo "📊 Taille totale des backups: $BACKUP_SIZE"
echo ""

# Nettoyer les vieux backups (garder les 7 derniers)
echo "🧹 Nettoyage des anciens backups (> 7 jours)..."
find $BACKUP_DIR -name "${POSTGRES_DB}_*.sql" -mtime +7 -delete 2>/dev/null || true
find $BACKUP_DIR -name "n8n_data_*.tar.gz" -mtime +7 -delete 2>/dev/null || true
find $BACKUP_DIR -name "env_*.bak" -mtime +7 -delete 2>/dev/null || true

echo "✅ Nettoyage terminé"
echo ""
echo "💡 Pour restaurer: ./scripts/restore.sh $BACKUP_DIR/${POSTGRES_DB}_$DATE.sql"
echo ""
