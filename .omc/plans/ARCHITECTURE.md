# ARCHITECTURE — Podcast/Video Pipeline

> Author: `planner` agent acting as architecture designer (the dedicated
> `architect` role is read-only-no-write per project routing).
> Scope: module boundaries, container topology, data contracts, state model,
> secret surface, and failure/retry matrix for the MVP described in
> `.omc/research/requirements.md` and constrained by `.omc/research/critique.md`.
> Mandate boundaries: this document defines **interfaces and contracts only**;
> it contains no implementation code beyond DDL and JSON Schemas. Out-of-scope
> edits: source files outside `.omc/plans/`.

---

## 0. Decision drivers (cite-linked)

| # | Driver                                                                | Source                                                      |
|---|-----------------------------------------------------------------------|-------------------------------------------------------------|
| D1| n8n must NOT host long-running browser steps                          | `critique.md` H1 (REJECT-class)                             |
| D2| Discord 3 s ack / 15 min follow-up window cannot wrap NotebookLM run  | `critique.md` H3                                            |
| D3| `storageState.json` is a top-tier credential (file, not env var)      | `critique.md` H4                                            |
| D4| Idempotency required on `(user_id, subject_hash)`                     | `critique.md` M3; `requirements.md` AC3.x                   |
| D5| Per-user + global rate-limit kill switch is mandatory pre-deploy      | `critique.md` M2                                            |
| D6| ≤25 MB → Discord direct; else signed-URL fallback                     | `requirements.md` AC5.1/5.2; `critique.md` M2               |
| D7| Linear happy-path; explicit early-exit on failure (no branch retries) | `requirements.md` §Internal Inconsistencies #1              |
| D8| Schema isolation under `podcast.*`, not `public.*`                    | `critique.md` L3                                            |
| D9| Reuse veille_auto compose patterns (postgres, networks, healthcheck)  | `refs/veille_auto/docker-compose.yml:5-30, 119-140, 201-203`|

---

## 1. Container topology

### 1.1 Services

| Service          | Image                            | Purpose                                                              | Network        |
|------------------|----------------------------------|----------------------------------------------------------------------|----------------|
| `postgres`       | `postgres:16-alpine`             | State store (`podcast.*` schema), n8n DB                              | podcast-net    |
| `n8n`            | `n8nio/n8n:2.22.3`               | Trigger ingestion + dispatcher + Discord post-back ONLY               | podcast-net    |
| `discord-bot`    | custom (Python `discord.py`)     | Slash-command listener; defers, validates, POSTs to n8n webhook       | podcast-net    |
| `browser-worker` | custom (Python + Playwright)     | Owns Chromium, NotebookLM session, polling loop, artifact download    | podcast-net    |
| `redis`          | `redis:7-alpine`                 | Job queue (LPUSH/BRPOP) — AOF enabled for durability per §2.2.        | podcast-net    |

Optional / deferred: `prometheus`, `grafana` (mirror veille_auto compose comments
at lines 162-199 — keep stub blocks commented).

### 1.2 Justifications (per service)

- **postgres** — Reused pattern from `refs/veille_auto/docker-compose.yml:5-30`.
  Stores n8n internal state AND `podcast.jobs`. Single DB, separate schemas
  (D8). Postgres is the authoritative state store; Redis is the queue
  transport (§2.2).
- **n8n** — Pattern from `refs/veille_auto/docker-compose.yml:35-93`. Restricted
  to: receive Discord webhook → INSERT job row → LPUSH to Redis → return 200.
  Then a callback webhook from `browser-worker` re-enters n8n to format the
  Discord post. **No browser node, no long polling node.** (D1)
- **discord-bot** — Separate container so that the 3 s `defer` SLA (D2) is not
  contingent on n8n cold start / queue depth. Owns slash-command registration
  + signature verification (`DISCORD_PUBLIC_KEY`).
- **browser-worker** — Python + Playwright. BRPOPs from Redis list
  `podcast:jobs`; runs one job at a time (queue depth 1 in-flight, 4 queued;
  aligns with `requirements.md` open-question recommendation). Persists
  `storageState.json` to a dedicated volume (D3).
- **object storage** — Deferred to Phase 4 Q3; see §1.6.

### 1.3 Volumes

