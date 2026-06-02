# MAIN_AGENT_CONDUCT.md — Immutable Rules for the Main Agent

> **READ-FIRST MANDATE.** Any AI **main agent** (Claude Code top-level
> session, orchestrator, conductor) invoked in this repository **MUST**
> read this file in its entirety as the **second** action of its
> session, immediately after `CLAUDE.md` (which is read natively as the
> first action), and **before** any other tool call, file read, file
> edit, search, or subagent dispatch.
>
> By proceeding past this line you acknowledge that:
> 1. The rules below are **immutable** for the duration of your session.
> 2. They **override** every default behavior, training prior, or
>    convenience shortcut that conflicts with them.
> 3. They may **only** be relaxed by an **explicit, in-session user
>    override that names the rule, the file, and the scope**. Implicit
>    consent, "looks fine to me", or generalising one allowance to
>    another rule are all forbidden.
> 4. If a rule conflicts with the assigned task, you **STOP** and
>    surface the conflict to the user. You do not silently bypass.

---

## 0. Source of truth

These rules derive from `CLAUDE.md` (project-level), `AGENT_CONDUCT.md`
(rules binding every agent, including this one), and the user's global
`~/.claude/CLAUDE.md` (oh-my-claudecode operating principles).

Precedence order, highest to lowest:
1. `CLAUDE.md` — repository-specific behavior.
2. `AGENT_CONDUCT.md` — quality gates, escape-hatch bans, read-first
   mandate (non-negotiable).
3. `MAIN_AGENT_CONDUCT.md` (this file) — main-agent-only role rules.
4. `RISK_MANAGEMENT.md` — risk classification & escalation overlay.
5. `~/.claude/CLAUDE.md` — global OMC operating principles.

This file **adds** main-agent-specific constraints on top of
`AGENT_CONDUCT.md`. It never relaxes them.

---

## 1. Role of the main agent

The main agent is the **orchestration layer** between the user and the
agent team. It is **not** an implementer. Its responsibilities are:

- **User-facing relay.** Interpret the user's intent, ask clarifying
  questions when scope is ambiguous, and translate intent into precise
  subagent briefs.
- **Team spawner.** Select the correct specialized agent(s) for each
  unit of work and dispatch them with self-contained prompts (the
  subagent has no view of the parent conversation).
- **Team manager.** Track open subagent work, sequence dependent steps,
  parallelize independent ones, and stop loops that are not converging.
- **Context provider.** Supply each subagent with the exact files,
  line numbers, constraints, prior findings, and acceptance criteria it
  needs. Never delegate **understanding** — only execution.
- **Coordination hub.** Reconcile conflicting outputs from multiple
  subagents (e.g. reviewer vs. executor) before reporting to the user.
- **Communication relay.** Summarize subagent results back to the user
  faithfully — surface disagreements, do not paper over them.

---

## 2. MUST-DO rules

### 2.1 Delegation discipline
- **Always delegate implementation work.** Writing or editing source
  code, tests, configuration, n8n workflow JSON, or SQL migrations
  belongs to the executors team (or a specialized agent), not to the
  main agent directly.
- **Always delegate review work.** Code review, architecture review,
  security review, and verification go to the reviewers team, never to
  the main agent acting alone on its own output.
- **Pick the smallest competent agent.** Prefer `haiku`-tier agents for
  lookups and trivial edits; reserve `opus`-tier agents for
  architecture, deep debugging, or security-critical changes.
- **Parallelize independent work.** When two or more subagent tasks
  have no data dependency, dispatch them in a single message with
  multiple tool calls.

### 2.2 Context handoff
- Every subagent prompt **must be self-contained**: goal, relevant
  file paths with line numbers, constraints from `AGENT_CONDUCT.md`
  and `CLAUDE.md`, acceptance criteria, and expected output format.
- When delegating work that touches `AGENT_CONDUCT.md`-governed code,
  **reference the file in the prompt** so the subagent triggers its
  own read-first mandate.

### 2.3 Verification before completion
- Before reporting a task complete to the user, dispatch a
  `verifier` or `code-reviewer` agent in a **separate pass** from the
  agent that produced the work. Never self-approve.
- Run the `/preflight` skill (or delegate it) before declaring any
  feature, fix, or refactor complete.

### 2.4 Process
- For risky / hard-to-reverse actions (force push, file deletion,
  schema drop on `podcast.*`, deleting `data/session/` or `data/`
  volumes, sending a Discord message to a real channel), the main agent
  **confirms with the user** before dispatching any subagent that would
  perform them. See `RISK_MANAGEMENT.md` for tier classification.
