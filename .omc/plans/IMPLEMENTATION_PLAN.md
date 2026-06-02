# Implementation Plan — Discord → NotebookLM Podcast/Video Pipeline

> Authoritative phased plan. Derived from `.omc/research/requirements.md`
> (analyst dossier) and `.omc/research/critique.md` (red-team H1–H4).
> All veille_auto citations refer to `/home/yoann/podcast/.omc/refs/veille_auto/`.
> Authoring constraints: AGENT_CONDUCT.md §1.5 (FR ui / EN dev), §1.4 (secrets),
> MAIN_AGENT_CONDUCT.md §2.5 (dispatch channel).

---

## 1. Top-Level Arborescence

```
podcast/
├── docker-compose.yml              # Orchestration (postgres, n8n, redis, worker)
├── env.template                    # Placeholder secrets only (committed)
├── .env                            # gitignored, chmod 600
├── .gitignore                      # Mirrors veille_auto/.gitignore:1-67
├── README.md                       # FR user intro + EN ops; mirrors veille_auto/README.md
├── CLAUDE.md                       # Agent guidance (this repo)
├── QUICKSTART.md                   # Operator first-run (mirrors veille_auto/QUICKSTART.md)
├── config/
│   └── notebooklm_styles.json      # Authoritative video preset list (user-pasted)
├── db/
│   └── init.sql                    # Postgres schema in `podcast.*`
├── scripts/
│   ├── setup.sh                    # Generates .env, dirs, storageState volume
│   ├── start.sh / stop.sh / restart.sh / status.sh / logs.sh
│   ├── backup.sh / restore.sh
│   └── seed-google-session.sh      # One-shot interactive login → storageState.json
├── workflows/
│   └── pipeline.json               # n8n linear workflow export (≤10 nodes)
├── worker/                         # Playwright browser-worker container (H1)
│   ├── Dockerfile                  # python:3.12-slim + Playwright + chromium
│   ├── pyproject.toml              # ruff/pylint config, deps pin
│   ├── .pylintrc                   # Quality gate (AGENT_CONDUCT §1.1)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                 # Queue listener (Redis BRPOP) entrypoint
│   │   ├── config.py               # Env-loading, no real defaults (§1.4)
│   │   ├── queue.py                # Redis job claim + ack
│   │   ├── selectors.py            # NotebookLM DOM selectors + version const
│   │   ├── session.py              # storageState.json load/validate/refresh
│   │   ├── notebooklm/
│   │   │   ├── login.py
│   │   │   ├── notebook.py         # create, upload sources, customize prompt
│   │   │   ├── generate.py         # audio/video trigger + polling loop
│   │   │   └── download.py
│   │   ├── gemini.py               # Source-curation call w/ response_schema
│   │   ├── validators.py           # Subject, sources liveness, dedup
│   │   ├── delivery.py             # Discord channel.send (NOT interaction token, H3)
│   │   ├── observability.py        # Screenshot/DOM/HAR on failure (M4)
│   │   └── db.py                   # podcast.jobs CRUD
│   └── tests/
│       ├── test_validators.py
│       ├── test_gemini_schema.py
│       └── test_selectors_smoke.py
├── bot/                            # Discord slash-command interactive surface
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py                 # discord.py / interactions client
│   │   ├── commands.py             # /podcast slash command + modal
│   │   ├── validate.py             # Subject length/sentence/strip rules
│   │   ├── webhook_client.py       # POST to n8n /webhook/podcast
│   │   └── config.py
│   └── tests/
└── data/                           # All persistent state (gitignored)
    ├── postgres/                   # mirrors veille_auto/docker-compose.yml:15
    ├── n8n/                        # mirrors veille_auto/docker-compose.yml:82
    ├── redis/
    ├── artifacts/                  # MP3/MP4 outputs by interaction_id
    └── session/                    # storageState.json (chmod 600, restricted volume, H4)
```