| Volume                          | Mounted in        | Purpose                                                                |
|---------------------------------|-------------------|------------------------------------------------------------------------|
| `./data/postgres`               | `postgres`        | DB data                                                                |
| `./data/n8n`                    | `n8n`             | n8n workflow JSON                                                      |
| `./data/worker/session`         | `browser-worker`  | `storageState.json` — `chmod 600`, owned by worker UID (D3). NOT in git.|
| `./data/worker/artifacts`       | `browser-worker`  | Downloaded MP3/MP4 staging area (also mounted RO into n8n if needed)   |
| `./data/worker/debug`           | `browser-worker`  | Screenshots, DOM dumps, HAR on failure (`critique.md` M4)              |
| `./data/redis`                  | `redis`           | AOF persistence data (`--appendonly yes`; §2.2 durability)             |
| `./db/init.sql`                 | `postgres` (RO)   | Schema bootstrap (`refs/veille_auto/scripts/init.sql:1-2` pattern)     |

### 1.4 Healthchecks

| Service          | Test                                                              | Interval |
|------------------|-------------------------------------------------------------------|----------|
| `postgres`       | `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB`                    | 10 s     |
| `n8n`            | `wget -qO- http://localhost:5678/healthz \|\| exit 1`               | 30 s     |
| `discord-bot`    | `python -c "import socket; socket.create_connection(('127.0.0.1', 8081), 1)"` (internal HTTP probe) | 30 s |
| `browser-worker` | HTTP `GET /healthz` on internal port 8090 returning `{"ok": true, "session_valid": bool}` | 30 s |
| `redis`          | `redis-cli ping`                                                  | 10 s / timeout 3 s / retries 5 |

Pattern lifted from `refs/veille_auto/docker-compose.yml:19-23, 129-133`.

### 1.5 Linear data flow (ASCII)

```
   User (Discord)
        │  /podcast subject:"…" mode:podcast
        ▼
 ┌────────────────┐  (defer ≤3 s, validate, sign-check)
 │  discord-bot   │
 └───────┬────────┘
         │ HTTPS POST /webhook/podcast-trigger  (JSON, §3.1)
         ▼
 ┌────────────────┐
 │      n8n       │  ─► INSERT podcast.jobs (status='queued')
 │  (trigger WF)  │  ─► LPUSH podcast:jobs <job_id>
 │                │  ─► 200 OK to discord-bot
 └────────────────┘
         │ Redis BRPOP podcast:jobs
         ▼
 ┌────────────────┐
 │ browser-worker │  status='gemini_running'
 │   step 1: call Gemini (§3.2/3.3)   ──► status='gemini_done'
 │   step 2: Playwright → NotebookLM  ──► status='notebooklm_uploading'
 │   step 3: trigger generation       ──► status='notebooklm_generating'
 │   step 4: download artifact        ──► status='delivered'  (or 'failed')
 └───────┬────────┘
         │ HTTPS POST /webhook/podcast-callback (JSON, §2.1 callback)
         ▼
 ┌────────────────┐
 │      n8n       │  Decide: ≤25 MB → Discord attachment
 │  (callback WF) │            > 25 MB → object-storage signed URL (Phase 4 backend pending Q3)
 │                │  POST to Discord channel.send (NOT interaction token, D2)
 └────────────────┘
         │
         ▼
   User (Discord) — receives MP3/MP4 or signed URL
```

### 1.6 Deferred services (Phase 4 — pending Q3)

`minio` (or external S3/R2): MinIO sidecar OR external S3/R2 — decision deferred per IMPLEMENTATION_PLAN.md §4 Q3; Phase 4 ships Discord-attachment-only fallback if Q3 unresolved (PLAN §7). Not present in `docker-compose.yml`; see §5.bis for the deferred secrets.

---

## 2. n8n ↔ browser-worker contract

### 2.1 REST shape (synchronous part)

Two HTTP endpoints, both internal to `podcast-net`, both protected by a shared
`WORKER_SHARED_TOKEN` in the `X-Worker-Token` header (constant-time compare).

#### `POST http://browser-worker:8090/jobs`  (n8n → worker)

Optional — kept for **direct dispatch / admin replay** only. The primary path
is queue-driven (§2.2). Same request body as the queue payload (§3.4).
Response (immediate):
```json
{"accepted": true, "job_id": "<uuid>", "queued_position": 0}
```
HTTP 202 on accept, 409 on `job_id` already terminal, 429 if backlog full.

#### `POST http://n8n:5678/webhook/podcast-callback`  (worker → n8n)

Worker emits this when the job reaches a terminal state. Schema in §3.6.
n8n's callback workflow validates the shared token, looks up the row,
formats the Discord message, posts via the bot's REST channel (not via the
interaction token — D2), and updates `podcast.jobs.status='delivered'`.

### 2.2 Queue protocol (primary path) — Redis `LPUSH` / `BRPOP`

**Decision: Redis list queue** (`LPUSH` to enqueue, `BRPOP` to consume).
Chosen per IMPLEMENTATION_PLAN.md §1; Redis is the queue transport.
Redis is already declared in `docker-compose.yml` for this purpose.

