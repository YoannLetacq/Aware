# RISK_MANAGEMENT.md — Risk Framework for AI Agents (TEMPLATE)

> Reusable template. Replace every `{{PLACEHOLDER}}`, then save as
> `RISK_MANAGEMENT.md`. §1 (the tier model) and §5–7 (escalation, recording,
> acknowledgement) are project-agnostic — keep them verbatim. §2–4 (the risk
> **catalogs**) must be rewritten for the target project's hazards.

## Placeholder legend

| Placeholder | Meaning |
| --- | --- |
| `{{SEVERE_IMPACT_EXAMPLES}}` | What "Severe" means for this project |
| `{{DESTRUCTIVE_TARGETS}}` | Irreversible local stores (DB schema, volumes, sessions) |
| `{{PRODUCT_RISK_ROWS}}` | The product/correctness hazard table |
| `{{PRODUCT_UNIQUE_RISK}}` | The single most project-specific product risk |
| `{{SECURITY_RISK_ROWS}}` | The CWE hazard table |
| `{{SECURITY_GATE_TRIGGERS}}` | Changes that mandate a `security-reviewer` |
| `{{CONFIG_HELPER}}` / `{{TOP_TIER_CREDENTIAL}}` | Required-env helper / bearer-equiv secret |

---

> **CONSULT-BEFORE-ACTING MANDATE.** Any AI agent operating here **MUST**
> consult this file before any action carrying operational, product, or
> security risk. Read `CLAUDE.md`, `AGENT_CONDUCT.md`,
> `MAIN_AGENT_CONDUCT.md` first; this file tells you **how to weigh** the
> risk. It is binding, it **adds** an obligation (never relaxes a rule), and
> **High/Critical → STOP** and get explicit confirmation. "Probably fine" is
> not a risk assessment; naming hazard+likelihood+impact+mitigation is.

---

## 0. Source of truth & precedence

Derives from `CLAUDE.md`, `AGENT_CONDUCT.md`, `MAIN_AGENT_CONDUCT.md`,
`~/.claude/CLAUDE.md`. Precedence (high→low): `CLAUDE.md` →
`AGENT_CONDUCT.md` → `MAIN_AGENT_CONDUCT.md` → `RISK_MANAGEMENT.md` →
`~/.claude/CLAUDE.md`. Where a conduct rule forbids an action, that ban
wins; this file only adds the duty to **classify and escalate**.

---

## 1. Risk classification model

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
| **Severe** | {{SEVERE_IMPACT_EXAMPLES}} |

### 1.3 Tier matrix
|              | Minor   | Serious | Severe   |
| ------------ | ------- | ------- | -------- |
| **Rare**     | Low     | Low     | High     |
| **Possible** | Low     | Medium  | Critical |
| **Likely**   | Medium  | High    | Critical |

### 1.4 Tier → required behavior
- **Low** — proceed; note in reasoning trace.
- **Medium** — proceed only with a stated, logged mitigation.
- **High** — **STOP**; surface hazard/tier/mitigation; get confirmation.
- **Critical** — **STOP**; explicit override naming action+file+scope **and**
  a paired independent verification.

---

## 2. Operational risk (agent actions)

| Hazard | Default tier | Control |
| --- | --- | --- |
| `--force` push to main branch | **Critical** | Forbidden without override; confirm even with lease. |
| `git reset --hard`, `clean -f`, `checkout .`, `restore .`, `branch -D` | **High** | Forbidden without instruction; prefer stash/new branch. |
| Deletion of tracked content | **High** | Inspect first; if it contradicts its description or you didn't create it, surface. |
| Deleting/overwriting {{DESTRUCTIVE_TARGETS}} | **Critical** | Irreversible; confirm + require a backup first. |
| Destructive schema migration | **Critical** | Confirm; require a proven rollback path. |
| Commit that may carry a secret | **Critical** | Never commit; scan staged diff first. |
| `--no-verify` / `--no-gpg-sign` / `-i` flags | **High** | Forbidden (`AGENT_CONDUCT.md` §2). |
| Updating a tracked file | **Medium** | Confirm "Proceed? Yes/No" before writing. |
| Main agent implementing directly (outside allowlist) | **High** | Delegate per `MAIN_AGENT_CONDUCT.md` §3. |

Controls: prefer the reversible path; state the **blast radius** before any
irreversible action; confirm High/Critical with the user **before**
dispatching a subagent that would perform them.

---

## 3. Product risk (correctness & external-service safety)

The risks unique to this project — what does "wrong output" or "abused
upstream" mean here, and what protects against it.

**Most project-specific risk:** {{PRODUCT_UNIQUE_RISK}}

| Hazard | Default tier | Control |
| --- | --- | --- |
{{PRODUCT_RISK_ROWS}}

Controls: outputs are advisory until the pipeline proves them (no agent
declares correctness — that is a human sign-off); changes touching the
unique risk above are **at least High**; never tune one path without stating
the trade-off; conflicts with a stored invariant are surfaced, not absorbed.

---

## 4. Security risk (CWE-aware)

| Hazard (CWE) | Default tier | Control |
| --- | --- | --- |
| Secret in plain text / real `getenv` default (CWE-798) | **Critical** | `.env` only; use `{{CONFIG_HELPER}}`. |
| `{{TOP_TIER_CREDENTIAL}}` leaked (CWE-522) | **Critical** | Bearer-equivalent; never logged/copied/committed. |
| SQL by f-string/concatenation (CWE-89) | **Critical** | Parameterised queries only. |
| IDOR — resource by inbound id without ownership scope (CWE-639) | **Critical** | Scope every access to its owner. |
{{SECURITY_RISK_ROWS}}
| Broad exception swallowing hiding a failure | **Medium** | Specify exception types; no bare `except`. |

### 4.2 Severity gate (when a `security-reviewer` is mandatory)
Required, not optional, when a change touches: {{SECURITY_GATE_TRIGGERS}}.
Security-relevant paths are **never** simplified in a cleanup pass; flag for
dedicated review.

---

## 5. Confirmation & escalation protocol

On **High/Critical**: 1. **STOP** (don't act, don't dispatch an actor).
2. State action / hazard+catalog-row / tier+why / mitigation in one block.
3. Wait for an explicit override naming action+file+scope. 4. For Critical,
pair with an independent verification lane. 5. If declined, record it and
take the next safest path — never the bypass. Escalation never weakens a
gate; surface the underlying error instead.

---

## 6. Recording risk decisions

For any **Medium+** action that proceeds:
```
RISK: <hazard> | tier=<Low|Medium|High|Critical> | mitigation=<...> | approved_by=<user|self(Low only)>
```
Low: self-noted. Medium: mitigation logged. High/Critical: user approval
captured verbatim. Durable decisions → OMC project memory / notepad.

---

## 7. Acknowledgement protocol

Before the first risk-bearing action, confirm in your reasoning trace that
you have (1) read the conduct files, (2) classified the action against §1,
(3) confirmed it violates no conduct rule. High/Critical → return with the
§5 block first.
