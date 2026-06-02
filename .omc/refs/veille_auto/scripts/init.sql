-- ==========================================
-- SCHÉMA BASE DE DONNÉES - VEILLE IA
-- ==========================================

-- Table principale des articles RSS
CREATE TABLE IF NOT EXISTS rss_articles (
    id SERIAL PRIMARY KEY,
    url VARCHAR(2048) UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    content TEXT,
    source VARCHAR(255) NOT NULL,
    source_type VARCHAR(100),
    category VARCHAR(100),
    published_at TIMESTAMP WITH TIME ZONE,
    sent_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Migration: add source_type column if upgrading from an older schema
ALTER TABLE rss_articles ADD COLUMN IF NOT EXISTS source_type VARCHAR(100);

-- Index pour optimiser les requêtes
CREATE INDEX IF NOT EXISTS idx_url ON rss_articles(url);
CREATE INDEX IF NOT EXISTS idx_sent_at ON rss_articles(sent_at);
CREATE INDEX IF NOT EXISTS idx_published_at ON rss_articles(published_at);
CREATE INDEX IF NOT EXISTS idx_source ON rss_articles(source);
CREATE INDEX IF NOT EXISTS idx_category ON rss_articles(category);
CREATE INDEX IF NOT EXISTS idx_created_at ON rss_articles(created_at);

-- Index composite pour recherches fréquentes
CREATE INDEX IF NOT EXISTS idx_source_sent_at ON rss_articles(source, sent_at);
CREATE INDEX IF NOT EXISTS idx_category_published ON rss_articles(category, published_at DESC);

-- Partial index for the recent-sent_at hot path (article_stats view)
CREATE INDEX IF NOT EXISTS idx_sent_at_recent
    ON rss_articles(sent_at) WHERE sent_at IS NOT NULL;

-- Fonction pour mettre à jour updated_at automatiquement
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger pour updated_at
DROP TRIGGER IF EXISTS update_rss_articles_updated_at ON rss_articles;
CREATE TRIGGER update_rss_articles_updated_at
    BEFORE UPDATE ON rss_articles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Table de logs pour tracking (optionnel)
CREATE TABLE IF NOT EXISTS execution_logs (
    id SERIAL PRIMARY KEY,
    workflow_name VARCHAR(255) NOT NULL,
    execution_status VARCHAR(50) NOT NULL,
    articles_found INTEGER DEFAULT 0,
    articles_sent INTEGER DEFAULT 0,
    errors TEXT,
    executed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_execution_logs_date ON execution_logs(executed_at DESC);

-- Vue pour statistiques rapides
CREATE OR REPLACE VIEW article_stats AS
SELECT
    COUNT(*) as total_articles,
    COUNT(*) FILTER (WHERE sent_at IS NOT NULL) as sent_articles,
    COUNT(*) FILTER (WHERE sent_at > NOW() - INTERVAL '24 hours') as last_24h,
    COUNT(*) FILTER (WHERE sent_at > NOW() - INTERVAL '7 days') as last_7days,
    COUNT(DISTINCT source) as total_sources,
    COUNT(DISTINCT category) as total_categories,
    MAX(sent_at) as last_sent,
    MIN(created_at) as oldest_article
FROM rss_articles;

-- Fonction pour purger les anciens articles (> 90 jours)
CREATE OR REPLACE FUNCTION purge_old_articles()
RETURNS TABLE(deleted_count BIGINT) AS $$
DECLARE
    rows_deleted BIGINT;
BEGIN
    DELETE FROM rss_articles
    WHERE COALESCE(sent_at, created_at) < NOW() - INTERVAL '90 days';

    GET DIAGNOSTICS rows_deleted = ROW_COUNT;
    RETURN QUERY SELECT rows_deleted;
END;
$$ LANGUAGE plpgsql;

-- Fonction pour statistiques par source
CREATE OR REPLACE FUNCTION get_source_stats()
RETURNS TABLE(
    source_name VARCHAR(255),
    total_count BIGINT,
    sent_count BIGINT,
    last_article TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        source as source_name,
        COUNT(*) as total_count,
        COUNT(*) FILTER (WHERE sent_at IS NOT NULL) as sent_count,
        MAX(published_at) as last_article
    FROM rss_articles
    GROUP BY source
    ORDER BY total_count DESC;
END;
$$ LANGUAGE plpgsql;

-- ==========================================
-- FONCTIONS DE DÉDUPLICATION POUR N8N
-- ==========================================

-- Fonction 1: Filtrer les URLs nouvelles (retourne seulement les URLs non présentes en base)
CREATE OR REPLACE FUNCTION filter_new_urls(urls_to_check TEXT[])
RETURNS TABLE(url TEXT) AS $$
BEGIN
    RETURN QUERY
    SELECT u.val as url
    FROM unnest(urls_to_check) u(val)
    WHERE NOT EXISTS (SELECT 1 FROM rss_articles a WHERE a.url = u.val);
END;
$$ LANGUAGE plpgsql;

-- Fonction 2: Vérifier les doublons avec détails (retourne le statut de chaque URL)
CREATE OR REPLACE FUNCTION check_url_duplicates(urls_to_check TEXT[])
RETURNS TABLE(
    url TEXT,
    is_new BOOLEAN,
    existing_id INTEGER,
    existing_created_at TIMESTAMP WITH TIME ZONE,
    existing_sent_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.url::TEXT,
        (a.id IS NULL) as is_new,
        a.id as existing_id,
        a.created_at as existing_created_at,
        a.sent_at as existing_sent_at
    FROM unnest(urls_to_check) u(url)
    LEFT JOIN rss_articles a ON a.url = u.url::TEXT;
END;
$$ LANGUAGE plpgsql;

-- Fonction 2b: Version JSONB pour n8n (RECOMMANDÉE)
CREATE OR REPLACE FUNCTION check_url_duplicates_json(urls_json JSONB)
RETURNS TABLE(
    url TEXT,
    is_new BOOLEAN,
    existing_id INTEGER,
    existing_created_at TIMESTAMP WITH TIME ZONE,
    existing_sent_at TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.url::TEXT,
        (a.id IS NULL) as is_new,
        a.id as existing_id,
        a.created_at as existing_created_at,
        a.sent_at as existing_sent_at
    FROM jsonb_array_elements_text(urls_json) u(url)
    LEFT JOIN rss_articles a ON a.url = u.url::TEXT;
END;
$$ LANGUAGE plpgsql;

-- Fonction 3: Traiter un batch d'articles en JSON (pour workflow n8n complet)
CREATE OR REPLACE FUNCTION process_rss_batch(articles_json JSONB)
RETURNS TABLE(
    url TEXT,
    is_new BOOLEAN,
    should_process BOOLEAN,
    article_data JSONB
) AS $$
BEGIN
    RETURN QUERY
    WITH incoming AS (
        SELECT
            value->>'url' as url,
            value as data
        FROM jsonb_array_elements(articles_json)
    )
    SELECT
        i.url,
        (a.url IS NULL) as is_new,
        (a.url IS NULL) as should_process,
        i.data as article_data
    FROM incoming i
    LEFT JOIN rss_articles a ON a.url = i.url;
END;
$$ LANGUAGE plpgsql;

-- Fonction 4: Stats de déduplication (monitoring)
CREATE OR REPLACE FUNCTION get_deduplication_stats()
RETURNS TABLE(
    total_articles INTEGER,
    last_24h INTEGER,
    last_7days INTEGER,
    avg_per_day NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::INTEGER as total,
        COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '24 hours')::INTEGER as last_24h,
        COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days')::INTEGER as last_7days,
        ROUND(COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days')::NUMERIC / 7, 2) as avg_per_day
    FROM rss_articles;
END;
$$ LANGUAGE plpgsql;

-- Insérer un log d'initialisation
INSERT INTO execution_logs (workflow_name, execution_status, articles_found, articles_sent)
VALUES ('database_init', 'success', 0, 0);

-- Message de confirmation
DO $$
BEGIN
    RAISE NOTICE '✅ Base de données initialisée avec succès !';
    RAISE NOTICE '📊 Tables créées : rss_articles, execution_logs';
    RAISE NOTICE '📈 Vues créées : article_stats';
    RAISE NOTICE '🔧 Fonctions créées : purge_old_articles(), get_source_stats()';
    RAISE NOTICE '🔄 Fonctions n8n : filter_new_urls(), check_url_duplicates(), process_rss_batch()';
END $$;