Justification:
- Redis is already in the stack (`docker-compose.yml` redis service, pattern
  from `refs/veille_auto/docker-compose.yml:119-140`). No extra service added.
- `BRPOP` is a blocking pop with built-in timeout; no polling tick required.
- Queue list: `podcast:jobs` on Redis DB 0 (`redis://redis:6379/0`).
- The Postgres `podcast.jobs` row is the authoritative state record; Redis
  carries only the job_id signal. This preserves transactional safety: n8n
  INSERTs the row first (Postgres TX commits), then does an independent
  `LPUSH`. In the rare case the LPUSH is lost the worker recovery tick
  (§below) catches it.

**Protocol:**
1. n8n trigger workflow:
   ```
   INSERT INTO podcast.jobs (...) VALUES (...) RETURNING id;
   LPUSH podcast:jobs <json_envelope>
   ```
   n8n LPUSHes a JSON envelope to list `podcast:jobs`:
   ```json
   {
     "job_id": "<UUID>",
     "interaction_id": "<Discord interaction snowflake>"
   }
   ```
   This enriches the queue value beyond a bare UUID so the worker has
   `interaction_id` immediately for log correlation without an extra
   Postgres round-trip.
2. `browser-worker` at boot calls `BRPOP podcast:jobs 30` in a loop.
   On receiving a value it **`JSON.parse`s the popped string** to obtain
   the envelope; `job_id` is the canonical key used to look up and lock
   the row:
   ```sql
   SELECT * FROM podcast.jobs
    WHERE id = $1 AND status = 'queued'
    FOR UPDATE SKIP LOCKED;
   UPDATE podcast.jobs SET status='gemini_running', started_at=NOW()
    WHERE id = $1;
   ```
   (`$1` is `envelope.job_id`, not the raw popped string.)
   **Protocol property**: LPUSH value is a JSON object, parsable by `JSON.parse`.
   A popped value that fails `JSON.parse` is a poison message and must be
   treated per §6 F4.

3. **Lost-LPUSH recovery**: worker also runs a 30 s tick polling Postgres for
   `status='queued' AND created_at < NOW() - INTERVAL '30 seconds'`. Covers
   the case where the worker was down when the LPUSH fired or the LPUSH was
   dropped (Redis list is not durable across restarts unless AOF is on;
   `docker-compose.yml` enables `--appendonly yes`).
4. At any terminal state the worker:
   - `UPDATE podcast.jobs SET status='delivered'|'failed', finished_at=NOW(),
     artifact_url=…, error=…`
   - `POST /webhook/podcast-callback` to n8n (§2.1).

---

## 3. Data contracts (JSON Schema draft 2020-12)

All schemas declare `$schema: https://json-schema.org/draft/2020-12/schema`
and use `additionalProperties: false` unless noted.

### 3.1 Discord → n8n trigger payload

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://podcast.local/schemas/discord-trigger.json",
  "title": "DiscordTrigger",
  "type": "object",
  "additionalProperties": false,
  "required": ["interaction_id", "user_id", "channel_id", "guild_id",
               "subject", "mode", "timestamp", "locale"],
  "properties": {
    "interaction_id": {"type": "string", "pattern": "^[0-9]{15,25}$"},
    "user_id":        {"type": "string", "pattern": "^[0-9]{15,25}$"},
    "channel_id":     {"type": "string", "pattern": "^[0-9]{15,25}$"},
    "guild_id":       {"type": ["string", "null"], "pattern": "^[0-9]{15,25}$"},
    "subject":        {"type": "string", "minLength": 40, "maxLength": 400},
    "mode":           {"type": "string", "enum": ["podcast", "video"]},
    "style":          {"type": ["string", "null"], "maxLength": 64},
    "timestamp":      {"type": "string", "format": "date-time"},
    "locale":         {"type": "string", "enum": ["fr", "en"]}
  },
  "allOf": [
    {
      "if":   {"properties": {"mode": {"const": "video"}}},
      "then": {"required": ["style"],
               "properties": {"style": {"type": "string", "minLength": 1}}}
    }
  ]
}
```

### 3.2 n8n / worker → Gemini request

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://podcast.local/schemas/gemini-request.json",
  "title": "GeminiRequest",
  "type": "object",
  "additionalProperties": false,
  "required": ["subject", "mode", "language_hint", "target_count"],
  "properties": {
    "subject":        {"type": "string", "minLength": 40, "maxLength": 400},
    "mode":           {"type": "string", "enum": ["podcast", "video"]},
    "language_hint":  {"type": "string", "enum": ["fr", "en", "mixed"]},
    "target_count":   {"type": "integer", "minimum": 5, "maximum": 15,
                       "default": 8}
  }
}
```

