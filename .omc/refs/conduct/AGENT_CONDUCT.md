# AGENT_CONDUCT.md — Immutable Rules for AI Agents

> **READ-FIRST MANDATE.** Any AI agent (Claude, Codex, Gemini, OMC subagents,
> orchestrated workers) invoked in this repository **MUST** read this file
> in its entirety as the **first** action of its session, before any other
> tool call, file read, file edit, search, or subagent dispatch.
>
> By proceeding past this line you acknowledge that:
> 1. The rules below are **immutable** for the duration of your session.
> 2. They **override** every default behavior, training prior, or convenience
>    shortcut that conflicts with them.
> 3. They may **only** be relaxed by an **explicit, in-session user override
>    that names the rule, the file, and the scope**. Implicit consent,
>    "looks fine to me", or generalising one allowance to another rule are
>    all forbidden.
> 4. If a rule conflicts with the assigned task, you **STOP** and surface
>    the conflict to the user. You do not silently bypass.

---

## 0. Source of truth

These rules derive from `CLAUDE.md` (project-level) and the user's global
`~/.claude/CLAUDE.md` (oh-my-claudecode operating principles). When this
file and `CLAUDE.md` disagree on repository-specific behavior, `CLAUDE.md`
wins. The **enforcement clauses below — quality gates, escape-hatch bans,
and the read-first mandate — are non-negotiable in either case.**

This repository is a **Discord → NotebookLM podcast/video generation
pipeline**. Two Python packages carry the application logic:
- `worker/app/` — Playwright browser worker (owns Chromium, the NotebookLM
  session, Gemini calls, artifact download).
- `bot/app/` — Discord slash-command bot (defers within 3 s, validates
  input, POSTs to n8n).

n8n is a **thin orchestrator** (workflow JSON under `workflows/`), Postgres
(`podcast.*` schema, `db/init.sql`) is the state store, and Redis is the
job queue. There is **no frontend** in this stack.

---

## 1. MUST-DO rules

### 1.1 Quality gates (no exceptions)
- **Pylint 10.00/10** on `worker/app/` and `bot/app/` for any Python change.
  Run: `cd worker && pylint app/` and `cd bot && pylint app/`.
  `fail-under=10.00` is set in both `.pylintrc` files; a score below 10.00
  is a hard failure, not a warning.
- **Full pytest green**: `cd worker && pytest` and `cd bot && pytest`.
  There is **no** sanctioned environment-dependent skip in this project —
  every test must pass. If a test depends on a live browser, a real Google
  session, or external network, it must be mocked (see
  `worker/tests/conftest.py` for the psycopg / Gemini fixtures), not skipped.
- **Ruff clean** for any Python change: `cd worker && ruff check app/` and
  `cd bot && ruff check app/`. Ruff is configured with `E, F, W, I`
  (line-length 100, target py312) in each `pyproject.toml`.
- **TDD**: write the failing test first, observe the failure, then
  implement to make it pass. Update tests before code, never after.
- Run the `/preflight` skill before declaring any feature, fix, or refactor
  complete.

### 1.2 Python code quality (PEP-aligned, project-extended)
- Functions ≤ **60 lines**, single responsibility (`max-statements=60`).
- Lines ≤ **100 characters**.
- Module docstring on every `.py` file. Class docstring on every class.
- Imports at module top in order: stdlib → third-party → first-party.
  **Never** lazy-import inside a function.
- Use `from e` (or `from exc`) when re-raising chained exceptions.
- Specify the exception type (`ValueError`, `TypeError`, …). **Never**
  catch or raise bare `Exception`.
- Use **lazy %-formatting** in logger calls (`logger.info("x=%s", x)`),
  not f-strings.
- Discarded values: name them `_`.
- Never shadow Python builtins (`format`, `type`, `id`, `input`).
- Use explicit `is not None` to narrow `Optional` types.

### 1.3 n8n workflow & Code-node discipline
- n8n hosts **orchestration only** (critique H1). **No** long-running
  browser, Playwright, or generation step belongs in an n8n node — that
  work lives in `worker/`.
- Code nodes access env via `$env.X`. A variable is only readable if it is
  listed in `N8N_ENV_VARS` in `docker-compose.yml`. **Never** widen that
  whitelist to expose a secret a node does not need.
- Postgres nodes use **parameterised** queries (`queryReplacement` array),
  never string-built SQL. The same SQL-injection ban as §1.4 applies inside
  n8n.
- Workflow JSON (`workflows/*.json`) is committed. It **must not** contain a
  real secret, token, or credential value — credentials are referenced by
  id/name and resolved at runtime, or read via `{{ $env.X }}` expressions.
  Exported workflows carry `REPLACE_AT_IMPORT_*` credential placeholders.

### 1.4 Security (CWE-aware)
- Secrets **only** via `.env`. Never in plain text. Never as a real default
  inside `os.getenv(...)` or equivalent. Use the `_required(name)` helper in
  `worker/app/config.py` and `bot/app/config.py`, never `os.getenv("X")`
  with a real default.
