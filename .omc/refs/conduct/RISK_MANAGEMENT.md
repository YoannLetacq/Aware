# RISK_MANAGEMENT.md — Risk Framework for AI Agents

> **CONSULT-BEFORE-ACTING MANDATE.** Any AI agent (main orchestrator,
> OMC subagent, Codex, Gemini, or orchestrated worker) operating in this
> repository **MUST** consult this file before performing, planning, or
> delegating any action that carries operational, product, or security
> risk. Reading `CLAUDE.md`, `AGENT_CONDUCT.md`, and
> `MAIN_AGENT_CONDUCT.md` comes first; this file tells you **how to weigh
> the risk** of what those files allow.
>
> By proceeding past this line you acknowledge that:
> 1. This framework is **binding** for the duration of your session.
> 2. It **adds** a risk-assessment obligation on top of the conduct
>    files. It never relaxes a single rule in them.
> 3. When a risk is rated **High** or **Critical**, you **STOP** and
>    obtain explicit user confirmation before acting — no exceptions
>    without an explicit, in-session override that names the action,
>    the file, and the scope.
> 4. "Probably fine", "the test passed", or "it's a small change" are
>    **not** risk assessments. A risk assessment names the hazard, the
>    likelihood, the impact, and the mitigation.

---

## 0. Source of truth & precedence

This file derives from `CLAUDE.md`, `AGENT_CONDUCT.md`,
`MAIN_AGENT_CONDUCT.md`, and the user's global `~/.claude/CLAUDE.md`.

Precedence order, highest to lowest:
1. `CLAUDE.md` — repository-specific behavior.
2. `AGENT_CONDUCT.md` — quality gates, escape-hatch bans, read-first
   mandate (non-negotiable).
3. `MAIN_AGENT_CONDUCT.md` — main-agent-only role rules.
4. `RISK_MANAGEMENT.md` (this file) — risk classification and
   escalation overlay.
5. `~/.claude/CLAUDE.md` — global OMC operating principles.

This file **never overrides** a control already mandated by the conduct
files. Where a conduct rule already forbids an action, that ban wins;
this file only adds the duty to **classify and escalate** the risk of
actions the conduct files leave to judgement.

---

## 1. Risk classification model

Every risk-bearing action is scored on two axes, then mapped to a tier.

### 1.1 Likelihood

| Level | Meaning |
| --- | --- |
| **Rare** | Requires an unusual combination of conditions. |
| **Possible** | Could plausibly occur in normal operation. |
| **Likely** | Expected to occur if the action is repeated. |

### 1.2 Impact

| Level | Meaning |
| --- | --- |
| **Minor** | Recoverable in-session, no data/trust loss. |
| **Serious** | Lost work, regression, or incorrect output reaching review. |
| **Severe** | Irreversible data loss, leaked credential, Google-account ban, or wrong content delivered to a real Discord user. |

### 1.3 Tier matrix

|              | Minor   | Serious | Severe   |
| ------------ | ------- | ------- | -------- |
| **Rare**     | Low     | Low     | High     |
| **Possible** | Low     | Medium  | Critical |
| **Likely**   | Medium  | High    | Critical |

### 1.4 Tier → required behavior

- **Low** — proceed; note the risk in your reasoning trace.
- **Medium** — proceed only with a stated mitigation (test, backup,
  verifier pass). Log what the mitigation is.
- **High** — **STOP**. Surface the risk to the user (hazard, tier,
  mitigation) and obtain confirmation before acting or delegating.
- **Critical** — **STOP**. Never proceed on agent judgement alone.
  Requires an explicit user override naming the action, file, and
  scope, **and** a paired verification (e.g. `omc ask codex`
  cross-validation per `MAIN_AGENT_CONDUCT.md` §2.5).

---

## 2. Operational risk (agent actions)

Risk that an agent's own action damages the repository, history, or
running stack.

### 2.1 Catalog