### 3.3 Gemini response — `Sources` schema

Authoritative; mirrors `requirements.md` §Gemini Prompt Contract & AC2.4.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://podcast.local/schemas/sources.json",
  "title": "Sources",
  "type": "object",
  "additionalProperties": false,
  "required": ["sources"],
  "properties": {
    "sources": {
      "type": "array",
      "minItems": 5,
      "maxItems": 15,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": ["url", "title", "type", "relevance_score",
                     "language", "rationale"],
        "properties": {
          "url":             {"type": "string", "format": "uri",
                              "pattern": "^https://"},
          "title":           {"type": "string", "minLength": 1,
                              "maxLength": 300},
          "type":            {"type": "string",
                              "enum": ["paper", "youtube",
                                       "article", "video_other"]},
          "relevance_score": {"type": "number", "minimum": 0, "maximum": 1},
          "language":        {"type": "string", "enum": ["fr", "en", "other"]},
          "rationale":       {"type": "string", "minLength": 1, "maxLength": 280}
        }
      }
    }
  }
}
```

Post-validation rules (worker, not schema): at least one `type=paper` and at
least one of `{youtube, video_other}`; URL liveness HEAD-check within 5 s;
dedup on normalised URL.

### 3.4 Queue payload — NotebookLM job request

This is the payload persisted in `podcast.jobs.payload JSONB` and also the
shape of `POST /jobs` (§2.1).

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://podcast.local/schemas/notebooklm-job-request.json",
  "title": "NotebookLMJobRequest",
  "type": "object",
  "additionalProperties": false,
  "required": ["job_id", "subject", "mode", "source_list",
               "discord_context"],
  "properties": {
    "job_id":  {"type": "string", "format": "uuid"},
    "subject": {"type": "string", "minLength": 40, "maxLength": 400},
    "mode":    {"type": "string", "enum": ["podcast", "video"]},
    "style":   {"type": ["string", "null"], "maxLength": 64},
    "source_list": {
      "type": "array", "minItems": 5, "maxItems": 15,
      "items": {"$ref": "https://podcast.local/schemas/sources.json#/properties/sources/items"}
    },
    "discord_context": {
      "type": "object", "additionalProperties": false,
      "required": ["user_id", "channel_id"],
      "properties": {
        "user_id":    {"type": "string", "pattern": "^[0-9]{15,25}$"},
        "channel_id": {"type": "string", "pattern": "^[0-9]{15,25}$"},
        "locale":     {"type": "string", "enum": ["fr", "en"], "default": "fr"}
      }
    }
  }
}
```

### 3.5 NotebookLM job result (worker → n8n callback body core)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://podcast.local/schemas/notebooklm-job-result.json",
  "title": "NotebookLMJobResult",
  "type": "object",
  "additionalProperties": false,
  "required": ["job_id", "status"],
  "properties": {
    "job_id":  {"type": "string", "format": "uuid"},
    "status":  {"type": "string",
                "enum": ["delivered", "failed"]},
    "artifact": {
      "type": "object", "additionalProperties": false,
      "required": ["path_or_url", "kind", "size_bytes", "sha256", "duration_seconds"],
      "properties": {
        "path_or_url":     {"type": "string"},
        "kind":            {"type": "string", "enum": ["file", "url"]},
        "mime":            {"type": "string", "enum": ["audio/mpeg", "video/mp4"]},
        "size_bytes":      {"type": "integer", "minimum": 1},
        "sha256":          {"type": "string", "pattern": "^[a-f0-9]{64}$"},
        "duration_seconds":{"type": "number", "minimum": 0}
      }
    },
    "error": {
      "type": "object", "additionalProperties": false,
      "required": ["stage", "code", "message"],
      "properties": {
        "stage":   {"type": "string",
                    "enum": ["gemini", "source_validation",
                             "notebooklm_upload", "notebooklm_generate",
                             "download", "delivery"]},
        "code":    {"type": "string", "minLength": 1, "maxLength": 64},
        "message": {"type": "string", "minLength": 1, "maxLength": 500}
      }
    }
  },
  "allOf": [
    {"if": {"properties": {"status": {"const": "delivered"}}},
     "then": {"required": ["artifact"]}},
    {"if": {"properties": {"status": {"const": "failed"}}},
     "then": {"required": ["error"]}}
  ]
}
```

### 3.6 Discord final response (n8n → Discord channel.send)

n8n constructs this from the job result; not user-facing JSON, but a contract
to keep the formatter predictable.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://podcast.local/schemas/discord-response.json",
  "title": "DiscordResponse",
  "type": "object",
  "additionalProperties": false,
  "required": ["channel_id", "content", "kind"],
  "properties": {
    "channel_id": {"type": "string", "pattern": "^[0-9]{15,25}$"},
    "user_mention": {"type": "string", "pattern": "^<@[0-9]{15,25}>$"},
    "content":    {"type": "string", "minLength": 1, "maxLength": 2000,
                   "description": "French caption (subject + duration) or French error."},
    "kind":       {"type": "string",
                   "enum": ["attachment", "signed_url", "error"]},
    "attachment_path": {"type": ["string", "null"]},
    "signed_url":      {"type": ["string", "null"], "format": "uri"},
    "signed_url_expires_at": {"type": ["string", "null"], "format": "date-time"}
  },
  "allOf": [
    {"if": {"properties": {"kind": {"const": "attachment"}}},
     "then": {"required": ["attachment_path"]}},
    {"if": {"properties": {"kind": {"const": "signed_url"}}},
     "then": {"required": ["signed_url", "signed_url_expires_at"]}}
  ]
}
```

