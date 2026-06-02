# Veille Auto Reusable Patterns Inventory

## 1. Docker Compose Service Architecture

**Pattern**: n8n + PostgreSQL stack with healthchecks, environment wiring, and per-service logging.

**Citations:**
- `docker-compose.yml:1–31` — PostgreSQL service definition with `healthcheck` (test, interval, retries), volumes mounting `init.sql`, port binding to `127.0.0.1:5433`.
- `docker-compose.yml:32–93` — n8n service definition with healthcheck dependency, environment wiring for DB and Discord, N8N_ENV_VARS whitelist mechanism, file restrictions via `N8N_RESTRICT_FILE_ACCESS_TO`.
- `docker-compose.yml:98–115` — RSSHub and Redis services with healthchecks, bridge network `veille-network`, logging config (json-file, max-size 10m, 3 files).

**Env Wiring Pattern:**
- `docker-compose.yml:39–75` — Complete environment section for n8n; secrets sourced from `.env` (e.g., `${DISCORD_WEBHOOK_URL}`), timezone defaults to `Europe/Paris`.
- `env.template:1–71` — Template structure with sections (PostgreSQL, N8N, Discord, Gemini, Monitoring, RSSHub, Timezone); secure password generation comments; placeholders use `CHANGEME_` prefix or `YOUR_*` convention.

**N8N_ENV_VARS Whitelist:**
- `docker-compose.yml:75` — Explicit whitelist: `DISCORD_WEBHOOK_URL,DISCORD_WEBHOOK_TECH_NEWS,DISCORD_WEBHOOK_COMPANIES,DISCORD_WEBHOOK_REDDIT,DISCORD_WEBHOOK_OTHERS,DISCORD_BOT_TOKEN,DISCORD_ALLOWED_AUTHORS,GEMINI_API_KEY,GEMINI_MODEL,POSTGRES_USER,POSTGRES_PASSWORD,POSTGRES_DB,WEBHOOK_URL,N8N_API_KEY`.

---

## 2. Discord Bot Trigger & Command Parsing

**Pattern**: n8n `discordTrigger` node with mention pattern, `DISCORD_ALLOWED_AUTHORS` whitelist enforcement, and deferred-interaction pattern.

**Trigger Node:**
- `workflow-simplified.json:4–32` — `n8n-nodes-discord-trigger.discordTrigger` with `guildIds`, `channelIds`, and `pattern: "botMention"` for Discord @mention detection.

**Whitelist Enforcement (Code Node):**
- `workflow-simplified.json:34–45` — "Authorize Mention" node parses `$env.DISCORD_ALLOWED_AUTHORS` (comma-separated user IDs), filters input, empty env allows all mentions (backwards compatible).
- `env.template:42–44` — Configuration reference: `DISCORD_ALLOWED_AUTHORS=` (comma-separated Discord user IDs allowed to trigger; empty = anyone).

**Deferred Interaction Pattern:**
- `workflow-simplified.json:47–62` — "Acquire Lock1" node uses Redis (Webdis) to set a lock with execution ID as token; `retryOnFail: true, maxTries: 5, waitBetweenTries: 2000`.
- `workflow-simplified.json:63–96` — "Check lock Result1" conditional node validates lock acquisition; if locked, branches to "already running" message path; else proceeds to processing path.
- `workflow-simplified.json:481–497` — "Release lock" node at end uses Lua EVAL to atomically delete lock only if execution ID matches (safe against stale executions).

---

## 3. Gemini Call Node & Prompt-Injection Pattern

**Pattern**: HTTP POST to Gemini `generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` with prompt-injection guard via JSON parsing and MAX_TOKENS handling.

**Gemini Filter Node:**
- `workflow-simplified.json:363–393` — `n8n-nodes-base.httpRequest` POST to `=https://generativelanguage.googleapis.com/v1beta/models/{{ $env.GEMINI_MODEL }}:generateContent`; headers: `Content-Type: application/json`, `x-goog-api-key: {{ $env.GEMINI_API_KEY }}`.
- `env.template:47–52` — Gemini configuration: `GEMINI_API_KEY` (from aistudio.google.com), `GEMINI_MODEL` (defaults to gemini-pro, suggests gemini-2.0-flash for cost/latency).
- Prompt template (lines 381–382) includes structured output request: `Respond ONLY with JSON` with fields `confidence`, `score`, `reason`, `summary`, `takeaway`, `tag`.

