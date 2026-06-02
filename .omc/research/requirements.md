# Requirements & Ambiguity Dossier — Podcast/Video Pipeline

> Source: Analyst agent (task `aaa5ac2956054a381`). Persisted by main agent
> under MAIN_AGENT_CONDUCT.md §3 direct-write allowlist (`.omc/**`).
> File:line citations to `/home/yoann/veille_auto/**` were not produced
> by the analyst (sandbox-denied); they are marked `[CITATION NEEDED]`
> for the Explore agent re-dispatch to backfill.

## Missing Questions

1. **Discord interaction surface** — Slash command vs mention parsing are not mutually exclusive in the brief ("mention OR slash command"). Which is primary? Slash commands give typed parameters, choice lists, and ephemeral error responses; mentions require NLP parsing of free text. Pick one as MVP path, defer the other. Why it matters: doubles the validation surface and the Discord bot's payload schema.
2. **Who runs the headless browser?** n8n Docker container, a sidecar Playwright service, or a separate worker? n8n's `Execute Command` is fragile for long-running browser sessions. Why it matters: shapes the entire deployment topology.
3. **Output delivery channel** — Where does the finished MP3/MP4 land? Re-posted to the originating Discord channel, uploaded to S3/Drive with a link, or stored locally? Discord upload limit is 25 MB (boost-dependent up to 500 MB); NotebookLM videos can exceed.
4. **Per-user vs shared NotebookLM account** — Single service Google account used by all Discord users, or OAuth-per-user? Single account is simpler but rate-limited and a single point of ToS risk.
5. **Notebook lifecycle** — One NotebookLM notebook per request (created + destroyed) or a long-lived notebook reused? Affects automation complexity and source-pollution risk.
6. **Concurrency model** — If two Discord users trigger simultaneously, do requests queue (single browser session) or parallelize (multiple browser contexts + multiple Google sessions)?
7. **Maximum sources to upload** — NotebookLM caps sources per notebook (50 as of late 2024, subject to change). What does Gemini return — 5? 20? Need explicit cap.
8. **Subject language** — French user-facing UI implies French subjects. Does Gemini receive the French subject verbatim, or is it translated to English first to improve source diversity?
9. **Authentication retry policy** — When Google session expires mid-pipeline, retry behavior is undefined.
10. **Idempotency / deduplication** — If user re-triggers the same subject, do we reuse existing artifacts or regenerate?
11. **Cost ceiling** — Gemini API has per-token cost; NotebookLM generation is free but rate-limited. Any per-user quota?
12. **Observability** — How does the user see progress (a 10-minute pipeline needs status updates) — edited Discord message, follow-up messages, or silence-then-result?

## Undefined Guardrails

1. **Subject length** — "1-2 precise sentences" is subjective. Suggested bound: `min_chars=40, max_chars=400, min_sentences=1, max_sentences=2` (sentence count via simple `[.!?]` split, tolerant). Reject below `min_chars` with a French clarification prompt.
2. **Subject quality** — Vague subjects ("AI", "le climat") produce bad sources. Suggested: a pre-flight Gemini classifier call that returns `{specific: bool, reason: str}`; reject if `specific=false` with the reason surfaced to the user.
3. **NotebookLM video style enumeration** — Hard-code the list in the slash-command Choice array; treat the list as configuration (`config/notebooklm_styles.json`) so it can be updated without code change. **User commitment: user pastes the authoritative preset list before Phase 1 implementation begins.** If a chosen preset has been renamed/removed by NotebookLM, the browser worker must fail-fast with a "preset unavailable" error.
4. **Source count** — Suggested: Gemini prompted to return exactly 8 sources, validated `min=5, max=15`. Below `min`, retry once with a broader prompt; above `max`, truncate by `relevance_score`.
5. **Source type mix** — Suggested: at least one of each of `{academic_paper, youtube_video, news_or_blog}` required; bias prevention.
6. **Pipeline timeout** — Suggested: hard cap 15 minutes end-to-end. Per-stage: Gemini 60 s, source validation 90 s, NotebookLM upload 180 s, NotebookLM generation 600 s.
7. **Retry budget** — Suggested: Gemini call retries=2 (exponential backoff 5 s / 20 s), browser actions retries=1 per logical step, Discord post retries=3.
8. **Secrets** — Suggested guardrail: a pre-commit hook (or CI step) that runs `gitleaks` or equivalent; `env.template` only contains placeholders. `[CITATION NEEDED: veille_auto/env.template pattern]`.

