# Adversarial Critique — n8n Podcast Pipeline

> Source: Critic agent (task `aadd7421963787785`). Persisted by main
> agent under MAIN_AGENT_CONDUCT.md §3 direct-write allowlist
> (`.omc/**`). File:line citations to veille_auto unverified.

## VERDICT: REJECT (conception as currently described)

The proposed design has at least three structural flaws that are not addressed in the brief: (1) long-running browser-automation step inside n8n, (2) total dependence on a ToS-violating headless-browser path, (3) Discord 3 s / 15 min interaction limits. Any one of them sinks the MVP. All three together mean the pipeline will appear to work in dev and fail unpredictably in production.

## HIGH severity

### H1. n8n is the wrong orchestrator for a multi-minute browser-automation step
- **Evidence**: NotebookLM Audio/Video generation regularly takes 2–10+ minutes; n8n executions are designed around short HTTP-shaped steps. Long-running nodes block a worker, hold the execution row open in Postgres, and are killed by `EXECUTIONS_TIMEOUT` / container restarts / deploys.
- **Why it matters**: a single user request can monopolise an n8n worker for ~10 min. Two concurrent requests starve the queue. A redeploy mid-generation loses state.
- **Mitigation**: split into two services — n8n stays as the *trigger/dispatcher* and *poster-back*, and a dedicated **background worker** (Python/Node) owns the browser session and the polling loop. Communication via a queue (Redis/RQ, BullMQ, or Postgres `LISTEN/NOTIFY`) with a `job_id`. n8n calls `POST /jobs`, returns immediately, then a webhook from the worker re-enters n8n to post to Discord.

### H2. NotebookLM has no API and an active anti-automation ToS — single point of failure
- **Evidence**: Google's ToS prohibits automated access to consumer products without a documented API. Headless-browser automation against a Google login fights (a) reCAPTCHA/device-fingerprint heuristics, (b) consent flows, (c) UI churn, (d) account suspension risk.
- **Why it matters**: the entire product value hinges on a vendor that can kill access overnight. No SLA, no error contract, no escalation path.
- **Mitigations**:
  - Use a **burner Google Workspace account**, never personal.
  - **Persist cookies/session** (Playwright `storageState`) to avoid re-login on every run; refresh out-of-band.
  - **Fallback TTS path** behind a feature flag (ElevenLabs, Azure Speech, OpenAI TTS) so a vendor outage doesn't zero the product. *(Note: user has not confirmed appetite for fallback — flag as future work, not MVP.)*
  - Document the ToS risk in README.

### H3. Discord interaction timing model is incompatible with the happy path
- **Evidence**: Discord slash-command interactions require an **initial response within 3 seconds**; after `deferReply()` you get **15 minutes** for the follow-up. NotebookLM generation routinely exceeds 15 minutes.
- **Why it matters**: relying on the interaction token to post the result silently breaks past 15 min.
- **Mitigation**: on trigger, immediately `deferReply()` and post an acknowledgement embed with a `job_id` and "I'll ping you when it's done". When the worker finishes, post the artifact as a **new message** in the same channel mentioning the user, **not** via the original interaction token.

### H4. Secret surface: `.env` is insufficient for Google session state
- **Evidence**: real secret surface includes:
  1. Google email + password (or app password)
  2. TOTP seed if 2FA on the account
  3. **Persisted browser session/cookies** (`storageState.json`) — bearer credential equivalent to the password until it expires
  4. Discord bot token
  5. Gemini API key
  6. n8n basic-auth / encryption key
- **Why it matters**: `.env` covers (1), (4), (5), (6) acceptably; (3) is a *file*, not a variable, and bypasses 2FA. Storing it next to `docker-compose.yml` is a footgun.
- **Mitigations**:
  - Mount `storageState.json` from a **dedicated, restricted volume** (`chmod 600`, owned by the worker UID).
  - Do not commit `.env.template` with realistic-looking placeholders.
  - Plan for **session rotation**: cookie storage will expire; design a manual re-auth procedure now.

## MEDIUM severity