| Hazard | Default tier | Control |
| --- | --- | --- |
| `--force` / `--force-with-lease` push to `master`/`main` | **Critical** | Forbidden without explicit user override (`AGENT_CONDUCT.md` §2). Confirm even with lease. |
| `git reset --hard`, `clean -f`, `checkout .`, `restore .`, `branch -D` | **High** | Forbidden without explicit user instruction. Prefer a safe alternative (stash, new branch). |
| File / directory deletion of tracked content | **High** | Inspect the target first. If it contradicts how it was described, or you did not create it, surface instead of deleting. |
| Deleting / overwriting `data/session/storageState.json` or any `data/` volume (postgres, redis, n8n) | **Critical** | Irreversible: destroys the Google session or the job/state store. Confirm with user; require a backup (`scripts/backup.sh`) first. |
| Drop / destructive migration on the `podcast.*` schema | **Critical** | Confirm with user; require a proven rollback path before applying. `db/init.sql` is idempotent (`IF NOT EXISTS`) — never replace it with a `DROP`-first variant. |
| Editing / re-importing an n8n workflow on the live instance | **High** | Export and back up the current workflow first; an overwrite loses manual credential wiring. Rotating `N8N_ENCRYPTION_KEY` invalidates all stored credentials. |
| Commit that may carry a secret (incl. inline secrets in workflow JSON) | **Critical** | Never commit. Scan staged diff for keys/tokens/`storageState` before any commit. |
| `--no-verify`, `--no-gpg-sign`, `--no-edit`, interactive `-i` flags | **High** | Forbidden (`AGENT_CONDUCT.md` §2). No bypass of hooks/signing. |
| Updating a tracked file | **Medium** | Confirm "Proceed with update? (Yes/No)" before writing. Confirmation persists for the operation, not the session. |
| Main agent implementing directly (outside allowlist) | **High** | Delegate to `executor` per `MAIN_AGENT_CONDUCT.md` §3 unless an exception applies. |

### 2.2 Controls

- Prefer the **reversible** path: a new branch over a force-push, a
  stash over a hard reset, an additive migration over a drop, a workflow
  export before a re-import.
- Before any irreversible action, state the **blast radius** (what is
  lost if this is wrong) in your reasoning trace.
- High/Critical operational actions are confirmed with the user
  **before** any subagent that would perform them is dispatched.

---

## 3. Product risk (pipeline correctness & account safety)

Risk that the pipeline delivers the **wrong content to the wrong user**,
abuses an upstream service, or burns the Google session the whole system
depends on. These are the risks unique to this project: the output is an
AI-generated artifact posted automatically into a real Discord channel,
produced by **driving NotebookLM through an unofficial browser session**.

### 3.1 Catalog

| Hazard | Default tier | Control |
| --- | --- | --- |
| Aggressive / detectable browser automation of NotebookLM triggers a Google **account ban** or lockout | **Critical** | The burner session is the single point of failure for the whole pipeline. Use a dedicated burner Workspace account (never a personal one). Any change to pacing, selectors, login, or CAPTCHA handling in `worker/app/notebooklm/` or `session.py` is **at least High**; never tune toward faster/more-parallel automation without surfacing the ban risk. CAPTCHA / challenge must alert the operator (`OPERATOR_DISCORD_WEBHOOK`), never auto-retry blindly. |
| Artifact delivered to the **wrong** `channel_id` / `user_id` | **Critical** | Delivery (`worker/app/delivery.py`) must resolve the target strictly from the job's stored context, never from a re-derived or user-supplied id. Verify the job→channel mapping after any change to the delivery path. |
| Rate-limit bypass or idempotency failure → duplicate delivery or quota/cost abuse | **High** | The per-user / global daily limits (`RATE_LIMIT_*`) and the 24-h idempotency window (`podcast.recent_delivered` view + `uq_jobs_delivered_idempotency`) are cost and abuse controls. Never weaken or skip them; any change to the enqueue or delivery gate requires a duplicate-delivery test. |
| `storageState.json` expires mid-job and the failure is swallowed | **High** | A `SESSION_EXPIRED` condition must move the job to `failed` with a clear `error_code` and alert the operator — never reported as success or silently retried forever. |
| Gemini returns hallucinated / off-topic sources fed into NotebookLM | **Medium** | Gemini source output is a **suggestion**, not ground truth. Validate the envelope shape and source types at the boundary; a low-quality result is a surfaced outcome, not a silent pass. |
| Job stuck in a non-terminal status (`gemini_running`, `notebooklm_generating`) | **Medium** | Every lifecycle path must reach a terminal state (`delivered` or `failed`) with `finished_at` set. A change to the state machine requires a test proving no path dead-ends. |
| Discord 3-second ack missed (slow validation before defer) | **Medium** | The bot must defer within 3 s (critique H3) and post the result later via `channel.send`. Never add blocking work before the defer. |

### 3.2 Controls

- **Delivered artifacts are advisory until the pipeline proves them.** No
  agent declares a generation "correct"; it declares the lifecycle reached
  `delivered` and the artifact hash/size were recorded. Content quality is
  a human judgement.
- Any change touching **account safety** (NotebookLM automation pacing,
  login, selectors, session refresh) is treated as **at least High** risk
  and requires surfacing the ban exposure explicitly — inspection alone is
  not sufficient.
- Never tune one path (e.g. faster generation, fewer waits) without
  stating the trade-off against detection / rate-limit risk.
- Output that conflicts with a stored job invariant (wrong channel, wrong
  mode, duplicate) is a **conflict to surface**, not a value to silently
  accept.

---

## 4. Security risk (CWE-aware)

Risk that a change introduces an exploitable weakness. Mirrors
`AGENT_CONDUCT.md` §1.4 and the project secret rules; this section adds
the **severity gate** for when a security review is mandatory.