## Scope Risks

1. **NotebookLM "browser automation" rabbit hole** — DOM-selector drift is constant. Prevention: isolate all selectors into one `selectors.ts` file with a `version` constant and a smoke-test script run on schedule; treat selector breakage as a known operational risk, not a code defect.
2. **Both podcast and video modes in MVP** — Video Overview is newer, slower, and more brittle than Audio Overview. Prevention: ship `podcast` mode first behind a feature flag; gate `video` behind a second milestone.
3. **Multi-language sources** — Gemini may return French and English sources mixed; NotebookLM handles both but quality varies. Prevention: explicit `language` parameter in Gemini prompt (default `fr`, allow `mixed`); document as a known limitation in MVP.
4. **Discord embed/UX polish** — Easy to spend days on progress bars, ephemeral replies, error embeds. Prevention: MVP uses plain text replies in three states: `received`, `done`, `error`. Defer embed prettification.
5. **"Curated by Gemini" creep into agentic search** — Tempting to add Tavily, Perplexity, arXiv direct API. Prevention: MVP is Gemini-only; document the source-quality limitation rather than expanding.
6. **n8n complexity creep** — Easy to build 30-node graphs. Prevention: target ≤10 nodes, linear, one HTTP webhook in / one HTTP callback out; complex logic lives in custom code nodes or external services, not in n8n branches.

## Unvalidated Assumptions

1. **NotebookLM has no public API** — True as of 2026-05 per stated brief. Validation: re-check Google's developer changelog before sprint start.
2. **Playwright/Puppeteer can authenticate to Google without triggering the "unusual sign-in" block** — Requires persistent profile + residential IP. Validation: a 24-hour smoke test running every 4 hours from the target Docker host to confirm session survives.
3. **Gemini can produce reliably-formatted JSON** — Modern Gemini (2.0+/2.5) supports `response_mime_type=application/json` and `response_schema`. Validation: 50-call dry run with schema-pinned output measuring parse-success rate ≥ 98 %.
4. **Discord bot can post files up to user's pipeline output size** — Validation: known limit 25 MB free / 50 MB Nitro Basic / 500 MB Nitro. If artifacts exceed, fallback to S3/Drive link.
5. **veille_auto's docker-compose patterns directly transfer** — `[CITATION NEEDED: veille_auto/docker-compose.yml]`.
6. **Single Google account survives sustained automation** — Validation: monitor Google account "Recent security activity" page; if blocks appear, pivot to OAuth-per-user with stored refresh tokens (much more complex).
7. **NotebookLM Audio Overview is consistently in the requested language** — Validation: include explicit "respond in French" instruction in the notebook customization step; spot-check first 5 outputs.

## Acceptance Criteria

### Stage 1 — Discord trigger
- AC1.1: User invokes `/podcast subject:"…" mode:podcast` and receives an ephemeral acknowledgment in French within 2 s.
- AC1.2: User invokes with `mode:video style:Explainer`; if `style` is absent when `mode=video`, the command rejects with French clarification.
- AC1.3: Subject failing length validation produces a French error listing the specific rule violated (`min_chars`, `max_sentences`, etc.).
- AC1.4: A valid payload is POSTed to n8n webhook with schema `{interaction_id, user_id, channel_id, subject, mode, style|null, timestamp, locale}`.