**Reused patterns (citations):**
- Docker network + postgres healthcheck → `refs/veille_auto/docker-compose.yml:5-30, 201-203`.
- n8n env whitelist via `N8N_ENV_VARS` → `refs/veille_auto/docker-compose.yml:75`.
- 127.0.0.1-only port bindings → `refs/veille_auto/docker-compose.yml:18, 77, 108`.
- json-file log rotation (10m, 3 files) → `refs/veille_auto/docker-compose.yml:24-28`.
- env.template placeholder-only secrets → `refs/veille_auto/env.template:11, 20, 41, 50`.
- `.env` gitignore + data dirs + OMC state ignore → `refs/veille_auto/.gitignore:6-7, 14-15, 66`.
- Redis lock via webdis pattern (adapt for queue) → `refs/veille_auto/docker-compose.yml:120-160`.
- scripts/setup.sh secret generation via `openssl rand` → `refs/veille_auto/CLAUDE.md` security section.
- init.sql schema bootstrap → `refs/veille_auto/scripts/` `init.sql:1` (entire file model; canonical location in this repo: `db/init.sql`).
- README ops table format → `refs/veille_auto/README.md:124-135`.

---

## 2. Phase Breakdown

### Phase 0 — Scaffolding & Secrets Surface (Day 0)

**Deliverables**
- Repository skeleton (directories, empty `__init__.py`, placeholders).
- `docker-compose.yml` declaring `postgres`, `redis`, `n8n`, `worker`, `bot`.
- `env.template` with placeholders only (covers DISCORD_BOT_TOKEN, DISCORD_APP_ID, DISCORD_PUBLIC_KEY, GEMINI_API_KEY, POSTGRES_*, N8N_ENCRYPTION_KEY, N8N_API_KEY, GOOGLE_BURNER_EMAIL, GOOGLE_BURNER_PASSWORD, GOOGLE_BURNER_TOTP_SEED, RATE_LIMIT_PER_USER_DAY, RATE_LIMIT_GLOBAL_DAY, KILL_SWITCH).
- `.gitignore` extending `veille_auto/.gitignore:1-67` + `data/session/**`, `data/artifacts/**`.
- `scripts/setup.sh` generating `.env`, creating `data/session/` with `chmod 700`, generating empty `storageState.json` placeholder with `chmod 600` (critique H4).
- `db/init.sql` creating `podcast` schema, `podcast.jobs` table (id PK uuid, interaction_id text unique, user_id, channel_id, guild_id, locale, subject, subject_hash, mode, style, status enum, payload jsonb, attempt smallint, gemini_sources jsonb, artifact_path, artifact_sha256, artifact_size_bytes, artifact_duration_s, error_stage, error_code, error_message, started_at, finished_at, created_at, updated_at), `podcast.rate_limits` (user_id, day, count), `podcast.audit_log` (job_id, event, payload jsonb, ts) — addresses critique L3, M3.
- Pylint config + ruff config in `worker/`, `bot/`.

**Acceptance criteria**
- `docker compose config` validates with no warnings.
- `docker compose up postgres` → schema `podcast.*` created; `\dt podcast.*` lists three tables.
- `scripts/setup.sh` is idempotent; second run does not overwrite existing `.env`.
- `gitleaks detect` passes on committed files (no real secret values).
- AC1.* prerequisites: bot infra container exists but is a stub.

**Smallest demo proving phase**
- `./scripts/setup.sh && ./scripts/start.sh && ./scripts/status.sh` returns all services healthy and `podcast.jobs` query returns 0 rows.

**Agent team (MAIN §2.5 routing)**
- `executor` (sonnet) — scaffolds files, writes Dockerfiles, init.sql.
- `executor` (haiku) — generates setup.sh / start.sh / stop.sh / status.sh / logs.sh by adapting `veille_auto/scripts/*.sh`.
- `code-reviewer` (sonnet) — diff review against AGENT_CONDUCT §1.4 secrets rule.
- `verifier` (sonnet) — runs `/preflight` (pylint placeholder, `docker compose config`).

---

### Phase 1 — Discord Slash Command + n8n Webhook Stub (Day 1–2)

**Deliverables**
- `bot/app/commands.py` registering `/podcast subject:str mode:choice[podcast,video] style:choice[optional]` with style choices populated from `config/notebooklm_styles.json` at startup.
- `bot/app/validate.py`: 40–400 chars, ≤2 sentences, strip `<@…>` / backticks / zero-width (AC1.3, critique M1 prompt-injection guard).
- `bot/app/main.py` calling `interaction.response.defer()` within 3 s then `interaction.followup.send("Reçu — génération en cours…")` (critique H3 compliant: stops using interaction token thereafter).
- `bot/app/webhook_client.py` POSTs to `http://n8n:5678/webhook/podcast` with payload schema per AC1.4.
- `workflows/pipeline.json` — n8n workflow with two nodes: Webhook (POST `/podcast`) → Code node that INSERTs into `podcast.jobs` (status='queued') + LPUSH job to `redis://redis:6379/0` queue `podcast:jobs`, then responds 202.

