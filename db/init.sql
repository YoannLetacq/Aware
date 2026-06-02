-- ==========================================
-- PODCAST PIPELINE SCHEMA
-- Pattern reference: refs/veille_auto/scripts/init.sql:1-3
-- ==========================================

-- pgcrypto required for gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ==========================================
-- SCHEMA
-- ==========================================
CREATE SCHEMA IF NOT EXISTS podcast;

-- ==========================================
-- STATUS ENUM (D7: linear, explicit fail)
-- ==========================================
DO $$ BEGIN
    CREATE TYPE podcast.job_status AS ENUM (
        'queued',
        'gemini_running',
        'gemini_done',
        'notebooklm_uploading',
        'notebooklm_generating',
        'delivered',
        'failed'
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ==========================================
-- JOBS TABLE
--
-- NOTE: Two-namespace convention for job identity:
--   - `id` (UUID) is the database primary key, used in all SQL queries (e.g. WHERE id = $1).
--   - `job_id` appears in JSON request envelopes (NotebookLMJobRequest §3.4) as the
--     application-layer identifier carried in the JSONB `payload` column.
--   These two identifiers coexist without conflict: `id` owns DB addressing,
--   `job_id` owns the inter-service message envelope.
-- ==========================================
CREATE TABLE IF NOT EXISTS podcast.jobs (
    -- Primary key
    id                   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Discord trigger context
    interaction_id       TEXT        NOT NULL UNIQUE,
    user_id              TEXT        NOT NULL,
    channel_id           TEXT        NOT NULL,
    guild_id             VARCHAR(32) NULL,                          -- Discord guild id; NULL for DM channels
    -- Request metadata
    locale               VARCHAR(8)  NOT NULL DEFAULT 'fr',         -- FR-only UX per language convention
    -- Request payload
    subject              TEXT        NOT NULL,
    subject_hash         TEXT        NOT NULL,
    mode                 TEXT        NOT NULL CHECK (mode IN ('podcast', 'video')),
    style                TEXT        NULL,
    payload              JSONB       NOT NULL DEFAULT '{}'::jsonb,  -- Full NotebookLMJobRequest envelope
    -- Lifecycle
    status               podcast.job_status NOT NULL DEFAULT 'queued',
    attempt              SMALLINT    NOT NULL DEFAULT 1 CHECK (attempt BETWEEN 1 AND 3),  -- Retry counter
    started_at           TIMESTAMPTZ NULL,                          -- Set by worker on BRPOP claim (§2.2 step 2)
    finished_at          TIMESTAMPTZ NULL,                          -- Set at terminal status (delivered or failed)
    -- Gemini output
    gemini_sources       JSONB       NULL,
    -- Artifact
    artifact_path        TEXT        NULL,
    artifact_sha256      TEXT        NULL,
    artifact_size_bytes  BIGINT      NULL,
    artifact_duration_s  NUMERIC(8,2) NULL,                         -- Audio/video duration once known
    -- Failure context
    error_stage          TEXT        NULL,
    error_code           TEXT        NULL,
    error_message        TEXT        NULL,
    -- Audit timestamps
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================
-- RATE LIMITS TABLE (M2 quota enforcement)
-- ==========================================
CREATE TABLE IF NOT EXISTS podcast.rate_limits (
    user_id     TEXT        NOT NULL,
    day         DATE        NOT NULL,
    count       INTEGER     NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

-- ==========================================
-- AUDIT LOG TABLE (M3, M4 observability)
-- ==========================================
CREATE TABLE IF NOT EXISTS podcast.audit_log (
    id          BIGSERIAL   PRIMARY KEY,
    job_id      UUID        NULL REFERENCES podcast.jobs (id),
    event       TEXT        NOT NULL,
    payload     JSONB       NULL,
    ts          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ==========================================
-- INDEXES
-- ==========================================

-- NOTE: Idempotency design (§3.5 / Fix 6)
-- The plan calls for a 24-hour deduplication window on delivered jobs.
-- A partial index predicate of the form
--   WHERE status = 'delivered' AND created_at > now() - interval '24 hours'
-- is NOT allowed by Postgres because now() is not IMMUTABLE; index predicates
-- must be immutable expressions.  The time-window enforcement therefore lives
-- in the application layer: the bot pre-checks
--   SELECT * FROM podcast.recent_delivered WHERE user_id=$1 AND subject_hash=$2
--     AND mode=$3 AND COALESCE(style,'-')=$4
-- before enqueuing.  The index below prevents duplicate *lifetime* delivered
-- rows for the same combination; the view below scopes lookups to 24 h.
CREATE UNIQUE INDEX IF NOT EXISTS uq_jobs_delivered_idempotency
    ON podcast.jobs (user_id, subject_hash, mode, COALESCE(style, '-'))
    WHERE status = 'delivered';

COMMENT ON INDEX podcast.uq_jobs_delivered_idempotency IS
    'Unique constraint on delivered jobs per (user, subject_hash, mode, style). '
    'The 24-hour idempotency window from §3.5 is enforced at SELECT-time by the '
    'bot using the podcast.recent_delivered view, not in this index predicate, '
    'because now() is not immutable and cannot appear in a partial index WHERE clause.';

-- Helper view for the bot idempotency lookup (§3.5 / IMPLEMENTATION_PLAN §5).
-- Use this view — not the raw table — for all 24-h duplicate checks.
CREATE OR REPLACE VIEW podcast.recent_delivered AS
    SELECT *
    FROM podcast.jobs
    WHERE status = 'delivered'
      AND created_at > NOW() - INTERVAL '24 hours';

COMMENT ON VIEW podcast.recent_delivered IS '24h lookback for idempotency; see IMPLEMENTATION_PLAN.md §3.5';

CREATE INDEX IF NOT EXISTS idx_jobs_status_created
    ON podcast.jobs (status, created_at)
    WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS idx_jobs_user_created
    ON podcast.jobs (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_job_id
    ON podcast.audit_log (job_id);

CREATE INDEX IF NOT EXISTS idx_audit_ts
    ON podcast.audit_log (ts DESC);

-- ==========================================
-- UPDATED_AT TRIGGER
-- Pattern: refs/veille_auto/scripts/init.sql:41-54
-- ==========================================

-- Reuse the function if already created by another schema
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_podcast_jobs_updated_at ON podcast.jobs;
CREATE TRIGGER update_podcast_jobs_updated_at
    BEFORE UPDATE ON podcast.jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ==========================================
-- CONFIRMATION
-- ==========================================
DO $$
BEGIN
    RAISE NOTICE 'podcast schema initialised: jobs, rate_limits, audit_log';
END $$;