**JSON Parsing & Retry Logic:**
- `workflow-simplified.json:394–406` — "Parse AI Filter" node detects `finishReason === 'MAX_TOKENS'`, attempts JSON parse on truncated response, falls back to `confidence = 0` on parse failure; logs statistics (success/max-tokens/too-short counts).
- Lines 396–405: Cleaning step removes code fence markers (`\`\`\`json`), attempts `JSON.parse(clean)`, catches errors gracefully.

---

## 4. Discord Output Node & Per-Channel Routing

**Pattern**: Dynamic webhook URL routing per source type (Tech News, Company Blogs, Reddit, Other) with embed grouping and Discord API v10 message POST.

**Routing Logic:**
- `workflow-simplified.json:407–419` — "Sort Split & Limit" node maps source types to webhook URLs and metadata; 10-article limit per group; `_webhook`, `_color`, `_label` tags attached per item.
- `env.template:34–39` — Discord webhook configuration: four separate webhooks (`DISCORD_WEBHOOK_TECH_NEWS`, `DISCORD_WEBHOOK_COMPANIES`, `DISCORD_WEBHOOK_REDDIT`, `DISCORD_WEBHOOK_OTHERS`) for per-category routing.

**Embed Formatting & POST:**
- `workflow-simplified.json:451–463` — "Parse & Format Embeds" node builds Discord embeds (title, description, url, color, footer); size limit 5800 chars per payload; embeds grouped by source_type.
- `workflow-simplified.json:464–481` — "Send to Discord" node: POST method to `={{ $json.webhook_url }}` with JSON body `{ content, embeds }`; uses Discord API v10 endpoint structure.

**Sent Marking:**
- `workflow-simplified.json:499–520` — "Mark Sent" node updates `rss_articles.sent_at = NOW()` for all posted URLs; `executeOnce: true` to prevent duplicates; `onError: continueRegularOutput` for resilience.

---

## 5. Scripts: Setup, Start, Stop, Logs, Backup

**Setup Convention:**
- `scripts/setup.sh:1–95` — Idempotent setup: checks Docker/Compose, generates `.env` from `env.template`, auto-generates secure passwords via `openssl rand`, creates directories (`data/postgres`, `data/n8n`, `backups`, `logs`), displays next steps.
- Lines 44–53: Password generation pattern: `openssl rand -base64 32 | tr -d "=+/" | cut -c1-32` for PostgreSQL; `openssl rand -hex 32` for n8n encryption key.

**Start Convention:**
- `scripts/start.sh:1–62` — Pre-flight checks (.env exists, Discord webhook filled), `docker compose up -d`, 30-second init wait, displays service URLs and login info.
- Lines 24–33: Webhook validation pattern—check for placeholder text (`YOUR_WEBHOOK_ID`) and warn user if not filled in.

**Stop Convention:**
- `scripts/stop.sh:1–22` — Single `docker compose down`, reminder that data persists in `./data/`.
- Line 19: Data persistence message: `# ℹ️  Les données sont conservées dans ./data/`.

**Logs Convention:**
- `README.md:131–132` — Logs command pattern: `./scripts/logs.sh {n8n,postgres,rsshub,all}`.

**Backup Convention:**
- `scripts/backup.sh:1–67` — Three-part backup (PostgreSQL dump, n8n tar.gz, .env copy); dated filenames via `DATE=$(date +%Y%m%d_%H%M%S)`; automatic cleanup of backups >7 days old via `find ... -mtime +7 -delete`.
- Lines 34–49: `pg_dump` for DB, `tar -czf` for workflows, `cp .env` for config; line 59–61 shows retention cleanup pattern (keep 7 days).

---

## 6. Env Template Structure & README/QUICKSTART Layout

**Env Template Sections:**
- `env.template:1–71` — Eight sections: PostgreSQL (user, password, db, port), N8N (encryption key, host, port), Discord (4 webhooks, bot token, allowed authors), Gemini (API key, model), Monitoring (optional), RSSHub (optional), Timezone.
- `env.template:6–14` — PostgreSQL section with password generation guidance (`# Générer avec: openssl rand -base64 32`).
- Password generation guidance: comments like `# Générer avec: openssl rand -base64 32` for each secret (lines 9, 19, 58).
- Placeholder convention: `CHANGEME_` for auto-generatable values, `YOUR_` for manual input.

