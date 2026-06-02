# CLAUDE.md — Agent Guidance for the Podcast Pipeline Repo

## Project Overview

This repository is an automated **Discord → NotebookLM podcast/video generation pipeline**.

Stack:
- **n8n** — trigger ingestion, rate-limit enforcement, Discord post-back (thin orchestrator only)
- **PostgreSQL** — state store (`podcast.*` schema), idempotency, rate limits, audit log
- **Redis** — job queue (`podcast:jobs` list) + rate-limit counters
- **Playwright worker** (`worker/`) — owns Chromium, NotebookLM session, Gemini calls, artifact download
- **Discord bot** (`bot/`) — slash-command listener, defers within 3 s, validates input, POSTs to n8n

## Conduct Files (READ FIRST)

Every agent operating in this repository **must** read the conduct files before acting:

- `.omc/refs/conduct/AGENT_CONDUCT.md` — immutable rules for all agents (read first)
- `.omc/refs/conduct/MAIN_AGENT_CONDUCT.md` — additional rules for the main orchestrator
- `.omc/refs/conduct/RISK_MANAGEMENT.md` — risk classification & escalation overlay (consult before any risk-bearing action)
- `.omc/refs/conduct/AGENT_SPAWN_DIRECTIVES.md` — roster & headcount for multi-agent / ralph cycles

Reusable, project-agnostic versions of all four live in `.omc/refs/conduct/templates/`.

## Quality Gates

- **Pylint 10.00/10** on `worker/app/` and `bot/app/` for any Python change.
  Run: `cd worker && pylint app/` and `cd bot && pylint app/`.
- **Full pytest green**: `cd worker && pytest` and `cd bot && pytest`.
- Run the `/preflight` skill before declaring any feature, fix, or refactor complete.

## Language Convention (AGENT_CONDUCT §1.5)

- **User-facing strings** → French (target users are French).
- **Dev-facing strings** (errors, logs, comments, commit messages, identifiers, docstrings) → English.

## Python Code Quality (AGENT_CONDUCT §1.2)

- Module docstring on every `.py` file. Class docstring on every class.
- Functions ≤ 60 lines, lines ≤ 100 characters.
- Imports at module top: stdlib → third-party → first-party. Never lazy-import inside a function.
- Use `from e` / `from exc` when re-raising chained exceptions. Never bare `except`.
- Lazy %-formatting in logger calls (`logger.info("x=%s", x)`), not f-strings.
- Never shadow Python builtins (`format`, `type`, `id`, `input`).

## Secret Rules (AGENT_CONDUCT §1.4)

- Secrets **only** via `.env`. Never in plain text. Never as a real default in `os.getenv(...)`.
- `storageState.json` is a top-tier credential (equivalent to a bearer token).
  It is **never** committed; `data/session/` is git-ignored.
- `env.template` contains placeholders only (`CHANGEME_*` / `YOUR_*`).
- Use the `_required(name)` helper in `worker/app/config.py` and `bot/app/config.py`
  instead of `os.getenv("X")` with a real default.

## Architecture Highlights

- **n8n must NOT host long-running steps** (critique H1). Playwright/generation runs in `worker`.
- **Discord 3 s ack** (critique H3): bot defers immediately; result posted via `channel.send`
  with `Authorization: Bot $DISCORD_BOT_TOKEN` — NOT via the interaction follow-up token.
- **Queue transport**: Redis `LPUSH`/`BRPOP` on `podcast:jobs`.
- **Idempotency**: `subject_hash = sha256(lower(strip(subject)))`; partial unique index
  on `(user_id, subject_hash, mode, COALESCE(style, '-'))` where `status = 'delivered'`.
- **Schema isolation**: all tables under `podcast.*`, not `public.*` (critique L3).

## Key File Locations

| Path | Purpose |
|------|---------|
| `docker-compose.yml` | Service orchestration |
| `env.template` | Placeholder secrets (committed) |
| `db/init.sql` | PostgreSQL DDL — `podcast.*` schema |
| `config/notebooklm_styles.json` | Video preset baseline (user to verify against live UI) |
| `worker/app/selectors.py` | All NotebookLM DOM selectors + `SELECTORS_VERSION` |
| `worker/app/config.py` | Env-loading with `_required()` helper |
| `bot/app/config.py` | Same pattern for bot |
| `workflows/pipeline.json` | n8n workflow export |
| `scripts/seed-google-session.sh` | One-shot interactive login → storageState.json |

## Commit Convention

Conventional Commits: `<type>(<scope>): <subject>`.
Types: `feat`, `fix`, `chore`, `docs`, `ci`, `infra`, `workflow`.
Scopes: `bot`, `n8n`, `worker`, `db`, `compose`, `scripts`.
Body explains the **why**.
