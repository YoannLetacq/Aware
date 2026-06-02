# AGENT_CONDUCT.md — Immutable Rules for AI Agents (TEMPLATE)

> Reusable template. Replace every `{{PLACEHOLDER}}`, then save as
> `AGENT_CONDUCT.md`. Delete any §/bullet that does not apply to the
> target project (e.g. drop the frontend or n8n sections if absent).

## Placeholder legend

| Placeholder | Meaning | Example |
| --- | --- | --- |
| `{{PROJECT_SUMMARY}}` | One-paragraph description of the stack | "Discord → NotebookLM pipeline…" |
| `{{CODE_ROOTS}}` | Python packages under quality gates | `worker/app/`, `bot/app/` |
| `{{LINT_CMDS}}` | Pylint invocation(s) | `cd worker && pylint app/` |
| `{{TEST_CMDS}}` | Test invocation(s) | `cd worker && pytest` |
| `{{EXTRA_LINT_CMDS}}` | Other linters (ruff/eslint/…), or remove | `ruff check app/` |
| `{{TEST_SKIP_EXCEPTION}}` | Sanctioned env-dependent skips, or "none" | none |
| `{{PYLINTRC_PATHS}}` | `.pylintrc` location(s) | `worker/.pylintrc` |
| `{{SANCTIONED_DISABLES}}` | Framework false-positives encoded there | `no-member` (psycopg) |
| `{{TOP_TIER_CREDENTIAL}}` | Bearer-equivalent secret file, if any | `storageState.json` |
| `{{SECURITY_SURFACE}}` | Project-specific security concerns | Ed25519, SQL, IDOR… |
| `{{CONFIG_HELPER}}` | Required-env helper | `_required(name)` |
| `{{LANG_UI}}` / `{{LANG_DEV}}` | Language convention | French / English |
| `{{COMMIT_TYPES}}` / `{{COMMIT_SCOPES}}` | Conventional-commit vocab | feat,fix… / bot,worker… |
| `{{DESTRUCTIVE_TARGETS}}` | Irreversible local targets | schema, `data/` volumes |

---

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
>    that names the rule, the file, and the scope**.
> 4. If a rule conflicts with the assigned task, you **STOP** and surface
>    the conflict to the user. You do not silently bypass.

---

## 0. Source of truth

These rules derive from `CLAUDE.md` (project-level) and the user's global
`~/.claude/CLAUDE.md`. When this file and `CLAUDE.md` disagree on
repository-specific behavior, `CLAUDE.md` wins. The enforcement clauses —
quality gates, escape-hatch bans, read-first mandate — are non-negotiable.

{{PROJECT_SUMMARY}}

---

## 1. MUST-DO rules

### 1.1 Quality gates (no exceptions)
- **Pylint 10.00/10** on {{CODE_ROOTS}} for any change. Run: {{LINT_CMDS}}.
- **Full test suite green**: {{TEST_CMDS}}. Sanctioned skips: {{TEST_SKIP_EXCEPTION}}.
  Anything that depends on a live external system must be mocked, not skipped.
- **Static analysis clean**: {{EXTRA_LINT_CMDS}}.
- **TDD**: write the failing test first, observe failure, then implement.
- Run the `/preflight` skill before declaring any change complete.

### 1.2 Python code quality (PEP-aligned)
- Functions ≤ 60 lines; lines ≤ 100 chars.
- Module docstring per `.py`; class docstring per class.
- Imports at module top (stdlib → third-party → first-party); never lazy-import.
- `from e`/`from exc` on re-raise; specify exception types; no bare `except`.
- Lazy %-formatting in logger calls; name discards `_`; no builtin shadowing.
- Explicit `is not None` to narrow `Optional`.

### 1.3 Orchestrator / workflow discipline (remove if N/A)
- Orchestration tools host **orchestration only** — no long-running compute.
- Workflow definitions are committed and **must not** contain real secrets;
  credentials are referenced, not inlined.
- Any env exposure to in-tool code is whitelist-bound; never widen it to
  expose a secret a node does not need.

### 1.4 Security (CWE-aware)
- Secrets **only** via `.env`. Never plain text. Never a real `getenv` default;
  use `{{CONFIG_HELPER}}`.
- **`{{TOP_TIER_CREDENTIAL}}`** is a bearer-equivalent credential: never
  committed, never logged, never copied outside its store.
- Project security surface (validate, never weaken): {{SECURITY_SURFACE}}.
- **SQL**: parameterised queries only. Never f-string/concatenate into SQL.
- **IDOR**: every resource access scoped to its owner; flag inbound-id lookups.

### 1.5 Language convention
- UI-facing strings → **{{LANG_UI}}**.
- Dev-facing strings (errors, logs, comments, commits, identifiers,
  docstrings) → **{{LANG_DEV}}**.

### 1.6 Process
- Confirm with the user before risky/irreversible actions (force push, file
  deletion, {{DESTRUCTIVE_TARGETS}}, sending external messages).
- Confirm before updating a tracked file ("Proceed with update? Yes/No").
- Conventional Commits: `<type>(<scope>): <subject>`. Types: {{COMMIT_TYPES}}.
  Scopes: {{COMMIT_SCOPES}}. Body explains the **why**.

---

## 2. MUST-NOT rules — escape hatches are forbidden

Forbidden in committed code unless the user names the rule, file, and scope:

- **`# pylint: disable=…`** inline. The only sanctioned suppression is
  {{PYLINTRC_PATHS}}, which encodes framework false-positives
  ({{SANCTIONED_DISABLES}}). New false-positive → propose adding it there.
- **`# noqa`**, **`# type: ignore`** to silence static analysis.
- **`--no-verify`**, **`--no-gpg-sign`**, **`--no-edit`**, interactive `-i`.
- **Bare `except:` / `except Exception:`**; builtin shadowing; lazy imports.
- **Markdown files** without explicit request, except `CLAUDE.md`/`README.md`.
- **Secrets inlined** in workflow definitions or any committed artifact.
- **`--force` push to the main branch** (even `--force-with-lease`: ask first).
- **Destructive git** (`reset --hard`, `branch -D`, `clean -f`, `checkout .`,
  `restore .`, force-push to shared branches) without explicit instruction.
- **Empty commits. Secret-bearing commits.**
- **Bypassing the read-first mandate.**

---

## 3. Violation handling

1. **STOP.** 2. Surface the conflict, naming the rule precisely. 3. Wait for
explicit override. 4. Never adopt a workaround that violates a MUST-NOT rule.
If a quality gate cannot be met legitimately, surface the underlying error —
do not suppress it.

---

## 4. Acknowledgement protocol for delegated agents

When this file is referenced in your delegation prompt, your **first action**
must be a `Read` of it; your **second**, before implementation, is to confirm
in your reasoning trace that the task does not require violating any rule.