**Acceptance criteria (requirements.md mapping)**
- AC1.1: `/podcast subject:"Les LLM open-source" mode:podcast` → ephemeral FR ack within 2 s.
- AC1.2: `mode:video` without `style` → ephemeral FR error.
- AC1.3: subject 12 chars → FR error listing `min_chars`.
- AC1.4: `podcast.jobs` row present with status='queued' and Redis LIST length increases by 1.
- Linearity check: n8n workflow node count ≤ 4 in this phase.

**Smallest demo proving phase**
- Slash command in test guild creates a `podcast.jobs` row visible via `docker compose exec postgres psql -U podcast -c "SELECT id, status FROM podcast.jobs"`.

**Agent team**
- `executor` (sonnet) — `bot/` Python (discord.py 2.x); n8n JSON crafted by hand against n8n schema.
- `test-engineer` (sonnet) — pytest for `validate.py` covering empty, too-long, mention-strip, sentence count.
- `security-reviewer` (sonnet) — review prompt-injection strip rules + webhook auth (HMAC header secret shared bot↔n8n).
- `verifier` (sonnet) — runtime check via `qa-tester` style invocation.

---

### Phase 2 — Gemini Source Curation (Day 3–4)

**Deliverables**
- n8n workflow extended: after queue push, a parallel branch is NOT added; Gemini is called from the **worker** (linearity preserved: n8n stays trigger/dispatcher per critique H1).
- `worker/app/main.py` BRPOPs `podcast:jobs`; updates `podcast.jobs.status='gemini_running'`.
- `worker/app/gemini.py` calls Gemini with `response_mime_type=application/json` + `response_schema` matching the Sources contract (requirements §Gemini Prompt Contract).
- `worker/app/validators.py`: schema parse → URL HEAD liveness (5 s timeout, parallel) → URL normalize + dedup → type-mix check (≥1 academic, ≥1 video) → count 5≤n≤15.
- Retry budget: 2 retries with exponential backoff (5 s / 20 s), broader prompt on retry per requirements §Retry budget.
- Persist validated sources to `podcast.jobs.gemini_sources` jsonb.

**Acceptance criteria**
- AC2.1 (system prompt EN), AC2.2 (parse success ≥98 % on local 50-call dry run), AC2.3 (count 5–15 enforced), AC2.4 (each source carries required fields).
- On vague subject (e.g., `"IA"`), pipeline aborts with FR Discord message via fresh channel.send (NOT interaction token, H3). Job status='failed', error_stage='gemini', error_code='SUBJECT_TOO_NARROW'.

**Smallest demo proving phase**
- Trigger `/podcast subject:"Les modèles de langage open-source en 2025" mode:podcast` → `podcast.jobs.gemini_sources` jsonb contains 5–15 validated sources, status advances to `gemini_done`.

**Agent team**
- `executor` (opus) — Gemini JSON-mode integration (SDK choice matters; consult `document-specialist` for current `google-genai` Python SDK contract).
- `document-specialist` (haiku) — fetch current `google-genai` SDK doc for `response_schema` usage; pin SDK version.
- `test-engineer` (sonnet) — fixture-based tests with recorded Gemini responses (no live calls in CI).
- `critic` (sonnet) — challenge subject-validator edge cases.

---

### Phase 3 — Playwright Browser-Worker: NotebookLM Upload (Day 5–7)