### 4.1 Catalog

| Hazard (CWE) | Default tier | Control |
| --- | --- | --- |
| Secret in plain text / as a real `getenv` default (CWE-798) | **Critical** | Secrets only via `.env`. Use `_required(name)` in `worker/app/config.py` / `bot/app/config.py`, never a real default. |
| `storageState.json` leaked (logged, copied out of `data/session/`, committed, or bundled into an artifact/debug dump) (CWE-522) | **Critical** | Top-tier credential, Google bearer-equivalent. chmod 600, worker-UID owned, git-ignored. Never serialise it anywhere but `data/session/`. |
| Discord Ed25519 signature verification weakened or bypassed (CWE-347) | **Critical** | The bot verifies every interaction with `DISCORD_PUBLIC_KEY` (pynacl). Never short-circuit, move into n8n, or accept unverified requests. |
| SQL built by f-string / concatenation, in `worker/` or an n8n Postgres node (CWE-89) | **Critical** | Parameterised queries only (psycopg params / n8n `queryReplacement`). No exceptions. |
| IDOR — job or channel resolved by a user-supplied id without ownership scope (CWE-639) | **Critical** | Delivery and job lookups are scoped to the stored job owner. Flag any lookup that trusts an inbound id. |
| SSRF / open relay via `WEBHOOK_URL` / `N8N_WEBHOOK_URL` pointed at an attacker-controlled host (CWE-918) | **High** | Webhook targets are internal service names; never make them user-controllable. |
| `WORKER_SHARED_TOKEN` missing, logged, or not validated on the bot→n8n / worker↔n8n hop (CWE-306) | **High** | Header auth required on internal endpoints. Validate at the boundary; never log the token. |
| n8n Code-node `$env` exposure widened beyond need (`N8N_ENV_VARS`) | **High** | Only whitelist the variables a node actually reads. Adding a secret to the list to "make it work" is an escalation. |
| Redis reachable without `requirepass` | **High** | `REDIS_PASSWORD` is mandatory (compose enforces `:?`). Never connect without it. |
| Broad exception swallowing that hides a security or session failure | **Medium** | Specify exception types; never bare `except`. |

### 4.2 Severity gate (when a `security-reviewer` is mandatory)

A dedicated `security-reviewer` pass is **required**, not optional, when
a change touches any of:
- Discord interaction verification, the bot's request authenticity, or
  `WORKER_SHARED_TOKEN` handling.
- `storageState.json`, the Google session, or `worker/app/session.py`.
- SQL construction or query parameters (`worker/` or n8n nodes).
- Anything that resolves a job or a delivery channel by an inbound id.
- Secret handling, `.env`, `config.py`, the `N8N_ENV_VARS` whitelist, or
  exported n8n workflow JSON.

Security-relevant paths are **never** simplified in a cleanup pass
(`MAIN_AGENT_CONDUCT.md` §4.5); they are flagged for dedicated review.

---

## 5. Confirmation & escalation protocol

When an action lands at **High** or **Critical**:

1. **STOP.** Do not act and do not dispatch a subagent that would act.
2. State, in one block to the user:
   - the **action** you intend (file, command, scope),
   - the **hazard** and which catalog row it maps to,
   - the **tier** and why,
   - the **mitigation** you propose.
3. Wait for an **explicit** override that names the action, the file,
   and the scope. Implicit consent or "looks fine" is not an override.
4. For **Critical** actions, pair execution with an independent
   verification lane (`omc ask codex` cross-validation, or a
   `verifier`/`security-reviewer` pass distinct from the author).
5. If the user declines, record the decision and choose the next
   safest path — never the bypass.

Escalation never weakens a gate: if pylint 10/10, ruff clean, or
pytest-green cannot be met legitimately, surface the obstacle with the
underlying error (`AGENT_CONDUCT.md` §3). Do not suppress or work around
it.

---

## 6. Recording risk decisions

For any **Medium+** action that proceeds, capture a one-line record so
the decision is auditable:

```
RISK: <hazard> | tier=<Low|Medium|High|Critical> | mitigation=<...> | approved_by=<user|self(Low only)>
```

- **Low** — self-noted in the reasoning trace; no user sign-off needed.
- **Medium** — mitigation stated and logged before proceeding.
- **High / Critical** — user approval string captured verbatim.

Persisted decisions that should outlive the session belong in OMC
project memory or the notepad, not scattered in commit messages.

---

## 7. Acknowledgement protocol

Before the first risk-bearing action of a session, confirm in your own
reasoning trace that you have:

1. Read `CLAUDE.md`, `AGENT_CONDUCT.md`, and (if main agent)
   `MAIN_AGENT_CONDUCT.md`.
2. Classified the intended action against §1's tier matrix.
3. Confirmed the action does not require violating any conduct rule.

If the action is High or Critical, return to the user with the §5 block
before doing any work.