### M1. Discord trigger ergonomics
- Slash command for v1 (typed args + enum enforcement). For longer subjects, use a **modal** triggered by the slash command (textarea up to 4000 chars).
- Validation failure modes: empty subject, prompt-injection in subject (`"ignore previous instructions..."`), URLs in subject (SSRF-by-proxy risk via Gemini grounding), unicode/RTL tricks.

### M2. Cost & rate-limit blind spots
- **Gemini**: hard per-user-per-day cap (e.g. 3 podcasts/day/user), global daily ceiling, kill switch env var.
- **NotebookLM**: track generations/day in Postgres; refuse new jobs past threshold; queue overflow with clear Discord message.
- **Discord**: file upload ≤ 25 MB free / 50–500 MB with boosts. MP3s can exceed. Re-encode to target bitrate or host file (S3/MinIO) and post link.

### M3. No idempotency / no resume
- Persist `(discord_interaction_id, user_id, subject_hash, status, artifact_url)` in Postgres. Dedup on `subject_hash` within a TTL window. Retry the Discord post separately from the generation.

### M4. Observability
- A browser-automation pipeline without screenshots-on-failure and HAR captures is undebuggable. On every worker failure: persist `page.screenshot()` + DOM snapshot + last 50 network requests to a debug volume; Discord-DM the operator on repeated failures.

## LOW severity

- **L1. Style enum risk** — if `style` is small enum, fine. Free text → prompt-injection vector. Lock it down.
- **L2. Workflow JSON in git** — verify the n8n export does not include credential ids that leak account structure.
- **L3. Postgres reuse** — keep your tables in a separate schema (`podcast.*`), not `public.*`.

## Gap analysis

- No job/state table — required for H1 + M3.
- No artifact storage decision — local disk fills up; pick S3/MinIO with retention.
- No fallback when NotebookLM down (H2).
- No concurrency limit (Chromium ~500 MB RAM/instance).
- No Google-account-banned plan.
- No moderation filter (copyrighted / defamatory / NSFW).
- No GDPR / retention policy.
- No testing strategy with mock-NotebookLM mode.
- No cold-start session-validation step.
- No CI / lint posture for the worker.

## Ambiguity Risks

- `"upload to NotebookLM via headless browser"` — one notebook per request (recommended A — clean isolation, higher quota) or shared (B — source cross-contamination). Pick A.
- `"retrieve generated podcast/video"` — audio-only MVP halves the failure surface vs video. Re-confirm with user.
- `"subject + mode (+ style)"` — `style` optional? Default? Defaults shape the prompt; product decision, not code decision.

## Design changes that, if NOT made, will sink the project

1. Move the long-running NotebookLM step OUT of n8n into a dedicated background worker. **(H1)**
2. Stop responding via the original Discord interaction token after `deferReply`; post the artifact as a fresh channel message. **(H3)**
3. Treat `storageState.json` as a top-tier secret: restricted volume, `chmod 600`, documented rotation. **(H4)**
4. Add a job/state table in Postgres with idempotency on `(user_id, subject_hash)` and explicit status machine. **(M3, H1)**
5. Cap per-user and global daily generations with a hard kill switch env var before first deploy. **(M2)**
6. Decide artifact storage now (ephemeral vs S3/MinIO) and Discord file-size strategy. **(M2)**
7. Add failure-mode observability (screenshot + DOM + network log on every worker failure) from day one. **(M4)**
8. Use a burner Google Workspace account, never personal identity. **(H2, H4)**
9. Input filter / moderation step before Gemini for prompt injection, URLs, abuse. **(M1)**
10. Fallback TTS *deferred* pending user confirmation (not MVP). **(H2)**

Without (1), (2), (3), (4), the project will produce a demo that works once and breaks within two weeks of real use.

## Open Questions (unscored)

- Audio-only for v1, or audio + video from the start? Audio-only halves risk.
- Single operator or public Discord guild? Changes rate limits, moderation, secret handling.
- n8n as a hard constraint? If yes, accept the external-worker split as non-negotiable.
- Expected volume (podcasts/day)? Below ~3/day, manual NotebookLM is cheaper than building this.