**Deliverables**
- `worker/Dockerfile` with `mcr.microsoft.com/playwright/python:v1.50.0-noble` base (pinned), non-root user, mounts `data/session/` as restricted volume (`chmod 600`, owned by worker UID per critique H4).
- `worker/app/session.py`: load `storageState.json`; on cold start, validate via a probe page-load; if invalid, mark job 'failed' with `SESSION_EXPIRED` and DM operator via separate `OPERATOR_DISCORD_WEBHOOK` (critique observability M4).
- `scripts/seed-google-session.sh`: interactive one-shot Playwright `headed` run to perform first login on burner Workspace account (critique H2) + 2FA + storeState dump. Documented runbook only — never automated.
- `worker/app/notebooklm/login.py`: open `notebooklm.google.com`, validate session.
- `worker/app/notebooklm/notebook.py`: create notebook titled `{subject_first_60_chars} — {iso_date}` (AC3.2); upload all sources (link-add for URLs); record per-source success/fail; FR customization prompt set on notebook.
- `worker/app/selectors.py`: every NotebookLM DOM selector centralized + `SELECTORS_VERSION` constant.
- `worker/app/observability.py`: on any exception → `page.screenshot(path=...)`, dump DOM, dump last 50 requests (HAR via context tracing), upload paths into `podcast.audit_log`.

**Acceptance criteria**
- AC3.1: cold-start session probe < 30 s.
- AC3.2: notebook title format verified.
- AC3.3: upload success ≥ 80 % else abort with logged drop reasons.
- AC3.4: notebook customization prompt set in FR.
- H4 evidence: `ls -la data/session/storageState.json` shows mode 0600 owned by worker UID; volume mount declared `read_only: false` only for the worker service.

**Smallest demo proving phase**
- Manual queue inject of a known-good source set → notebook appears in NotebookLM UI under burner account with all sources visible; `podcast.jobs.status='notebooklm_uploading'` transitions to `notebooklm_generating` once upload completes.

**Agent team**
- `architect` (opus) — selector strategy + session-rotation runbook design (high-risk per H2/H4).
- `executor` (opus) — Playwright async code, error handling, session persistence.
- `document-specialist` (sonnet) — fetch Playwright `storageState` + tracing docs.
- `security-reviewer` (opus) — audit volume permissions, file mode, secret handling.
- `critic` (sonnet) — adversarial review of selector resilience.

---

### Phase 4 — Generation, Polling, Artifact, Discord Reply (Day 8–10)

**Deliverables**
- `worker/app/notebooklm/generate.py`: branch on `mode`:
  - `podcast`: click "Generate Audio Overview"; poll `is_complete` selector with backoff 10 s → 30 s → 60 s, hard cap 600 s per requirements §pipeline timeout.
  - `video`: select style from config, click "Generate Video Overview"; same polling, hard cap 600 s.
- `worker/app/notebooklm/download.py`: capture download to `data/artifacts/{interaction_id}.{mp3|mp4}`; compute SHA-256; size logged (AC4.4).
- `worker/app/delivery.py`: post as fresh channel message via Discord REST `POST /channels/{channel_id}/messages` with `Authorization: Bot $DISCORD_BOT_TOKEN` — explicitly NOT via interaction follow-up webhook (critique H3).
  - If file size ≤ 25 MB → attach directly (AC5.1).
  - Else → upload to object storage (decision deferred to Open Q below) → post signed URL with FR caption + expiry (AC5.2).
- `worker/app/db.py`: status transitions queued → gemini_running → gemini_done → notebooklm_uploading → notebooklm_generating → delivered; or → failed at any stage with `error_stage`.
- n8n workflow gets a second webhook endpoint `/webhook/job-complete` purely for audit-trail mirroring (optional, off by default — keeps n8n ≤10 nodes).

**Acceptance criteria**
- AC4.1, AC4.2 verified by end-to-end run with a known subject.
- AC4.3: filename matches `{interaction_id}.(mp3|mp4)`.
- AC4.4: `meta.json` next to artifact contains size, sha256.
- AC5.1/5.2/5.3: enforce; FR-only user-facing messages.
- H3 evidence: timing test where worker artificially delays 16 minutes still posts successfully (because channel.send, not interaction token).

**Smallest demo proving phase**
- End-to-end run with `subject:"Histoire courte du transformer"` mode podcast → MP3 attached to originating Discord channel within ~10 min; `podcast.jobs.status='delivered'`.

**Agent team**
- `executor` (opus) — generation polling, retries, download logic.
- `executor` (sonnet) — delivery module + size-branching.
- `test-engineer` (sonnet) — mock-NotebookLM mode for CI (a fake page served locally that mimics the selectors).
- `verifier` (opus) — runs the smallest demo end-to-end; produces evidence.
- `critic` (sonnet) — challenge timing assumptions, polling backoff curve.

---

### Phase 5 — Hardening & Observability (Day 11–13)