### Stage 2 — Gemini source curation
- AC2.1: n8n forwards subject + mode to Gemini with a system prompt (English, see Gemini Prompt Contract).
- AC2.2: Response parses as JSON conforming to `Sources` schema ≥ 98 % over a 50-call benchmark.
- AC2.3: After validation (liveness, type, dedup) the source list satisfies `5 ≤ len(sources) ≤ 15` else pipeline aborts with logged reason.
- AC2.4: Each source has `url`, `title`, `type ∈ {paper, youtube, article, video_other}`, `relevance_score ∈ [0,1]`, `language ∈ {fr,en,other}`.

### Stage 3 — NotebookLM upload
- AC3.1: Browser worker opens NotebookLM logged in as the service account in < 30 s.
- AC3.2: A new notebook is created with title `"{subject_first_60_chars} — {iso_date}"`.
- AC3.3: All sources are uploaded; upload-success rate per source logged. If < 80 % succeed, pipeline aborts.
- AC3.4: Notebook customization prompt is set in French specifying topic framing.

### Stage 4 — Generation
- AC4.1: For `mode=podcast`, "Generate Audio Overview" is triggered; completion polled with backoff; result downloaded as MP3.
- AC4.2: For `mode=video`, the chosen style preset is selected from the UI; "Generate Video Overview" triggered; result downloaded as MP4.
- AC4.3: Artifact filename matches `{interaction_id}.{mp3|mp4}`.
- AC4.4: Artifact size logged; SHA-256 computed; both persisted to `runs/{interaction_id}/meta.json`.

### Stage 5 — Delivery
- AC5.1: Artifact ≤ Discord upload limit → posted as attachment to originating channel with a French caption (subject + duration).
- AC5.2: Artifact > limit → uploaded to configured object storage; signed URL posted to channel with French caption + expiry notice.
- AC5.3: On any pipeline failure, a French error message naming the failing stage is posted (no stack traces leaked).

## Edge Cases

1. **Empty Gemini response** — Retry once with broader prompt; if still empty, abort with "subject too narrow" message.
2. **Gemini returns hallucinated URLs** — Source validation must HEAD-check (or GET for content-type) each URL with a 5 s timeout; drop dead links before upload.
3. **Source paywalled/JS-rendered** — NotebookLM cannot ingest paywalled content. Validator detects `200 + content-length < 2KB` heuristic or known paywall domains list → drop.
4. **YouTube source has no transcript** — Pre-check via YouTube oEmbed + transcript availability; drop if absent.
5. **Duplicate URL after normalization** — Strip query params (except `v=` for YouTube), lowercase host, trim trailing slash before dedup.
6. **Subject contains Discord mention or markdown** — Strip `<@…>`, backticks, and zero-width chars before sending to Gemini.
7. **User cancels mid-pipeline** — Out of MVP scope; document as known limitation.
8. **NotebookLM CAPTCHA** — Worker must detect CAPTCHA DOM presence and surface a `CAPTCHA_REQUIRED` error; admin alert via separate Discord webhook for manual intervention.
9. **Google "Verify it's you" interstitial** — Same handling as CAPTCHA; needs a one-time human-in-the-loop login + persistent cookie storage volume.
10. **NotebookLM source upload partial failure** — One bad source shouldn't fail the whole notebook if ≥ 80 % succeed; log the dropped sources.
11. **Concurrent invocations exceeding browser worker capacity** — Queue with bounded backlog (e.g., 5 pending); reject 6th with "system busy" French message.
12. **Style preset removed/renamed by NotebookLM upstream** — Worker validates preset availability at session start and surfaces a "preset deprecated" error.
13. **Subject in a language other than fr/en** — Gemini handles it; document as accepted but unsupported.
14. **Discord interaction token expires** (3-second initial ack, 15-minute follow-up window) — Bot must `defer` within 3 s and use follow-up webhooks. For longer pipelines, follow-ups via channel.send rather than interaction webhook.

## Gemini Prompt Contract (proposed)

System prompt (English, sent verbatim):