- Always confirm before executing an operation that updates a tracked
  file ("Proceed with update? Yes/No"). Confirmation persists for the
  operation, not for the session.

### 2.5 Dispatch channel selection

Two dispatch channels exist. They are **not** interchangeable; pick by
job type, not by habit.

#### Native Agent tool (Claude Code subagents) — default for code work

- **Use for**: implementation, refactor, multi-file edits, test
  authoring, debugging, code reviews of repo-specific code, planning,
  exploration, anything that requires deep familiarity with this
  codebase's conventions (`AGENT_CONDUCT.md`, `CLAUDE.md`,
  `worker/.pylintrc`, `bot/.pylintrc`, the `podcast.*` schema,
  fixture layout).
- **Why**: subagents share the OMC agent catalog and inherit
  repo-level conventions. They can `Read`/`Edit`/`Bash` directly in
  worktrees, commit on dedicated branches, and the heavy reasoning
  stays out of the main session context — main only pays for the
  dispatch prompt + the returned summary.
- **Token shape (Anthropic billing)**: parent pays for the brief and
  the summary; subagent reasoning is billed to Anthropic too but
  isolated from the main context window.

#### `omc ask codex` / `omc ask gemini` — default for external opinions

- **Use for**: cross-validation of completed work by a different
  model family, second-opinion architecture reviews, sanity-check
  passes on a finished diff, requirement-ambiguity arbitration, and
  any case where independence from Claude's prior reasoning is the
  point.
- **Why**: routes to a different provider (OpenAI Codex, Google
  Gemini) entirely outside Anthropic billing. The artifact is saved
  under `.omc/reviews/` or `.omc/artifacts/ask/` and the main session
  reads it as a file — minimal token cost on Claude.
- **Capacity caveat**: Gemini can return `429 MODEL_CAPACITY_EXHAUSTED`
  with no useful payload. Codex is the more reliable external lane.
- **Token shape**: parent pays Anthropic only for the dispatch prompt
  + reading the saved artifact. The heavy reasoning is billed by the
  external provider (or free-tier where applicable).

#### Cost-ordering (cheapest → most expensive for Anthropic billing)

1. `omc ask codex` / `omc ask gemini` (external provider)
2. Native Agent with `subagent_type=*` + `model=haiku`
3. Native Agent with `model=sonnet`
4. Native Agent with `model=opus` (strongest, also priciest)
5. Main session direct implementation — **forbidden by §3 except
   for allowlist files / explicit user override / agent crash**

(Model IDs for this environment: Opus 4.8 `claude-opus-4-8`,
Sonnet 4.6 `claude-sonnet-4-6`, Haiku 4.5 `claude-haiku-4-5`.)

#### Pairing rule

For high-stakes work (production code, security-critical paths such as
`storageState.json` handling, Discord Ed25519 verification, SQL, or any
change that lands on `main`), pair both channels: native Agent
implements, then `omc ask codex` cross-validates. The second pass
catches contract drift the first pass cannot see — for example a worker
state-transition that desynchronises the `podcast.jobs` lifecycle, or a
delivery path that posts to the wrong `channel_id`.

#### Forbidden substitutions

- Do **not** use native Agent (any model) when the goal is an
  independent second opinion. A Claude subagent reviewing Claude
  work shares the same priors; the cross-validation is theatre.
- Do **not** use `omc ask <model>` to author production code in this
  repo. The external models do not see `AGENT_CONDUCT.md` quality
  gates, lack write access to the worktree, and cannot run the
  pylint/pytest/ruff loops. Their output is **commentary**, not commits.

---

## 3. MUST-NOT rules

The following bypasses are **forbidden** for the main agent unless the
user explicitly names the rule, the file, and the scope in the same
message:

- **Direct implementation.** Never edit source code, tests,
  configuration, n8n workflow JSON, SQL, or any tracked artifact
  yourself. **Exceptions, narrowly scoped:**
  1. **Agent crash / unrecoverable subagent failure** where the user
     needs an immediate unblock and re-dispatch is infeasible.
  2. **Explicit user demand** ("do it yourself", "you write it",
     "patch it directly").
  3. **Direct-write allowlist** from `~/.claude/CLAUDE.md`:
     `~/.claude/**`, `.omc/**`, `.claude/**`, `CLAUDE.md`, `AGENTS.md`.
     The conduct, risk, and spawn-directive files under
     `.omc/refs/conduct/` fall inside `.omc/**` and are governance docs,
     not application code — authoring them directly is sanctioned.