**Deliverables**
- Rate limits enforced in bot pre-flight (read `podcast.rate_limits`): 3/user/day, 20/global/day, kill-switch env `KILL_SWITCH=1` returns FR "service temporairement indisponible" (critique M2).
- Idempotency: `subject_hash = sha256(normalize(subject))`; lookup last 24 h via `podcast.recent_delivered` view with same user_id+subject_hash+mode+style; if found, reply with cached artifact link (critique M3).
- CAPTCHA / "Verify it's you" detection (selectors) → status='failed', error_code='CAPTCHA_REQUIRED' → DM operator via `OPERATOR_DISCORD_WEBHOOK` (requirements §edge cases 8–9).
- Style-preset availability check at session start (requirements §edge cases 12).
- Concurrent-invocation cap: worker holds a Redis lock; max 1 in-flight + 4 queued; 6th request gets FR "système occupé" (requirements §edge cases 11).
- Session-rotation runbook in `QUICKSTART.md` (critique H4): how to re-run `seed-google-session.sh` when cookies expire.
- Daily backup script extended to include `data/session/` (encrypted) and `podcast.*` schema dump.
- `scripts/status.sh` extended to show queue depth, in-flight jobs, last successful generation, last failure reason.

**Acceptance criteria**
- 4th request from same user same day → FR rate-limit error; no Gemini call made; no job row created beyond status='rejected'.
- Same user retriggers identical subject within 24 h → cached artifact link returned, no new generation.
- `KILL_SWITCH=1` blocks all `/podcast` invocations.
- Failure-injection: forcibly invalidate `storageState.json` → next job fails fast, operator DM fires, no zombie chromium process.

**Smallest demo proving phase**
- Run 5 sequential `/podcast` calls from same user → first 3 succeed (or queue), 4th rejected with FR message; `KILL_SWITCH=1 docker compose up` blocks any new call.

**Agent team**
- `executor` (sonnet) — rate-limit, idempotency, kill switch.
- `architect` (opus) — concurrency lock model + runbook.
- `security-reviewer` (opus) — final pass on secret rotation, session file handling, GDPR retention.
- `qa-tester` (sonnet) — multi-scenario interactive run.
- `code-reviewer` (sonnet) — full diff review prior to v1.0 tag.

---

## 3. Cross-Cutting Concerns

