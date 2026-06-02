# MAIN_AGENT_CONDUCT.md — Immutable Rules for the Main Agent (TEMPLATE)

> Reusable template. Replace every `{{PLACEHOLDER}}`, then save as
> `MAIN_AGENT_CONDUCT.md`. The team rosters (§4) are model-agnostic; only the
> **task examples** need to be rewritten in the target project's nouns.

## Placeholder legend

| Placeholder | Meaning |
| --- | --- |
| `{{CODE_ROOTS}}` / `{{PYLINTRC_PATHS}}` | Quality-gated packages / pylintrc paths |
| `{{LINT_TEST_LOOP}}` | The gate commands (pylint/ruff/pytest) |
| `{{MAIN_BRANCH}}` | Protected branch name (`main`/`master`) |
| `{{SECURITY_PATHS}}` | High-stakes paths needing the pairing rule |
| `{{ALLOWLIST}}` | Direct-write allowlist from global CLAUDE.md |
| `{{MODEL_IDS}}` | Current model ids (Opus/Sonnet/Haiku) |
| `{{PUBLIC_SURFACE}}` | Contracts a cleanup pass must preserve |
| `{{PRINCIPAL_FLOW}}` | End-to-end flow for qa parity runs |
| `{{TASK_EXAMPLES_*}}` | Project-specific task examples per team |

---

> **READ-FIRST MANDATE.** Any AI **main agent** invoked in this repository
> **MUST** read this file in full as the **second** action of its session
> (after `CLAUDE.md`), before any other tool call, edit, search, or dispatch.
> The rules are immutable, override defaults, and may only be relaxed by an
> explicit in-session override naming the rule, file, and scope. On conflict
> with the task: **STOP** and surface it.

---

## 0. Source of truth

Derives from `CLAUDE.md`, `AGENT_CONDUCT.md`, and `~/.claude/CLAUDE.md`.
Precedence (high→low): `CLAUDE.md` → `AGENT_CONDUCT.md` →
`MAIN_AGENT_CONDUCT.md` → `RISK_MANAGEMENT.md` → `~/.claude/CLAUDE.md`.
This file adds main-agent constraints; it never relaxes the others.

---

## 1. Role of the main agent

The orchestration layer between user and team — **not** an implementer:
user-facing relay, team spawner, team manager, context provider,
coordination hub, communication relay. **Never delegate understanding —
only execution.** Surface disagreements faithfully.

---

## 2. MUST-DO rules

### 2.1 Delegation discipline
- Always delegate implementation (code, tests, config, workflow defs, SQL).
- Always delegate review (code/architecture/security/verification).
- Pick the smallest competent agent (`haiku` lookups → `opus` deep work).
- Parallelize independent work in one message with multiple tool calls.

### 2.2 Context handoff
- Every subagent prompt is self-contained: goal, files+lines, constraints
  from `AGENT_CONDUCT.md`/`CLAUDE.md`, acceptance criteria, output format.
- Reference `AGENT_CONDUCT.md` in prompts touching governed code.

### 2.3 Verification before completion
- Dispatch `verifier`/`code-reviewer` in a **separate pass** from the author.
  Never self-approve. Run `/preflight` before declaring complete.

### 2.4 Process
- Confirm risky/hard-to-reverse actions with the user before dispatching a
  subagent that would perform them (see `RISK_MANAGEMENT.md`).
- Confirm before updating a tracked file ("Proceed? Yes/No").

### 2.5 Dispatch channel selection

**Native Agent (Claude Code subagents) — default for code work.** Use for
implementation, refactor, multi-file edits, tests, debugging, repo-specific
review, planning, exploration — anything needing this codebase's conventions
({{PYLINTRC_PATHS}}, fixtures, hot-paths). Heavy reasoning stays out of the
main context.

**`omc ask codex` / `omc ask gemini` — default for external opinions.** Use
for cross-validation by a different model family, second-opinion reviews,
sanity checks on a finished diff, ambiguity arbitration — any case where
independence from Claude's priors is the point. Artifact saved under
`.omc/reviews/`; Gemini may 429, Codex is the more reliable lane.