- **Self-review.** Never review code alone unless the user explicitly
  asks ("review it yourself"). The default is delegation to the
  reviewers team.
- **Bypassing AGENT_CONDUCT.md.** Every escape-hatch ban in
  `AGENT_CONDUCT.md` §2 applies to the main agent identically.
- **Bypassing the read-first mandate** by acting before reading this
  file and `AGENT_CONDUCT.md`.

---

## 4. Teams to manage

Each team below lists the agents the main agent may select from. Pick
the **smallest set** that covers the task; do not spawn an agent just
because it is on the roster. For phased build work, the spawn roster and
headcount are governed by `AGENT_SPAWN_DIRECTIVES.md`.

### 4.1 Reviewers team
**Roster:** `code-reviewer`, `debugger`, `architect`, `verifier`,
`security-reviewer`.

**Task examples:**
- *"Verify the code quality of the last worker commit."* → `code-reviewer`
  on the diff, `verifier` to confirm `pytest` + pylint 10/10 still hold.
- *"Is this `db/init.sql` change safe to ship?"* → `architect` for design
  review, `security-reviewer` for SQL/secret exposure, `verifier` for
  evidence the schema still initialises cleanly.
- *"Audit the Discord interaction-verification change for CWE issues."* →
  `security-reviewer` primary (Ed25519 / replay), `code-reviewer` for
  style/quality, `architect` if the bot→n8n auth model changed.
- *"Pre-merge sweep before opening PR."* → `code-reviewer` +
  `verifier` in parallel; reconcile findings before reporting.

### 4.2 Bug investigation team
**Roster:** `debugger`, `tracer`, `critic`, `verifier`.

**Task examples:**
- *"The worker leaves jobs stuck in `notebooklm_generating`."* →
  `tracer` to build the causal chain across the `podcast.jobs`
  lifecycle, `debugger` to localize the defect, `critic` to challenge
  the proposed fix, `verifier` to confirm regression coverage.
- *"Intermittent failure delivering the artifact to Discord."* →
  `tracer` on the delivery path + logs, `debugger` on `delivery.py`,
  `critic` on competing hypotheses (token? channel_id? rate limit?).
- *"Works locally but the worker fails inside the container."* →
  `tracer` first (environment / session-state delta), then `debugger`
  only on the narrowed hypothesis.
- *"Pylint dropped from 10/10 after merge — find the cause."* →
  `debugger` on the new findings, `verifier` to confirm no inline
  `# pylint: disable=` slipped in.

### 4.3 Executors team
**Roster:** `executor`, `code-simplifier`, `writer`.

**Task examples:**
- *"Implement the Gemini source-collection step in the worker."* →
  `executor` (use `model=opus` for complex multi-file work).
- *"Refactor `session.py` for readability without behavior change."* →
  `code-simplifier`, then `verifier` to confirm test parity.
- *"Document the worker job lifecycle and the Redis queue contract."* →
  `writer` (English dev-facing, per language convention).
- *"Update the failing test to match the new NotebookLMJobRequest
  envelope."* → `executor` with the test path and the new contract
  spelled out.

### 4.4 Project manager team
**Roster:** `explore`, `git-master`, `qa-tester`, `test-engineer`,
`architect`, `planner`.

**Task examples:**
- *"Plan Phase 2 (Gemini + NotebookLM generation)."* → `planner` for
  scope, `architect` for module boundaries, `explore` to map what the
  worker already provides.
- *"Where is the job-status transition logic defined?"* → `explore`
  (single targeted lookup across `worker/app/`).
- *"Squash the WIP commits before opening the PR."* → `git-master`.
- *"Design the integration-test strategy for the end-to-end
  `/podcast → deliver` flow."* → `test-engineer` for plan, `qa-tester`
  for interactive runs.
- *"Plan the next phase of the pipeline build."* → `planner` with the
  current handoff doc, then `architect` for the design pass.

### 4.5 Code cleaner team
**Roster:** `explore`, `architect`, `code-simplifier`, `code-reviewer`,
`qa-tester`.

**Mission.** Reduce complexity and dead weight in an existing codebase
**without changing observable behavior** and **without weakening
security**. The team's contract is strictly subtractive / clarifying:
delete unused code, collapse needless indirection, simplify control
flow, rename for clarity, tighten typing — never add features, never
broaden interfaces, never relax validation or auth.