### 3.1 Secret rotation
- `.env` rotated quarterly; `N8N_ENCRYPTION_KEY` requires re-encrypting stored credentials → documented procedure (don't rotate casually).
- `storageState.json` rotated whenever Google triggers re-auth (manual). Runbook in `QUICKSTART.md`; encrypted backup in `backups/session/` keyed by date.
- Gemini key + Discord bot token rotated independently; both restartable via `docker compose restart worker bot`.
- `gitleaks` runs in CI as a pre-merge gate.

### 3.2 Session-state persistence for browser worker
- Volume: `./data/session:/app/session:rw` mounted **only** in the worker service; owned by worker UID; `chmod 700` on dir, `chmod 600` on file (critique H4).
- Validation: cold-start probe loads `notebooklm.google.com`, asserts a logged-in selector within 30 s; on failure, fail-fast.
- Never committed; gitignore includes `data/session/**`.

### 3.3 Logging strategy
- Container-level: json-file driver, 10 MB rotation, 3 files (mirror `veille_auto/docker-compose.yml:24-28`).
- Application-level: structured JSON logs (`structlog`) with `job_id` correlation; level INFO default, DEBUG via env.
- Failure logs: screenshot + DOM + last 50 network calls written to `data/artifacts/debug/{job_id}/` (critique M4).
- Audit: `podcast.audit_log` records every status transition with payload jsonb.

### 3.4 Error / retry policy
- Gemini: 2 retries, 5 s/20 s backoff; second retry uses broader prompt.
- URL liveness: per-URL no retry (5 s HEAD timeout); below `min_sources` after dedup → 1 retry of Gemini.
- NotebookLM upload: 1 retry per source; per-source failure tolerated up to 20 %.
- NotebookLM generation: no retry on timeout > 600 s; mark failed.
- Discord post: 3 retries with exponential backoff per requirements §retry budget.
- All retries logged in `podcast.audit_log`.

### 3.5 Idempotency table
- `subject_hash` = `sha256(normalize(subject))`.
- Partial unique index `uq_jobs_delivered_idempotency`
  ON `podcast.jobs (user_id, subject_hash, mode, COALESCE(style,'-'))`
  WHERE `status = 'delivered'`.
  (Note: the 24h window CANNOT be expressed in the partial index
   because `NOW()` is not IMMUTABLE.)
- 24h window enforced at SELECT-time via the view
  `podcast.recent_delivered` (see `db/init.sql`):
  `SELECT * FROM podcast.recent_delivered WHERE user_id=$1 AND subject_hash=$2 AND mode=$3 AND COALESCE(style,'-')=$4`.
- On `/podcast` invocation, bot pre-checks against the view; if hit,
  fast-path returns the cached artifact URL.

---

## 4. Open Questions (to resolve before Phase 0 starts)

Consolidated from `requirements.md §Open Questions` minus already-decided items:

1. **Headless-browser host**: confirm "separate `worker` container" (analyst recommendation) — assumed YES per critique H1 mitigation. *Blocking Phase 0.*
2. **Google account model**: single burner Workspace account for MVP — confirm? *Blocking Phase 3.*
3. **Output delivery > 25 MB**: object-storage backend choice — MinIO sidecar (self-hosted, adds 1 container) vs external S3/R2 (zero infra, external dep). *Blocking Phase 4.*
4. **Concurrent pipeline cap**: confirm 1 in-flight + 4 queued. *Blocking Phase 5.*
5. **Authoritative NotebookLM video preset list**: user commitment to paste before Phase 1. *Blocking Phase 1.*
6. **Source count target**: confirm target=8, accept 5–15. *Blocking Phase 2.*
7. **Subject language to Gemini**: FR verbatim with `language_hint=fr`? *Blocking Phase 2.*
8. **Per-user / global rate limits**: confirm 3/user/day, 20/global/day. *Blocking Phase 5.*
9. **CAPTCHA runbook owner**: confirm operator-only for MVP, alert via `OPERATOR_DISCORD_WEBHOOK`. *Blocking Phase 3.*
10. **Cost ceiling per Gemini call**: confirm 50k input / 5k output, retries capped at 2. *Blocking Phase 2.*
11. **Audio-only v1?** (critique H2 mitigation): ship `mode=podcast` first, gate `mode=video` behind a second milestone. *Reshapes Phase 4 scope.*
12. **n8n is a hard constraint?** If user accepts dropping n8n entirely, the worker can subscribe to Discord webhook directly and the architecture simplifies. Per brief: keep n8n. *Already answered — flagged for explicit user reconfirm.*

---

## 5. Risk Register (carry-forward from critique)

| ID | Risk | Mitigation phase |
|----|------|------------------|
| H1 | n8n long-running step | Phase 1 (split), Phase 3 (worker owns generation) |
| H2 | NotebookLM ToS / no API | Phase 3 burner account; fallback TTS deferred post-MVP |
| H3 | Discord 15-min token | Phase 1 (defer+ack), Phase 4 (channel.send for result) |
| H4 | storageState as secret | Phase 0 (volume), Phase 3 (mount + chmod), Phase 5 (rotation runbook) |
| M1 | Prompt injection | Phase 1 (validate.py strip) |
| M2 | Cost/rate limits | Phase 5 (rate_limits + kill switch) |
| M3 | Idempotency | Phase 0 (schema), Phase 5 (lookup) |
| M4 | Observability | Phase 3 (screenshot/HAR) |

---

## 6. Dispatch-Channel Pairing (MAIN_AGENT_CONDUCT.md §2.5)

For each phase, the executor team implements (native Agent, model tier as listed
above) and `omc ask codex` runs a cross-validation pass on the resulting diff
before merge — explicitly per MAIN_AGENT_CONDUCT.md §2.5 "Pairing rule".
Round-1 CCTP reference example applies: native Claude implements, Codex
cross-validates.

---

## 7. Acceptance — Plan Approval Gate

Before Phase 0 dispatch:
- User answers Open Questions 1–11.
- User pastes authoritative video preset list into `config/notebooklm_styles.json` placeholder.
- User confirms object-storage decision (Q3) — if deferred, Phase 4 ships with Discord-attachment-only path and oversized artifacts fail with FR "fichier trop volumineux, fonctionnalité S3 à venir".
