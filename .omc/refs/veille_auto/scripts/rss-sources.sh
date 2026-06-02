#!/bin/bash
# ==========================================
# GÉRER LES SOURCES RSS
# ==========================================
# Valide, affiche et recharge les sources RSS

# Résoudre le répertoire du projet
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

RSS_FILE="$PROJECT_DIR/rss_sources.json"

# Couleurs
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

show_usage() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  status    Afficher les sources actives (défaut)"
    echo "  validate  Valider la syntaxe JSON"
    echo "  reload    Redémarrer n8n pour recharger les sources"
    echo "  list      Lister toutes les sources (actives et inactives)"
    echo ""
}

validate_json() {
    echo -e "${BLUE}🔍 Validation de $RSS_FILE...${NC}"
    echo ""

    if [ ! -f "$RSS_FILE" ]; then
        echo -e "${RED}❌ Fichier non trouvé: $RSS_FILE${NC}"
        return 1
    fi

    # Validate JSON syntax
    if ! jq empty "$RSS_FILE" 2>/dev/null; then
        echo -e "${RED}❌ Erreur de syntaxe JSON:${NC}"
        jq . "$RSS_FILE" 2>&1
        return 1
    fi

    echo -e "${GREEN}✅ Syntaxe JSON valide${NC}"
    return 0
}

show_status() {
    echo -e "${BLUE}📡 Sources RSS - Statut${NC}"
    echo "================================"
    echo ""

    if ! validate_json; then
        return 1
    fi

    echo ""

    # Count sources
    local total=$(jq '.sources | length' "$RSS_FILE")
    local active=$(jq '[.sources[] | select(.active == true)] | length' "$RSS_FILE")
    local inactive=$((total - active))

    echo -e "📊 ${GREEN}$active actives${NC} / $total sources ($inactive inactives)"
    echo ""

    # Show active sources by category
    echo -e "${YELLOW}Sources actives par catégorie:${NC}"
    echo ""

    jq -r '.sources[] | select(.active == true) | "\(.category)|\(.name)|\(.priority)"' "$RSS_FILE" | \
    sort | \
    while IFS='|' read -r category name priority; do
        local icon="📰"
        case "$priority" in
            high) icon="🔥" ;;
            medium) icon="⭐" ;;
            low) icon="📄" ;;
        esac
        echo "  $icon [$category] $name"
    done

    echo ""

    # Check mount in container
    echo -e "${BLUE}🐳 Vérification du montage dans n8n...${NC}"
    if docker compose exec -T n8n test -f /home/node/rss_sources.json 2>/dev/null; then
        echo -e "${GREEN}✅ Fichier monté dans le conteneur n8n${NC}"
    else
        echo -e "${RED}❌ Fichier non monté! Exécutez: docker compose up -d${NC}"
    fi
}

list_all() {
    echo -e "${BLUE}📋 Toutes les sources RSS${NC}"
    echo "================================"
    echo ""

    if ! validate_json; then
        return 1
    fi

    echo ""
    echo -e "${GREEN}✅ ACTIVES:${NC}"
    jq -r '.sources[] | select(.active == true) | "  [\(.category)] \(.name) - \(.url)"' "$RSS_FILE"

    echo ""
    echo -e "${RED}❌ INACTIVES:${NC}"
    jq -r '.sources[] | select(.active == false) | "  [\(.category)] \(.name)"' "$RSS_FILE"

    echo ""

    # Custom RSSHub sources
    local custom_count=$(jq '.sources_custom_rsshub | length' "$RSS_FILE" 2>/dev/null || echo "0")
    if [ "$custom_count" != "0" ] && [ "$custom_count" != "null" ]; then
        echo -e "${YELLOW}🔧 SOURCES RSSHUB CUSTOM:${NC}"
        jq -r '.sources_custom_rsshub[] | "  [\(if .active then "✅" else "❌" end)] \(.name) - \(.url)"' "$RSS_FILE"
        echo ""
    fi
}

reload_sources() {
    echo -e "${BLUE}🔄 Rechargement des sources RSS...${NC}"
    echo ""

    if ! validate_json; then
        return 1
    fi

    echo ""
    echo "ℹ️  Note: Le fichier est monté en lecture seule."
    echo "   Les changements sont pris en compte à chaque exécution du workflow."
    echo ""

    read -p "Voulez-vous redémarrer n8n quand même? [y/N] " -n 1 -r
    echo ""

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo ""
        echo "🔄 Redémarrage de n8n..."
        docker compose restart n8n

        echo ""
        echo "⏳ Attente (5 secondes)..."
        sleep 5

        # Verify
        if docker compose exec -T n8n test -f /home/node/rss_sources.json 2>/dev/null; then
            echo -e "${GREEN}✅ n8n redémarré, fichier accessible${NC}"
        else
            echo -e "${RED}❌ Problème avec le montage${NC}"
        fi
    else
        echo "ℹ️  Pas de redémarrage. Les changements seront actifs au prochain run du workflow."
    fi
}

# Main
case "${1:-status}" in
    status)
        show_status
        ;;
    validate)
        validate_json
        ;;
    reload)
        reload_sources
        ;;
    list)
        list_all
        ;;
    -h|--help|help)
        show_usage
        ;;
    *)
        echo -e "${RED}Commande inconnue: $1${NC}"
        echo ""
        show_usage
        exit 1
        ;;
esac