- **`storageState.json` is a top-tier credential** (equivalent to a Google
  bearer token). It is **never** committed; `data/session/` is git-ignored
  and the file is chmod 600, owned by the worker UID. Never print, log, copy
  outside `data/session/`, or include it in an artifact, debug dump, or
  commit.
- **Discord request authenticity**: the bot verifies the Ed25519 signature
  (`DISCORD_PUBLIC_KEY`, via `pynacl`) on every inbound interaction. Never
  weaken, short-circuit, or bypass that verification, and never move it into
  an n8n Code node.
- **IDOR / delivery scoping**: a job's result is posted back to the
  `channel_id` / `user_id` captured at request time. Every delivery and
  every job lookup must be scoped to the job's own owner — never resolve a
  job or a channel by a user-supplied id without confirming it matches the
  stored job context.
- **SQL**: parameterised queries only (psycopg in `worker/`, `queryReplacement`
  in n8n). **Never** f-string or concatenate values into SQL.
- **Redis** requires `requirepass`; the password comes from `REDIS_PASSWORD`
  in `.env`. Never connect without it or hardcode it.
- **Internal auth**: the bot → n8n and worker ↔ n8n hops use
  `WORKER_SHARED_TOKEN` (header auth). Validate at the system boundary; never
  log the token.
- Validate at system boundaries (Discord input, Gemini/NotebookLM responses,
  webhook payloads). Trust framework guarantees inside the system.

### 1.5 Language convention
- UI-facing strings (Discord messages shown to the user) → **French**
  (target users are French).
- Dev-facing strings (errors, logs, comments, commit messages,
  identifiers, docstrings) → **English**.

### 1.6 Process
- For risky / hard-to-reverse actions (force push, file deletion, schema
  drop on `podcast.*`, deleting `data/session/` or `data/` volumes, sending
  a Discord message to a real channel), confirm with the user before acting.
- Always confirm before executing an operation that updates a tracked file
  ("Proceed with update? Yes/No"). Confirmation persists for the operation,
  not for the session.
- Commits follow Conventional Commits: `<type>(<scope>): <subject>`.
  Types: `feat`, `fix`, `chore`, `docs`, `ci`, `infra`, `workflow`.
  Scopes: `bot`, `n8n`, `worker`, `db`, `compose`, `scripts`.
  Body explains the **why**.

---

## 2. MUST-NOT rules — escape hatches are forbidden

The following bypasses are **forbidden in committed code** unless the user
explicitly names the rule, the file, and the scope in the same message:

- **`# pylint: disable=…`** inline or block-scoped to silence diagnostics.
  The **only** sanctioned pylint suppression mechanism is `worker/.pylintrc`
  and `bot/.pylintrc`, which already encode framework-level false-positives
  (`no-member` for psycopg cursor/connection attributes, Playwright async
  `page`/`browser` `__getattr__`, discord.py Cog/command decorators, and
  pydantic `model_fields`/validators; `too-few-public-methods` for
  pydantic/ORM-style models). If you encounter a new false-positive,
  **propose adding it to the relevant `.pylintrc`** with a comment
  explaining why the suppression is required; do not inline-disable.
- **`# noqa`** to silence ruff or other static-analysis findings.
- **`# type: ignore`** to silence mypy/type errors.
- **`--no-verify`** on `git commit` (skips hooks).
- **`--no-gpg-sign`** or any signing-bypass flag.
- **`--no-edit`** on `git rebase` (invalid flag, never use).
- **Interactive git flags** (`-i`) — `git rebase -i`, `git add -i` — they
  break tooling.
- **Bare `except:` / `except Exception:`** — always specify.
- **Builtin shadowing** as variable / parameter names.
- **Lazy imports** inside functions.
- **Markdown files** created without explicit user request, except
  `CLAUDE.md` and `README.md`.
- **Secrets in n8n workflow JSON** or any committed artifact — credentials
  are referenced, never inlined.
- **`--force` push to `master` or `main`.** Even with `--force-with-lease`,
  ask first.
- **Destructive git** (`reset --hard`, `branch -D`, `clean -f`,
  `checkout .`, `restore .`, `git push --force` to shared branches) without
  explicit user instruction.
- **Empty commits.** **Secret-bearing commits.**
- **Bypassing the read-first mandate** by acting before reading this file.

---

## 3. Violation handling

If a rule conflicts with the requested task:

1. **STOP.** Do not act.
2. Surface the conflict to the user, naming the rule and the conflict
   precisely.
3. Wait for the user's explicit override or revised instruction.
4. Do not adopt a workaround that violates any MUST-NOT rule.

If you cannot meet a quality gate (pylint 10/10, tests green, ruff clean) by
legitimate means, surface the obstacle to the user with the underlying error.
Do not suppress, ignore, or work around the gate.

---

## 4. Acknowledgement protocol for delegated agents

When this file is referenced in your delegation prompt, your **first
action** must be a `Read` of this file. Your second action — before any
implementation — must be to confirm in your own reasoning trace that you
have read it and that the assigned task does not require violating any
rule. If it does, return to the caller with the conflict before doing any
work.