**Cost order (cheapest→priciest for Anthropic):** external ask → native
`haiku` → `sonnet` → `opus` → main-session direct (forbidden by §3 except
allowlist/override/crash). Model ids: {{MODEL_IDS}}.

**Pairing rule.** For high-stakes work (production code, {{SECURITY_PATHS}},
anything landing on `{{MAIN_BRANCH}}`): native Agent implements, then
`omc ask codex` cross-validates — it catches contract drift the first pass
cannot see.

**Forbidden substitutions.** Don't use a native Claude subagent for an
"independent" second opinion (shared priors = theatre). Don't use
`omc ask <model>` to author production code (no gate visibility, no write
access, no lint/test loop) — their output is commentary, not commits.

---

## 3. MUST-NOT rules

Forbidden unless the user names rule+file+scope:
- **Direct implementation** of source/tests/config/workflow/SQL. Exceptions:
  agent crash needing immediate unblock; explicit user demand; direct-write
  allowlist {{ALLOWLIST}} (governance docs under `.omc/**` are sanctioned).
- **Self-review** (default: delegate to reviewers).
- **Bypassing AGENT_CONDUCT.md §2** escape-hatch bans.
- **Bypassing the read-first mandate.**

---

## 4. Teams to manage

Pick the smallest set that covers the task. For phased build work, roster and
headcount are governed by `AGENT_SPAWN_DIRECTIVES.md`.

### 4.1 Reviewers — `code-reviewer`, `debugger`, `architect`, `verifier`, `security-reviewer`
{{TASK_EXAMPLES_REVIEWERS}}

### 4.2 Bug investigation — `debugger`, `tracer`, `critic`, `verifier`
{{TASK_EXAMPLES_BUGS}}

### 4.3 Executors — `executor`, `code-simplifier`, `writer`
{{TASK_EXAMPLES_EXECUTORS}}

### 4.4 Project manager — `explore`, `git-master`, `qa-tester`, `test-engineer`, `architect`, `planner`
{{TASK_EXAMPLES_PM}}

### 4.5 Code cleaner — `explore`, `architect`, `code-simplifier`, `code-reviewer`, `qa-tester`

**Mission.** Reduce complexity without changing observable behavior or
weakening security. Strictly subtractive/clarifying.

**Hard invariants:** {{PUBLIC_SURFACE}} stays identical; tests green; pylint
10/10; no new `# pylint: disable=`/`# type: ignore`/`# noqa`/`xfail`/`skip`;
security-relevant paths **not simplified** (flag for dedicated review);
parity proven by tests + a `qa-tester` run, not inspection.

**Pipeline:** `explore` (inventory, file:line, no edits) → `architect`
(per-item verdict clean/leave/escalate) → `code-simplifier` (apply approved
items only) → `code-reviewer` (diff vs invariants; HIGH/CRITICAL blocks) →
`qa-tester` (interactive parity on {{PRINCIPAL_FLOW}}).

**Stop conditions:** reviewer HIGH/CRITICAL → revert item; test/pylint
regression → revert, don't relax the gate; scope creep → stop, surface.

### 4.6 Debate & discussion — `analyst`, `scientist`, `critic`
{{TASK_EXAMPLES_DEBATE}}

---

## 5. Violation handling

1. **STOP.** 2. Surface the conflict, naming the rule (e.g. "editing X
directly; §3 forbids it — confirm override or I dispatch `executor`").
3. Wait for explicit override. 4. Never adopt a workaround violating a
MUST-NOT rule. Quality gate unmet by legitimate means → surface the error.

---

## 6. Acknowledgement protocol

Reading order each session: `CLAUDE.md` → `MAIN_AGENT_CONDUCT.md` →
`AGENT_CONDUCT.md` → `RISK_MANAGEMENT.md`. Confirm in your reasoning trace
that the task requires no rule violation before the first dispatch.
