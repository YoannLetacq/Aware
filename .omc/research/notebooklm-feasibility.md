# NotebookLM Automation Feasibility Study
<!-- Scientist agent — research session notebooklm-feasibility-2026-05-26 — 2026-05-26 -->

## 1. NotebookLM Current State (May 2026)

### Audio Overview
Audio Overview is the original podcast-style feature: two AI hosts discuss the notebook's
sources in a conversational format. It is available on all plans with per-day generation
quotas: 3/day (Free), 20/day (Plus), 200/day (Ultra).
[support.google.com/notebooklm/answer/16212820, retrieved 2026-05-26]

**Download format:** WAV (uncompressed). The UI exposes a three-dot "More" menu →
"Download". Typical size for a ~10-min episode: ~50 MB WAV (≈ 5 MB if re-encoded to MP3
externally). Generation time: **2–5 minutes** for average-length sources.
[exploreaitogether.com/export-download-notebooklm-guide, retrieved 2026-05-26]

### Video Overview
Video Overview launched at Google I/O in May 2025, began rolling out July 2025
[workspaceupdates.googleblog.com/2025/07/video-overviews-studio-panel-updates-notebooklm.html,
retrieved 2026-05-26]. A major Cinematic tier was added in March 2026
[blog.google/innovation-and-ai/products/notebooklm/generate-your-own-cinematic-video-overviews-in-notebooklm,
retrieved 2026-05-26].

**Formats (3):**
- `Cinematic` — immersive, animated visuals; **Google AI Ultra subscribers, 18+, English only**
- `Explainer` — structured, comprehensive overview; all eligible plans
- `Brief` — bite-sized (~60–90 s); all eligible plans

**Visual style presets (9 — BASELINE, unverified against live UI; user to overwrite):**
Classic | Whiteboard | Watercolor | Retro Print | Heritage | Paper-craft | Kawaii | Anime | Custom
Styles are available for `Explainer` and `Brief` formats only, **not** for `Cinematic`.
Auto-select is also available.
[support.google.com/notebooklm/answer/16454555, retrieved 2026-05-26]

**Customization input:** Steering Prompt (free-text field) for topic focus / audience / goals.

**Download format:** MP4 (downloaded via button in video player). Reported resolution: 1080p;
reported size: under 10 MB for typical Explainer/Brief videos.
[search result aggregate, retrieved 2026-05-26]

**Generation time:** Official docs state "sometimes more than 30 minutes."
[support.google.com/notebooklm/answer/16454555, retrieved 2026-05-26]
Practical community reports suggest 5–15 min for Explainer/Brief; Cinematic may exceed 30 min.

**Generation quotas (Ultra tier):** 200 Video Overviews/day.
[exploreaitogether.com/export-download-notebooklm-guide, retrieved 2026-05-26]

---

## 2. Google Login Automation — Failure Modes and Workarounds

### Failure modes
1. **Headless fingerprinting.** Google detects `navigator.webdriver`, missing GPU fingerprint,
   anomalous canvas/WebGL hashes, and IP reputation. A plain `chromium --headless` launch is
   flagged immediately. [latenode.com/blog/…avoiding-bot-detection, retrieved 2026-05-26]
2. **Device verification / "Verify it's you" flow.** Google prompts on new-IP or new-device
   logins regardless of 2FA setting. This interrupts automation silently — the page stalls
   without raising an exception.
3. **2FA (TOTP / SMS).** Headless automation cannot intercept a push notification or
   hardware key. TOTP seeds can be pre-seeded for programmatic OTP generation, but storing
   the seed raises the same security concerns as the password itself (see critique.md H4).
4. **Embedded-framework block.** Google has blocked Google Account sign-in from all embedded
   browser frames since January 2021. Only top-level Chrome contexts are accepted.
   [developers.googleblog.com/guidance-to-developers-affected-by-our-effort-to-block-less-secure-browsers-and-applications,
   retrieved 2026-05-26]