---

## 4. State model — `podcast.jobs`

Single `init.sql` file at `./db/init.sql`, patterned on
`refs/veille_auto/scripts/init.sql:1-67`. Below is the **podcast-specific
DDL**; the file MUST also create the `podcast` schema and the existing
trigger function (`update_updated_at_column`) if not present.

```sql
-- ==========================================
-- PODCAST PIPELINE SCHEMA
-- Pattern reference: refs/veille_auto/scripts/init.sql:1-3
-- ==========================================

CREATE SCHEMA IF NOT EXISTS podcast;

-- Status state machine (D7: linear, explicit fail).
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

CREATE TABLE IF NOT EXISTS podcast.jobs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Discord trigger context
    interaction_id      TEXT NOT NULL UNIQUE,
    -- UNIQUE protects against double-submit; idempotency by (user_id, subject_hash, mode, style) is a separate concern handled by uq_jobs_delivered_idempotency.
    user_id             VARCHAR(32) NOT NULL,
    channel_id          VARCHAR(32) NOT NULL,
    guild_id            VARCHAR(32),
    locale              VARCHAR(8)  NOT NULL DEFAULT 'fr',
    -- Request
    subject             TEXT        NOT NULL CHECK (char_length(subject) BETWEEN 40 AND 400),
    subject_hash        CHAR(64)    NOT NULL,  -- sha256(lower(normalize(subject)))
    mode                VARCHAR(16) NOT NULL CHECK (mode IN ('podcast','video')),
    style               VARCHAR(64),
    -- Lifecycle
    status              podcast.job_status NOT NULL DEFAULT 'queued',
    attempt             SMALLINT    NOT NULL DEFAULT 1 CHECK (attempt BETWEEN 1 AND 3),
    -- Payload (full NotebookLMJobRequest, §3.4)
    payload             JSONB       NOT NULL,
    -- Artifact
    artifact_url        TEXT,
    artifact_size_bytes BIGINT,
    artifact_sha256     CHAR(64),
    artifact_duration_s NUMERIC(8,2),
    -- Failure (NotebookLMJobResult.error, §3.5)
    error_stage         VARCHAR(32),
    error_code          VARCHAR(64),
    error_message       TEXT,
    -- Audit
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at          TIMESTAMPTZ,
    finished_at         TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

-- Helper view for the bot idempotency lookup.
-- Use this view — not the raw table — for all 24-h duplicate checks.
CREATE OR REPLACE VIEW podcast.recent_delivered AS
    SELECT *
    FROM podcast.jobs
    WHERE status = 'delivered'
      AND created_at > NOW() - INTERVAL '24 hours';

-- Bot pre-flight idempotency lookup queries podcast.recent_delivered,
-- not podcast.jobs directly (see PLAN §3.5).

CREATE INDEX IF NOT EXISTS idx_jobs_status_created
  ON podcast.jobs (status, created_at)
  WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS idx_jobs_user_created
  ON podcast.jobs (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_jobs_interaction
  ON podcast.jobs (interaction_id);

-- Reuse updated_at trigger pattern from refs/veille_auto/scripts/init.sql:41-54
DROP TRIGGER IF EXISTS update_podcast_jobs_updated_at ON podcast.jobs;
CREATE TRIGGER update_podcast_jobs_updated_at
  BEFORE UPDATE ON podcast.jobs
  FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Per-user daily count (M2 quota enforcement, evaluated by n8n on trigger).
CREATE OR REPLACE FUNCTION podcast.count_user_today(uid VARCHAR)
RETURNS INTEGER AS $$
  SELECT COUNT(*)::INTEGER
    FROM podcast.jobs
   WHERE user_id = uid
     AND created_at > NOW() - INTERVAL '24 hours'
     AND status NOT IN ('failed');
$$ LANGUAGE sql STABLE;
```