**README.md Layout:**
- `README.md:1–163` — Sections: Architecture (flow diagram), Components (service table with images and ports), Repository layout (tree view), Requirements (hardware, credentials), Setup (installation steps), Configuration (env var table), RSS sources (file format), Database (schema overview), Operations (command table), Security notes, Troubleshooting (link to docs).
- `README.md:65–80` — Setup section: clone, chmod, setup.sh, edit .env, start.sh steps.
- TOC-style organization with code blocks for commands and example SQL queries.

**CLAUDE.md Documentation:**
- Mirrors README structure with emphasis on development tasks: Commands, Configuration files (with security notes), Database schema, n8n workflows, Project structure, Common issues & solutions, Workflow customization (cron, keywords, sources).

---

## 7. .gitignore Conventions

**Patterns:**
- `.gitignore:1–67` — Five categories: Sensitive data (`.env`, `*.pem`, `*.key`, `*.crt`, database/n8n passwords), Persistent data (`data/`, `backups/*.sql`, `backups/*.tar.gz`, `**/logs`), Docker (`docker-compose.override.yml`), System (`.DS_Store`, `.vscode`, `.idea`), Temporaries (`tmp/`, `*.tmp`, `*.bak`, Node/Python caches).
- Lines 55–57: Preservation pattern: `!data/.gitkeep`, `!backups/.gitkeep`, `!logs/.gitkeep` (keep directory structure).
- `.gitignore:5–12` — Secrets exclusion block (lines 5–12): `.env`, `*.pem`, `*.key`, `*.crt`, `.db_password`, `.n8n_password`, `.n8n_encryption_key`.
- Line 66: `.omc/` excluded (OMC state/research files).

---

## 8. Database Schema (init.sql) & Naming Conventions

**Main Table:**
- `scripts/init.sql:6–19` — `rss_articles` table: SERIAL primary key, `url` VARCHAR(2048) UNIQUE NOT NULL (dedup anchor), TEXT fields for title/description/content, VARCHAR for source/source_type/category, timestamps with time zone (published_at, sent_at, created_at, updated_at).
- Lines 24–38: Index strategy—simple indexes on url, sent_at, published_at, source, category; composite indexes `idx_source_sent_at` and `idx_category_published` for hot queries; partial index on sent_at (recent articles only).

**Views & Functions:**
- `scripts/init.sql:70–80` — `article_stats` view: aggregates total/sent/24h/7d counts, source and category cardinality, max(sent_at) for freshness.
- Lines 82–94: `purge_old_articles()` function deletes rows where `COALESCE(sent_at, created_at) < NOW() - INTERVAL '90 days'` (90-day retention policy).
- Lines 96–115: `get_source_stats()` function groups by source, returns counts and last article date per source.
- `scripts/init.sql:40–54` — Trigger function `update_updated_at_column()` auto-sets updated_at on every UPDATE via BEFORE UPDATE trigger.

**Deduplication Functions:**
- `scripts/init.sql:121–152` — `filter_new_urls(text[])` and `check_url_duplicates(text[])` helper functions for n8n queries; JSONB variant `check_url_duplicates_json()` for modern n8n versions.
- Lines 176–200: `process_rss_batch(articles_json JSONB)` — complete batch processing function (new/existing detection).

**Naming Convention:**
- Snake_case for all identifiers (functions, columns, tables).
- Composite index names follow pattern `idx_{column1}_{column2}`.
- Partial index names include the filter condition signature (e.g., `idx_sent_at_recent`).

---

## Key Patterns Summary

1. **Secure Password Generation**: `openssl rand -base64 32` (DB), `openssl rand -hex 32` (encryption keys).
2. **Environment Whitelisting**: Explicit `N8N_ENV_VARS` list in `docker-compose.yml` restricts Code node access.
3. **Redis Locking**: Execution ID as fencing token, Lua compare-and-delete for safe release.
4. **Gemini Error Resilience**: MAX_TOKENS detection, partial JSON parse on truncation, confidence floor (0) for filtering.
5. **Dedup Pattern**: `ON CONFLICT (url) DO NOTHING` at insert, `sent_at` null until successful post.
6. **90-Day Retention**: `COALESCE(sent_at, created_at)` as deletion anchor, automatic purge function.
7. **Per-Source Routing**: source_type tags enable dynamic webhook selection per article group.
8. **Idempotent Setup**: `setup.sh` creates `.env` only if missing; `mkdir -p` for directories.
9. **Dated Backups**: ISO8601-ish filename format `${TYPE}_${DATE}.{sql,tar.gz,bak}` with auto-cleanup >7 days.
10. **Port Binding**: All external bindings to `127.0.0.1`; internal network for Redis/Webdis.