5. **Account suspension.** Google suspends accounts showing unusual automated activity
   patterns. A personal account suspension is irrecoverable in the short term.
   [hidemyacc.com/google-account-suspended, retrieved 2026-05-26]

### Workarounds

**Playwright `storageState` re-use (recommended primary approach):**
Authenticate once manually via `playwright codegen` or a headed launch → save cookies,
localStorage, sessionStorage to `storageState.json`. On subsequent runs, load the file via
`browser.new_context(storage_state="storageState.json")`. This avoids re-login entirely
until the session expires.
[adequatica.medium.com/google-authentication-with-playwright, retrieved 2026-05-26;
labs.sogeti.com/…mfa-how-playwrights-built-in-storage-state…, retrieved 2026-05-26]

**Session durability:** Google sessions on Workspace accounts tend to last weeks to months;
personal accounts are shorter-lived and less predictable. A **burner Google Workspace
account** is strongly preferred (aligns with critique.md H2, H4).

**Stealth mode:** `playwright-extra` + `puppeteer-extra-plugin-stealth` patched the main
fingerprinting vectors but maintenance **stopped in March 2023**
[search result aggregate, retrieved 2026-05-26]. As of 2025–2026, projects rely on
launching a **headed Chromium with `--disable-blink-features=AutomationControlled`** plus
realistic viewport, UA string, and mouse-movement simulation.

**OAuth alternative:** No public OAuth scope covers NotebookLM. There is no Google-documented
API for NotebookLM notebook or generation operations. Browser automation is the only viable
path.

**Risk summary:** `storageState` reuse on a dedicated Workspace account, with headed
Chromium and stealth flags, is the workable approach. It is not zero-risk — Google can
invalidate the session or flag the IP at any time. This is the unavoidable consequence of
building on an undocumented surface (critique.md H2).

---

## 3. Community Wrappers

### notebooklm-py (primary candidate)
- **PyPI:** `pip install "notebooklm-py[browser]"` — Python 3.10–3.14
  [pypi.org/project/notebooklm-py, retrieved 2026-05-26]
- **GitHub:** github.com/teng-lin/notebooklm-py — v0.5.0 released 2026-05-24;
  15.2k stars, 2.1k forks, 1 260 commits. Active.
- **Surface exposed:** notebook CRUD, source management (URL/PDF/YouTube/Drive), Audio
  Overview (4 formats, 3 lengths, 50+ languages) → MP3/MP4 download, Video Overview
  (3 formats, 9 visual styles) → MP4 download, slide decks, quizzes, flashcards,
  infographics, mind maps, data tables, reports, multi-account support.
- **Mechanism:** Playwright + Chromium. Supports cookie import from existing browser sessions.
  Also exposes a library-only mode (no Playwright) that calls undocumented internal REST
  endpoints directly.
- **ToS exposure:** Explicitly flagged in README: "undocumented Google APIs that can change
  without notice. Not affiliated with Google." MIT license.
- **Does it obviate the browser?** Partially — the library-only mode uses undocumented
  internal endpoints (higher breakage risk); the browser mode still requires Chromium but
  abstracts all selector management. **This library is the most practical building block**
  and would obviate writing raw Playwright selectors from scratch.

### notebooklm-podcast-automator
- **GitHub:** github.com/upamune/notebooklm-podcast-automator — 31 stars, 11 forks. Active.
- **Surface:** Notebook creation, URL/YouTube source add, Audio Overview generation +
  Spotify upload. Playwright + CDP. Does **not** wait for generation completion (polling
  not implemented). Narrow scope; superseded by notebooklm-py for this use case.

### osen77/NotebookLM-API
- **GitHub:** github.com/osen77/NotebookLM-API — 42 commits, 12 stars. Active.
- **Surface:** FastAPI wrapper over Playwright; URL/YouTube/text upload, Audio Overview
  generation + status tracking + download URL retrieval, auto-login via cookies file, Docker.
  English and Hebrew. No ToS warning documented.