Notes:
- `gen_random_uuid()` requires `pgcrypto`; bootstrap with `CREATE EXTENSION
  IF NOT EXISTS pgcrypto;` (n8n image's Postgres 16 ships it).
- DB PK is `id` (UUID); §3.4 envelope field `job_id` is the request-correlation
  handle passed through the queue and callback — distinct concept from the DB PK.
- Partial unique index gives idempotency without blocking deliberate
  retries after failure (failed rows are excluded so user can re-trigger).
- The status enum is the **only** allowed lifecycle alphabet; transitions
  enforced in worker code, not by DB (keep DDL simple).

---

## 5. Secret surface — exhaustive

| Secret                              | Where stored                         | Consumer container | Why needed                                                                              | File vs var |
|-------------------------------------|--------------------------------------|--------------------|-----------------------------------------------------------------------------------------|-------------|
| `POSTGRES_USER`                     | `.env`                               | postgres, n8n, worker | DB auth                                                                                | var         |
| `POSTGRES_PASSWORD`                 | `.env`                               | postgres, n8n, worker | DB auth                                                                                | var         |
| `POSTGRES_DB`                       | `.env`                               | postgres, n8n, worker | DB selection                                                                           | var         |
| `N8N_ENCRYPTION_KEY`                | `.env`                               | n8n                | Encrypt stored credentials in n8n (pattern: veille_auto compose:40)                    | var         |
| `DISCORD_BOT_TOKEN`                 | `.env`                               | discord-bot, n8n   | Bot REST API auth (n8n posts artifacts via bot, D2); slash-command registration        | var         |
| `DISCORD_PUBLIC_KEY`                | `.env`                               | discord-bot        | Verify Ed25519 signature on Discord interaction HTTP callbacks                         | var         |
| `DISCORD_APP_ID`                    | `.env`                               | discord-bot        | Slash-command registration scope                                                       | var         |
| `GEMINI_API_KEY`                    | `.env`                               | browser-worker     | Source curation call                                                                   | var         |
| `GEMINI_MODEL`                      | `.env`                               | browser-worker     | Model selection (default `gemini-2.5-pro`)                                             | var         |
| `GOOGLE_BURNER_EMAIL`               | `.env`                               | browser-worker     | Initial Playwright login fallback if `storageState` invalid (one-time human-in-loop)   | var         |
| `GOOGLE_BURNER_PASSWORD`            | `.env` (burner account; critique H2)| browser-worker     | Same as above. App-password preferred over real password if 2FA is enabled.            | var         |
| `GOOGLE_BURNER_TOTP_SEED`           | `.env` (optional)                    | browser-worker     | 2FA seed if app-passwords disabled (critique H4 #2)                                    | var         |
| `NOTEBOOKLM_STORAGE_STATE_PATH`     | `.env` value, **file at path**       | browser-worker     | Playwright `storageState.json` location inside worker volume. **chmod 600, owner = worker UID.** Equivalent to bearer credential (D3). | path-var pointing to file |
| `WORKER_SHARED_TOKEN`               | `.env`                               | n8n, browser-worker, discord-bot (for outbound→n8n) | HMAC/bearer for internal endpoints (§2.1)                       | var         |
| `RATE_LIMIT_PER_USER_DAY`           | `.env`                               | n8n                | M2 / D5 enforcement (default 3)                                                        | var         |
| `RATE_LIMIT_GLOBAL_DAY`             | `.env`                               | n8n                | M2 / D5 (default 20)                                                                   | var         |
| `KILL_SWITCH`                       | `.env`                               | n8n                | Hard stop; integer string `"0"` (off) or `"1"` (on) — compare with `== "1"`, not truthiness | var         |
| `TZ`                                | `.env`                               | all                | Europe/Paris (pattern: veille_auto compose:13)                                         | var         |

Hard rules:
- `env.template` contains placeholders only (`AGENT_CONDUCT.md` §1.4).
- `storageState.json` is **never** committed; the `data/worker/session/`
  directory is in `.gitignore`.
- No real default in `os.getenv(...)`-equivalent calls.

## 5.bis Deferred secrets (Phase 4 — pending Q3)

Consumed only once Q3 selects an object-storage backend; if Q3 picks external S3/R2 the names change.

| Secret                         | Where stored | Consumer container         | Why needed                                    | File vs var |
|--------------------------------|--------------|----------------------------|-----------------------------------------------|-------------|
| `MINIO_ROOT_USER`              | `.env`       | minio, browser-worker, n8n | MinIO admin + presign credentials             | var         |
| `MINIO_ROOT_PASSWORD`          | `.env`       | minio, browser-worker, n8n | Same                                          | var         |
| `MINIO_BUCKET`                 | `.env`       | browser-worker, n8n        | Bucket name (default `podcast-artifacts`)     | var         |
| `MINIO_SIGNED_URL_TTL_SECONDS` | `.env`       | n8n                        | Default 86400 (24 h)                          | var         |

---

## 6. Failure modes & retry policy

Per-boundary table. "Stage" maps to `NotebookLMJobResult.error.stage` (§3.5).

| # | Boundary                              | Failure mode                                            | Timeout      | Retry policy                                                            | Citation                       |
|---|---------------------------------------|---------------------------------------------------------|--------------|-------------------------------------------------------------------------|--------------------------------|
| F1| Discord → discord-bot interaction     | Signature invalid; 3 s ack missed                       | 2.5 s ack    | None (interaction lost); log + admin webhook                            | requirements.md AC1.1; D2      |
| F2| discord-bot → n8n webhook             | n8n 5xx / connection refused                            | 5 s          | 3× exponential backoff (1/3/9 s); on final fail, ephemeral FR error to user | requirements.md §Guardrails 7 |
| F3| n8n → Postgres (enqueue)              | DB unreachable                                          | 5 s          | 2× retry; on final fail, bot posts FR error in channel                  | critique.md M3                 |
| F4| Redis LPUSH → browser-worker          | Missed LPUSH (worker down or Redis restart); malformed JSON envelope in queue | n/a | Worker 30 s tick polls Postgres `queued AND created_at < NOW()-30s` (§2.2). A popped value that fails `JSON.parse` is a poison message: log error + alert, ACK-and-discard (do not re-push), then emit a synthetic `failed` transition for the affected `job_id` if it can be recovered from context, else log and skip. | §2.2 lost-LPUSH recovery |
| F5| browser-worker → Gemini API (stage `gemini`)         | 5xx, timeout, schema-invalid response   | 60 s         | 2× exp backoff (5 s / 20 s); abort to `failed` after that               | requirements.md §Guardrails 7  |
| F6| source validation (stage `source_validation`)        | <5 live sources after HEAD-check        | 90 s total   | 1× retry of Gemini with broader prompt; else `failed`                   | requirements.md AC2.3; M2 in critique |
| F7| browser-worker → NotebookLM login                    | `storageState.json` expired; CAPTCHA    | 30 s         | Try cached session once; on fail, do NOT auto-retry login. Surface `CAPTCHA_REQUIRED` + admin Discord webhook | critique.md H2, H4; requirements.md edge cases 8/9 |
| F8| NotebookLM source upload (stage `notebooklm_upload`) | Per-source upload error                 | 180 s total  | Continue if ≥80 % succeed (AC3.3). 1× full-stage retry on hard failure  | requirements.md AC3.3          |
| F9| NotebookLM generate (stage `notebooklm_generate`)    | UI selector drift; generation never completes | 600 s   | No retry (cost). Mark `failed`, capture screenshot+DOM+HAR to debug volume | critique.md M4; requirements.md §Scope Risks 1 |
| F10| Artifact download (stage `download`) | Network mid-download                                    | 120 s        | 2× retry                                                                | inferred from M4               |
| F11| worker → n8n callback                | n8n 5xx                                                 | 10 s         | 3× exp backoff (2/8/32 s). On final fail, worker still updates row to `failed`; admin webhook fires | critique.md M3                |
| F12| n8n → Discord post-back              | [Deferred Phase 4] >25 MB artifact OR Discord 5xx      | 30 s         | If >25 MB → switch to object-storage signed URL (D6, AC5.2; backend pending Q3). Discord 5xx: 3× retry | requirements.md AC5.1/5.2     |
| F13| n8n quota check                      | Per-user or global rate limit exceeded                  | n/a          | Reject before enqueue; ephemeral FR message; do NOT enqueue             | critique.md M2; D5             |
| F14| Object storage unavailable           | [Deferred Phase 4] Bucket write fails for fallback case | 15 s         | 2× retry; on final fail, post FR error (applies once Phase 4 backend is active) | inferred from D6          |
| F15| `KILL_SWITCH=1`                      | All new triggers must reject                            | n/a          | n8n trigger workflow first-step gate; FR message "service en pause"     | critique.md M2; D5             |

Cross-cutting:
- Every stage transition is a **single UPDATE**; no partial state writes.
- Every `failed` write captures `error.stage`, `error.code`, `error.message`
  (≤500 chars, FR-translation happens in n8n during Discord post-back so the
  DB stays English/dev-facing per `AGENT_CONDUCT.md` §1.5).
- Debug-volume captures (F9) are mandatory: `page.screenshot()`, `dom.html`,
  `network.har` keyed by `job_id`.

---

## 7. Out-of-scope (called out explicitly)

- **Fallback TTS path** (ElevenLabs etc.) — `critique.md` H2 mitigation, but
  user has not confirmed; future milestone.
- **Mention-based trigger** — slash-command MVP only (`requirements.md`
  decided).
- **Video mode** in MVP — gate behind `mode=podcast` first; design supports
  both but `critique.md` open-question suggests audio-first.
- **OAuth-per-user** Google auth — single service (burner) account for MVP.
- **GDPR retention policy**, **moderation/abuse filter** beyond
  prompt-injection strip — flagged in critique gap analysis; require
  product decisions before design.

---

## 8. Acceptance checklist (for downstream `architect` / `critic` review)

- [ ] Every container in §1.1 has env, volumes, healthcheck specified.
- [ ] Redis BRPOP/LPUSH queue choice rationale (§2.2) holds against load
      assumption "1 in-flight + 4 queued".
- [ ] All six JSON Schemas (§3) validate the canonical happy-path payload.
- [ ] `podcast.jobs` DDL compiles cleanly on fresh Postgres 16; idempotency
      index excludes `failed` rows so retries work.
- [ ] Every secret in §5 appears in `env.template` as a placeholder, never
      a realistic default.
- [ ] Every boundary in `requirements.md` ACs is covered by a row in §6.

---

## 9. ADR (Architecture Decision Record)

**Decision.** Three-container split (`n8n` thin orchestrator, `discord-bot`
dedicated Discord gateway, `browser-worker` Python+Playwright) communicating
via Redis `LPUSH`/`BRPOP` queue on list `podcast:jobs` and bidirectional
REST callbacks, with a pluggable object-storage seam as artifact fallback above
the Discord 25 MB cliff (backend selection deferred to Phase 4 Q3; see §1.6).

**Drivers.** D1–D9 above. The dominant ones are D1 (n8n cannot host the
browser step), D2 (Discord 15 min interaction wall), D3 (`storageState.json`
is the real credential), D4/D5 (idempotency + kill switch are pre-deploy
requirements).

**Alternatives considered.**
- **A. n8n hosts Playwright via `Execute Command`.** Rejected: H1 in
  critique. Single long node blocks the worker; redeploys lose state.
- **B. Postgres-only queue (no Redis).** Rejected in favour of the Redis
  `LPUSH`/`BRPOP` queue (IMPLEMENTATION_PLAN.md §1). Redis is already in the
  stack and `BRPOP` blocks without polling; the `podcast:jobs` list on
  `redis://redis:6379/0` is the chosen transport. Lost-LPUSH recovery is
  handled by the 30 s Postgres polling tick (§2.2).
- **C. Single Python service replacing n8n entirely.** Rejected: user
  brief mandates n8n; veille_auto stack (D9) is the reuse pattern. n8n's
  visual workflow value still applies to the trigger/format/post-back
  parts.
- **D. Discord webhook-only (no bot).** Rejected: webhooks cannot send
  file attachments larger than 8 MB on free tier and cannot mention users
  cleanly for the post-back; bot REST is required for D2 compliance.

**Why chosen.** Smallest topology that respects every HIGH-severity finding
in `critique.md` (H1/H2/H3/H4), preserves the linear happy path (D7),
reuses veille_auto patterns (D9), and keeps the secret surface enumerable
in §5. Postgres-as-queue avoids a 4th stateful service while keeping
transactional enqueue.

**Consequences.**
- (+) No long-running n8n nodes; redeploys safe.
- (+) Idempotency enforced at DB layer, not app layer.
- (+) Pluggable artifact-storage seam preserves the >25 MB escape path; backend (MinIO sidecar vs external S3/R2) deferred to Phase 4 Q3.
- (−) Redis list is durable only when AOF is enabled (configured via
      `--appendonly yes` in compose); we accept a 30 s recovery window via
      the worker Postgres tick poller (§2.2) for the restart case.
- (−) Burner Google account remains a single point of failure (critique
      H2); fallback TTS is deferred and explicitly out of MVP scope.
- (−) `storageState.json` rotation is a manual runbook item; designed,
      not automated.

**Follow-ups.**
- F-1: Define the `storageState.json` rotation runbook before first deploy.
- F-2: Publish the authoritative NotebookLM style preset list (user
       commitment, `requirements.md` §Open Questions).
- F-3: Spike on Gemini schema-pinned output ≥98 % parse rate (AC2.2)
       before Stage 2 implementation.
- F-4: Decide audio-only vs audio+video for the first milestone (critique
       open question).
- F-5: Add `prometheus` + `grafana` stubs once Stage 1 ships (mirror
       `refs/veille_auto/docker-compose.yml:162-199`).