> You are a research curator. Given a subject (1-2 sentences) and an output mode, return a JSON array of 8 high-quality sources suitable for ingestion by NotebookLM. Each source must be publicly accessible without authentication and have textual or transcribable content. Prefer recency (≤ 24 months) unless the subject is historical. Required JSON schema (no prose, no markdown fences):
> ```
> {
>   "sources": [
>     {
>       "url": "string (https)",
>       "title": "string",
>       "type": "paper|youtube|article|video_other",
>       "relevance_score": 0.0–1.0,
>       "language": "fr|en|other",
>       "rationale": "one sentence in English"
>     }
>   ]
> }
> ```
> Constraints: no paywalled domains (list: nytimes.com, ft.com, wsj.com, sciencedirect.com without open-access flag, …); no social-media posts; no homepages (must be deep links); at least one academic source and at least one video source.

Request body (per call): `{subject: str, mode: 'podcast'|'video', language_hint: 'fr'|'en'}`.

Validation pipeline: schema → URL liveness (HEAD, 5 s) → dedup (normalized URL) → type-mix check → count check.

## Discord Slash Command Shape (proposed)

```
/podcast
  subject  (string, required, 40–400 chars)
  mode     (choice, required, [podcast, video])
  style    (choice, optional, populated from notebooklm_styles.json)
```

Validation rules in bot:
- If `mode=video` and `style` is null → ephemeral French error.
- If `mode=podcast` and `style` is set → ignored with informational ephemeral note.
- Subject runs through `validate_subject(text)`: length, sentence count, mention/markdown strip, then optional Gemini specificity classifier.
- On validation pass: `interaction.defer()` then HTTP POST to n8n webhook; reply text "Reçu — génération en cours. Cela peut prendre jusqu'à 15 minutes."

## Internal Inconsistencies in User Brief

1. **"Pipeline must be linear"** vs source-validation retry loops and CAPTCHA fallback — default: linear *happy path*; explicit error paths exit early to Discord with French message rather than branching back. Retries within a single stage are allowed.
2. **"Discord bot reacts to mention OR slash command"** — both supported is double the surface. Default: slash command only in MVP.
3. **"Video style chosen from NotebookLM's built-in presets"** — list is config-file-driven and refreshed manually with each NotebookLM UI release.
4. **"All secrets via docker-compose env"** vs Google session cookies (which are files) — env carries credentials for *first* login; subsequent sessions persist as files in a named Docker volume excluded from git via `.gitignore`.
5. **Language split (FR user, EN dev)** vs Gemini prompts — Gemini system prompt is English (dev-facing), subject passed as-is (likely FR). Explicit `language_hint` parameter recommended.

## Open Questions for User

- [x] Slash command vs mention parsing as MVP entry point — **DECIDED: slash command MVP, mention deferred**.
- [ ] Where does the headless browser run? — **Recommendation: separate `worker` container running Playwright + queue listener, not in-n8n.** Confirm before Phase 0.
- [ ] Single service Google account or OAuth-per-user? — Recommendation: single service account for MVP; document ToS risk acceptance.
- [ ] Output delivery: Discord attachment vs signed-URL object storage? — Recommendation: Discord-direct if <25 MB else object storage. Confirm storage backend (MinIO sidecar vs external S3).
- [ ] Maximum concurrent pipelines / queue depth? — Recommendation: 1 in-flight + 4 queued for MVP.
- [x] Authoritative NotebookLM video preset list — **User commitment: paste before Phase 1 starts**.
- [ ] Source count target (5 / 8 / 15)? — Recommendation: target 8, accept 5–15.
- [ ] Subject language: French verbatim vs translated to English before Gemini? — Recommendation: verbatim FR with `language_hint=fr` to Gemini.
- [ ] Per-user / per-channel rate limit policy? — Recommendation: 3 podcasts/day/user, 20/day global, hard kill switch env var.
- [ ] CAPTCHA / "verify it's you" human-in-the-loop runbook owner? — Operator (user) for MVP; alert via separate Discord webhook.
- [ ] Acceptable cost ceiling per invocation (Gemini tokens)? — Recommendation: 50k input + 5k output per call; cap retries.