- **Assessment:** Smaller scope than notebooklm-py; useful as architectural reference for
  the REST-wrapper pattern but not preferred over notebooklm-py.

### DataNath/notebooklm_source_automation
- **GitHub:** github.com/DataNath/notebooklm_source_automation
- **Surface:** Source-add automation only via Playwright. No generation or download. Narrow.

**Verdict on wrappers:** notebooklm-py (v0.5.0, 2026-05-24) is the only wrapper covering
both Audio and Video Overview download with active maintenance. It does **not** eliminate
ToS risk — it inherits and concentrates it. Integrating it saves significant Playwright
selector engineering but adds a community-dependency risk.

---

## 4. Artifact Retrieval

### Audio Overview
- **Format:** WAV download via UI three-dot menu. Some sources report MP3; WAV is confirmed
  by Google support documentation and the notebooklm-py library (which downloads as MP3 by
  re-encoding internally).
- **Typical size:** ~10–50 MB WAV for a 5–25 min episode. Re-encode to MP3 for Discord
  upload compliance (Discord free-tier limit: 25 MB).
- **Generation latency:** 2–5 minutes. Polling interval: 15–30 s is reasonable.
- **Retrieval mechanism:** notebooklm-py or raw Playwright — wait for the "Download" button
  to become active, intercept the network response carrying the audio blob, or click and
  capture to a temp path.

### Video Overview
- **Format:** MP4 download via button in video player.
- **Typical size:** < 10 MB for Explainer/Brief (1080p, short duration).
- **Generation latency:** 5–15 min (Explainer/Brief); up to 30+ min (Cinematic per official
  docs). Polling interval: 30–60 s.
- **Retrieval mechanism:** Same pattern — wait for download button, intercept or click-save.
  notebooklm-py exposes a `download_video_overview()` method.
- **Streaming / HLS:** No evidence of HLS streaming in the UI. The video player is embedded
  and download is a direct file transfer. No CDN URL pattern confirmed from public sources.

### Quota ceilings (Ultra tier — the required plan for Video Overview at scale)
| Feature              | Free | Plus | Ultra |
|----------------------|------|------|-------|
| Audio Overviews/day  |  3   |  20  |  200  |
| Video Overviews/day  |  0*  |  0*  |  200  |
*Video Overview available on all plans; Ultra quota confirmed. Free/Plus limits unconfirmed.

---

## 5. Integration Shape with n8n — Worker Architecture

### Confirming critique.md H1

