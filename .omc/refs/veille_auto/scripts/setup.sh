#!/bin/bash
# ==========================================
# SCRIPT D'INSTALLATION INITIALE
# ==========================================

set -e  # Arrêter si erreur

# Résoudre le répertoire du projet
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "🚀 Installation du Système de Veille IA"
echo "========================================"
echo ""

# Vérifier Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker n'est pas installé !"
    echo "📥 Installation de Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER
    echo "✅ Docker installé ! Déconnexion/reconnexion nécessaire."
    echo "   Puis relancez ce script."
    exit 1
fi

# Vérifier Docker Compose
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose plugin n'est pas installé !"
    echo "📥 Installation..."
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
fi

echo "✅ Docker et Docker Compose OK"
echo ""

# Créer le fichier .env s'il n'existe pas
if [ ! -f .env ]; then
    echo "📝 Création du fichier .env..."
    cp env.template .env

    # Générer les mots de passe sécurisés
    echo "🔐 Génération des mots de passe sécurisés..."
    DB_PASSWORD=$(openssl rand -base64 32 | tr -d "=+/" | cut -c1-32)
    N8N_KEY=$(openssl rand -hex 32)
    GRAFANA_PASSWORD=$(openssl rand -base64 16 | tr -d "=+/" | cut -c1-16)

    # Remplacer dans .env
    sed -i "s/POSTGRES_PASSWORD=CHANGEME_GENERATE_SECURE_PASSWORD/POSTGRES_PASSWORD=$DB_PASSWORD/" .env
    sed -i "s/N8N_ENCRYPTION_KEY=CHANGEME_GENERATE_ENCRYPTION_KEY/N8N_ENCRYPTION_KEY=$N8N_KEY/" .env
    sed -i "s/GRAFANA_PASSWORD=CHANGEME_GENERATE_PASSWORD/GRAFANA_PASSWORD=$GRAFANA_PASSWORD/" .env

    echo "✅ Fichier .env créé avec mots de passe générés"
    echo ""
    echo "⚠️  IMPORTANT : Éditer .env et ajouter votre DISCORD_WEBHOOK_URL"
    echo ""
else
    echo "ℹ️  Fichier .env existe déjà, pas de modification."
fi

# Créer les répertoires de données
echo "📁 Création des répertoires de données..."
mkdir -p data/postgres data/n8n data/prometheus data/grafana backups logs

# Créer les fichiers .gitkeep
touch data/.gitkeep backups/.gitkeep logs/.gitkeep

echo "✅ Répertoires créés"
echo ""

# Afficher les credentials
echo "🔑 CREDENTIALS GÉNÉRÉS"
echo "======================="
echo "n8n Interface:"
echo "  URL: http://localhost:5678"
echo "  📝 Note: Créez votre compte lors du premier accès (page /setup)"
echo ""
echo "PostgreSQL:"
echo "  User: n8n"
echo "  Pass: [voir .env]"
echo "  DB: veille_ia"
echo "  Port: 5433 (externe) / 5432 (interne)"
echo ""

echo "📋 PROCHAINES ÉTAPES"
echo "===================="
echo "1. Éditer .env et ajouter votre DISCORD_WEBHOOK_URL"
echo "2. Lancer: ./scripts/start.sh"
echo "3. Accéder à n8n: http://localhost:5678"
echo "4. Créer vos workflows dans l'interface n8n"
echo ""
echo "✅ Setup terminé !"
