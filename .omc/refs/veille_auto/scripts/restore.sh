#!/bin/bash
# ==========================================
# RESTAURER UN BACKUP
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

BACKUP_FILE=$1

if [ -z "$BACKUP_FILE" ]; then
    echo "❌ Usage: ./scripts/restore.sh <fichier_backup.sql>"
    echo ""
    echo "📁 Backups disponibles:"
    ls -lht backups/*.sql 2>/dev/null | head -5 | awk '{print "   " $9 " (" $5 ", " $6 " " $7 ")"}'
    exit 1
fi

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Fichier introuvable: $BACKUP_FILE"
    exit 1
fi

echo "⚠️  ATTENTION: Restaurer un backup va ÉCRASER les données actuelles !"
echo ""
echo "📁 Backup à restaurer: $BACKUP_FILE"
echo ""
read -p "Continuer ? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Annulé."
    exit 1
fi

echo ""
echo "💾 Restauration en cours..."
echo ""

# Backup de sécurité avant restauration
echo "📦 Création d'un backup de sécurité..."
./scripts/backup.sh

# Restauration
echo "♻️  Restauration de la base de données..."
docker compose exec -T postgres psql -U "$POSTGRES_USER" "$POSTGRES_DB" < "$BACKUP_FILE"

echo ""
echo "✅ Restauration terminée !"
echo ""
echo "💡 Vérifiez les données: ./scripts/status.sh"
echo ""