The H1 finding stands: Video Overview generation takes 5–30+ minutes.
n8n's default execution model runs each node synchronously in a single worker process.
`EXECUTIONS_TIMEOUT` (default: varies by hosting, commonly 300 s / 5 min) will kill the
execution mid-generation. Even in Queue Mode (n8n's Redis-backed scaling layer), a single
job occupying a worker for 30 min starves every other execution on that worker.
[docs.n8n.io/hosting/scaling/queue-mode, retrieved 2026-05-26]

### The three candidate topologies

The critique listed three options:
1. **HTTP webhook sidecar** — n8n POSTs to a worker HTTP endpoint; worker calls back via
   webhook when done.
2. **Redis queue** — n8n pushes a job to Redis; worker polls Redis; worker posts result to
   n8n webhook.
3. **Postgres NOTIFY** — n8n inserts a row; worker receives `LISTEN/NOTIFY`; worker updates
   row and triggers n8n webhook.

### Recommended: HTTP webhook sidecar (Option 1)

**Justification:**

- **Operational simplicity.** This project already runs Postgres and Discord, but does not
  yet have Redis. Adding Redis solely for job queuing is infrastructure overhead that Option
  1 avoids. n8n Queue Mode itself uses Redis for internal worker scaling; that Redis instance
  can serve both roles if Queue Mode is adopted, but the dependency is already present only
  when Queue Mode is in use.
- **Alignment with n8n's native webhook node.** n8n has a built-in Webhook trigger node.
  The worker completing a generation simply POSTs to `http://n8n:5678/webhook/<uuid>` with
  `{job_id, artifact_url, status}`. This re-enters the n8n workflow at exactly the right
  node with zero custom polling code in n8n.
- **Failure isolation.** The worker is a separate container. A worker crash or Chromium OOM
  does not affect the n8n process. A worker restart does not lose the in-progress session
  if `storageState.json` is on a persistent volume.
- **Postgres NOTIFY (Option 3) rejected:** Requires the worker to maintain a persistent
  Postgres connection with `LISTEN`. This conflates the job queue and the application DB,
  couples worker restart semantics to DB connection liveliness, and adds latency from the
  NOTIFY → wake-up cycle vs. a direct POST. It is elegant but over-engineered for this
  single-tenant pipeline.
- **Redis queue (Option 2) rejected:** Adds a mandatory new infrastructure component with no
  other use in the current architecture. BullMQ/RQ also require separate queue-monitor
  tooling. Prefer when concurrency > 1 worker instance is needed; defer to v2.

**Recommended container topology (Docker Compose):**

```
n8n            — orchestrator, Discord interaction handling, trigger/post-back
notebooklm-worker — Python FastAPI + notebooklm-py + Playwright/Chromium
postgres       — shared; worker uses podcast.* schema (critique.md L3)
```

Worker exposes `POST /jobs` (accepts subject, mode, style, job_id) → returns 202 immediately.
Worker executes browser automation, polls for completion, downloads artifact, stores to
MinIO/local volume, then calls `POST http://n8n:5678/webhook/<CALLBACK_UUID>`.
n8n webhook node resumes the workflow, posts artifact to Discord channel as a new message
(not via the original interaction token — critique.md H3).

`storageState.json` is mounted at `/secrets/storageState.json` (mode 600, worker UID only),
not in the repo, not in `.env`. Manual re-auth procedure: `docker exec -it notebooklm-worker
python -m notebooklm_worker.reauth` (headed Chromium, operator runs once per session expiry).

---

## 6. Verdict

**GO-WITH-CAVEATS**

The automation path is technically feasible as of May 2026:

- notebooklm-py v0.5.0 (2026-05-24) abstracts all Playwright selectors and exposes Audio
  and Video Overview download as first-class methods. Engineering the browser layer from
  scratch is unnecessary.
- Audio Overview: low-risk, fast (2–5 min), WAV download, well-understood.
- Video Overview (Explainer/Brief): medium-risk, 5–15 min generation, MP4 < 10 MB, workable.
- Video Overview (Cinematic): **Ultra plan required, English only, 30+ min** — out of scope
  for MVP.
- The HTTP-webhook-sidecar architecture resolves critique.md H1 without adding Redis.
- Session management via `storageState.json` on a Workspace burner account is the standard
  workaround; it is fragile but manageable with a documented re-auth procedure.

**Caveats that must be accepted before proceeding:**

1. **Single point of failure / ToS.** The entire pipeline depends on undocumented Google
   internals. Google can break notebooklm-py or suspend the account at any time with no SLA.
   A fallback TTS path (ElevenLabs / OpenAI TTS) behind a feature flag is the correct
   long-term hedge; defer to v2 only if the user explicitly accepts the risk.
2. **Session rotation is operational work.** storageState expires. A manual re-auth
   procedure must be documented and tested before production.
3. **notebooklm-py is a community dependency.** v0.5.0 is actively maintained but is not
   a Google product. Pin the version and snapshot vendor code for production.
4. **Video style preset list is not confirmed against live UI.** The planner should stub
   the enum with the 9-style baseline above, marked as user-overridable before Phase 1.
5. **File size / Discord upload.** WAV audio may exceed 25 MB on long episodes. Re-encode
   to MP3 in the worker, or use MinIO + Discord link. Decide before implementing the
   post-back step.

**Recommended worker architecture:** HTTP webhook sidecar (separate `notebooklm-worker`
container, `POST /jobs` → 202, callback to n8n Webhook node on completion).