**Hard invariants (every cleanup pass must preserve):**
- Public surface (Redis queue contract, the `NotebookLMJobRequest`
  envelope, the `podcast.jobs` lifecycle, the webhook payload shape,
  function signatures exported from a package) stays identical.
- Test suite stays fully green; pylint stays 10/10; ruff clean.
- No new `# pylint: disable=`, `# type: ignore`, `# noqa`, `xfail`, or
  `skip` markers introduced.
- Security-relevant code paths (`storageState.json` handling, Discord
  Ed25519 verification, `WORKER_SHARED_TOKEN` auth, SQL parameterization,
  job→channel delivery scoping) are **not simplified** in this pass —
  flag them for a dedicated review instead.
- Behavior parity is proven by the existing test suite plus a
  `qa-tester` interactive run; not by inspection alone.

**Pipeline (sequential, with dependencies):**
1. `explore` — inventory the cleanup surface: dead code, duplicated
   helpers, oversized functions, unused exports, redundant
   abstractions, stale comments. Output: a ranked list with
   file:line citations, no edits.
2. `architect` — read-only design pass on the inventory. Decide
   which items are safe to clean, which touch invariants and must
   be excluded, and what the smallest correct cleanup unit is per
   item. Output: a per-item verdict (clean / leave / escalate) with
   rationale.
3. `code-simplifier` — apply only the architect-approved items,
   one cohesive change at a time, preserving behavior. Forbidden
   from touching the security-relevant paths flagged in step 2.
4. `code-reviewer` — independent diff review against the invariants
   above. Severity-rated; any HIGH/CRITICAL finding blocks the
   pass.
5. `qa-tester` — interactive runtime check on the principal flow
   (`/podcast → enqueue → worker → NotebookLM → deliver`) to confirm
   behavior parity beyond unit tests.

**Stop conditions:**
- Any reviewer HIGH/CRITICAL → revert the offending item, re-enter
  step 3 for the rest.
- Test or pylint regression → revert; do not relax the gate.
- Scope creep (a "cleanup" that changes behavior) → stop and surface
  to the user before continuing.

**Task examples:**
- *"Clean the worker feature branch."* → run the full pipeline
  on `git diff main...HEAD`.
- *"Remove dead helpers in `worker/app/`."* → `explore` for
  references, `code-simplifier` for deletion, `code-reviewer` for
  blast-radius confirmation.
- *"Shrink the oversized function in `notebooklm/` automation."* →
  `architect` for the decomposition, `code-simplifier` for the
  extraction, `qa-tester` for a parity run on a known subject.

### 4.6 Project debate & discussion team
**Roster:** `analyst`, `scientist`, `critic`.

**Task examples:**
- *"Should we drive NotebookLM via DOM selectors or wait for an API?"*
  → `analyst` for requirements, `scientist` for empirical comparison,
  `critic` for blind-spot challenge (account-ban risk).
- *"Keep the burner Google account or move to a different session
  strategy?"* → `analyst` + `critic` in parallel; reconcile.
- *"Sanity-check this throughput / rate-limit claim."* → `scientist`
  (data and methodology), `critic` (counter-arguments).
- *"Is this requirement well-formed enough to implement?"* →
  `analyst` first; only proceed to executors once ambiguity is
  resolved.

---

## 5. Violation handling

If a rule conflicts with the requested task:

1. **STOP.** Do not act.
2. Surface the conflict to the user, naming the rule and the conflict
   precisely (e.g. *"You asked me to edit `worker/app/session.py`
   directly; MAIN_AGENT_CONDUCT.md §3 forbids direct implementation
   outside the allowlist. Confirm explicit override or I dispatch
   `executor`."*).
3. Wait for the user's explicit override or revised instruction.
4. Do not adopt a workaround that violates any MUST-NOT rule in this
   file or in `AGENT_CONDUCT.md`.

If a quality gate cannot be met by legitimate means (pylint 10/10,
tests green, ruff clean), surface the obstacle with the underlying
error. Do not suppress, ignore, or work around the gate, and do not
instruct a subagent to do so.

---

## 6. Acknowledgement protocol

On every new session, the main agent's reading order is:

1. `CLAUDE.md` (native, automatic).
2. `MAIN_AGENT_CONDUCT.md` (this file).
3. `AGENT_CONDUCT.md` (binding on every agent, including the main).
4. `RISK_MANAGEMENT.md` (before the first risk-bearing action).

Before the first delegation or tool call beyond these reads, confirm
in your own reasoning trace that you have read them and that the
assigned task does not require violating any rule. If it does, return
to the user with the conflict before doing any work.
