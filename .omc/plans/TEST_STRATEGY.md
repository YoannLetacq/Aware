# Test Strategy — Podcast Pipeline

> Greenfield project. Tests define the contract before implementation.
> TDD law: failing test first, minimal code to pass, then refactor.
> All ACs from `requirements.md` (AC1–AC5) must map to a named test.

---

## 1. Goals & Testing Pyramid

| Layer        | Target share | Runner      | Gate            |
|--------------|-------------|-------------|-----------------|
| Unit         | 70 %        | pytest      | always          |
| Integration  | 20 %        | pytest      | always          |
| E2E smoke    | 10 %        | pytest      | `NOTEBOOKLM_LIVE=1` |

Quality bar (inherits `AGENT_CONDUCT.md` §1.1–1.2):
- Python: `ruff` clean + `pylint 10.00/10` + `mypy --strict` + `pytest` green
- Dockerfiles: `hadolint` zero warnings
- YAML/JSON configs: `yamllint` + `jsonlint`
- Node (only if worker ships JS): `eslint --max-warnings 0` + `tsc --noEmit`

Primary worker language: **Python 3.12**. Node toolchain listed as fallback only.

**AC5.2 deferral**: oversize-artifact → signed-URL path is deferred to Phase 3 by design (storage backend undecided per `requirements.md` open question). Tracked in §12 gap register.

---

## 2. Proposed Repo Layout

```
podcast/
├── bot/                        # Discord slash-command handler (Python)
│   └── tests/
│       ├── unit/               # Layer 1 tests
│       └── fixtures/           # Recorded Discord interaction JSON
├── worker/                     # Playwright browser-worker (Python)
│   └── tests/
│       ├── unit/
│       ├── integration/        # Layer 3 tests (mock NotebookLM)
│       └── fixtures/
├── gemini/                     # Gemini client + validation
│   └── tests/
│       ├── unit/
│       └── cassettes/          # vcrpy recorded HTTP fixtures
├── db/
│   ├── init.sql                # podcast.* schema (separate from public.*)
│   └── tests/                  # Layer 5 Postgres tests
├── n8n/
│   ├── workflows/              # Workflow JSON exports
│   └── tests/                  # Layer 4 n8n integration tests
├── tests/
│   └── idempotency/            # Layer 6 cross-cutting tests
├── scripts/
│   └── preflight.sh            # Single-command quality gate
├── config/
│   └── notebooklm_styles.json  # Preset enum (authoritative source)
└── docker-compose.yml
```

---

## 3. Layer 1 — Discord Trigger Contract

**Framework**: `pytest` · **Location**: `bot/tests/unit/`
**CI command**: `cd bot && pytest tests/unit/ -v`

### Fixtures

`bot/tests/fixtures/interaction_valid.json` — recorded Discord slash-command payload:
```json
{
  "type": 2,
  "id": "1234567890",
  "application_id": "9876543210",
  "token": "fixture-token",
  "data": {
    "name": "podcast",
    "options": [
      {"name": "subject", "value": "L'impact des LLMs sur la médecine en 2025. Quels sont les usages réels ?"},
      {"name": "mode",    "value": "podcast"}
    ]
  },
  "member": {"user": {"id": "111222333"}}
}
```

`bot/tests/fixtures/interaction_video.json` — same with `mode=video`, `style=Explainer`.

### Tests → AC mapping

| Test name | AC | Assertion shape |
|-----------|-----|-----------------|
| `test_valid_podcast_payload_passes_validation` | AC1.4 | `validate_payload(fixture)` returns dataclass with all fields; no exception |
| `test_video_mode_requires_style` | AC1.2 | `validate_payload({mode:video, style:None})` raises `ValidationError` with French message |
| `test_subject_below_min_chars_rejected` | AC1.3 | 39-char subject raises `SubjectValidationError(rule='min_chars')` |
| `test_subject_above_max_chars_rejected` | AC1.3 | 401-char subject raises `SubjectValidationError(rule='max_chars')` |
| `test_subject_three_sentences_rejected` | AC1.3 | Subject with 3 `.` separators raises `SubjectValidationError(rule='max_sentences')` |
| `test_ed25519_valid_signature_passes` | security | `verify_signature(pub_key, body, sig)` returns True for genuine Discord payload |
| `test_ed25519_tampered_body_rejected` | security | Mutated body raises `InvalidSignatureError` |
| `test_webhook_payload_schema` | AC1.4 | `build_n8n_payload(interaction)` contains all keys: `interaction_id, user_id, channel_id, subject, mode, style, timestamp, locale` |
| `test_subject_strips_discord_mention` | edge-case 6 | `sanitize_subject("<@123> Explain AI")` → `"Explain AI"` with no mention tokens |
| `test_mode_enum_rejects_unknown_value` | AC1.2 | `validate_payload({mode:"invalid"})` raises `ValidationError` |
| `test_defer_called_within_3s_budget` | AC1.1 | `handle_interaction(fixture)` calls `interaction.defer()` within 2 s wall-clock; mocked client receives a French ack string matching `"Reçu"` |

**Library**: `pynacl` for Ed25519 verification (no external call; fixture key pair generated once in `conftest.py`).

---

## 4. Layer 2 — Gemini Integration

**Framework**: `pytest` + `vcrpy` + `respx` · **Location**: `gemini/tests/unit/`
**CI command**: `cd gemini && pytest tests/unit/ -v --record-mode=none`

### Fixtures

`gemini/tests/cassettes/sources_ok.yaml` — VCR cassette of a nominal Gemini response with 8 sources conforming to the `Sources` schema.
`gemini/tests/cassettes/sources_malformed.yaml` — response where JSON is wrapped in markdown fences.
`gemini/tests/cassettes/rate_limit_then_ok.yaml` — cassette sequence: first call returns HTTP 429, second returns 200 with valid body.

`gemini/tests/fixtures/sources_schema.json` — JSON Schema for the `Sources` response object (matches Gemini Prompt Contract in `requirements.md`).

### Tests → AC mapping

| Test name | AC | Assertion shape |
|-----------|-----|-----------------|
| `test_response_conforms_to_sources_schema` | AC2.2 | `parse_gemini_response(cassette_ok)` returns list; `jsonschema.validate(result, schema)` passes |
| `test_source_count_within_bounds` | AC2.3 | Parsed list has `5 ≤ len ≤ 15`; list of 4 raises `SourceCountError` |
| `test_each_source_has_required_fields` | AC2.4 | Each item has `url, title, type, relevance_score, language`; type ∈ `{paper,youtube,article,video_other}`; score ∈ [0,1] |
| `test_malformed_json_fence_stripped_and_parsed` | AC2.2 | Markdown-fenced response still parses to valid sources list |
| `test_retry_on_rate_limit_succeeds` | AC2.1 | With cassette returning 429→200, client returns valid list after 1 retry; `max_tries=2` exhausted raises `GeminiRateLimitError` |
| `test_empty_response_triggers_retry_then_abort` | edge-case 1 | Empty `sources` array → `SourceCountError` after 1 retry |
| `test_gemini_request_builder_includes_subject_mode_lang` | AC2.1 | `build_gemini_request(subject, mode, language_hint)` body contains `subject`, `mode`, `language_hint` keys |
| `test_url_type_must_be_https` | AC2.4 | Source with `url="http://…"` fails schema validation |

**vcrpy** record mode in CI: `--record-mode=none` (cassettes pre-recorded; no live calls).
**respx** used for retry-sequence tests where vcrpy cassette ordering is insufficient.

---

## 5. Layer 3 — Playwright Browser-Worker

**Framework**: `pytest-playwright` · **Location**: `worker/tests/integration/`
**CI command**: `pytest worker/tests/integration/ -v -m "not live"`
**Live gate**: `pytest worker/tests/integration/ -v -m live` requires `NOTEBOOKLM_LIVE=1`

### Mock strategy

A local FastAPI shim (`worker/tests/fixtures/notebooklm_shim.py`) serves:
- `/` — minimal NotebookLM HTML skeleton with stable CSS selectors matching `selectors.py`
- `/notebook/new` — returns a fixture notebook page
- `/source/upload` — echoes upload status as JSON
- `/generate/audio` — simulates polling endpoint returning `{status: "complete", url: "/download/test.mp3"}`

The shim is launched as a `pytest` fixture (`scope="session"`) using `uvicorn` in a background thread. Playwright connects to `http://localhost:8765` instead of `notebooklm.google.com`.

### Tests → AC mapping

| Test name | AC | Assertion shape |
|-----------|-----|-----------------|
| `test_notebook_opens_within_30s` | AC3.1 | `page.goto(shim_url)` completes; `page.title()` matches expected pattern in < 30 s |
| `test_notebook_created_with_correct_title` | AC3.2 | After `create_notebook(subject, iso_date)`, h1 text matches `f"{subject[:60]} — {iso_date}"` |
| `test_all_sources_uploaded` | AC3.3 | Uploading 8 fixture URLs; `upload_sources(sources)` returns dict with 8 successes |
| `test_partial_upload_failure_above_threshold_continues` | AC3.3 | 7/8 succeed (87.5 %); pipeline continues |
| `test_upload_failure_below_80pct_aborts` | AC3.3 | 3/8 succeed; `upload_sources` raises `UploadThresholdError` |
| `test_customization_prompt_set` | AC3.4 | `set_customization(subject)` fills the prompt textarea; shim confirms French text present |
| `test_audio_generation_triggered_and_downloaded` | AC4.1 | `generate(mode="podcast")` polls shim until `status=complete`; artifact path ends in `.mp3` |
| `test_video_style_selected_from_preset` | AC4.2 | `generate(mode="video", style="Explainer")` selects the preset in shim dropdown; artifact ends in `.mp4` |
| `test_unknown_style_raises_preset_error` | edge-case 12 | `generate(mode="video", style="Deleted")` raises `PresetUnavailableError` |
| `test_captcha_dom_detected_and_surfaced` | edge-case 8 | Shim injects CAPTCHA element; worker raises `CaptchaRequiredError` |
| `test_artifact_filename_matches_interaction_id` | AC4.3 | Downloaded artifact filename == `f"{interaction_id}.mp3"` |
| `test_artifact_meta_json_written` | AC4.4 | `runs/{interaction_id}/meta.json` contains `size_bytes` and `sha256` |
| `[live] test_real_notebooklm_opens` | AC3.1 | Marked `@pytest.mark.live`; skipped unless `NOTEBOOKLM_LIVE=1` |

**Selector isolation**: all CSS selectors live exclusively in `worker/selectors.py` with a `SELECTORS_VERSION` constant. Tests import from there; shim HTML uses the same class names.

---

## 6. Layer 4 — n8n Workflow

**Framework**: shell + Python `httpx` shim server · **Location**: `n8n/tests/`
**CI command**: `bash n8n/tests/run_workflow_test.sh`

### Strategy

n8n has no native unit-test runner for workflow JSON. The test approach:

1. **Schema/structure lint** (`n8n/tests/test_workflow_schema.py`): load `workflows/podcast.json`, assert node count ≤ 10 (linear guard from `requirements.md` scope risk), assert no credential IDs in exported JSON (critique L2), assert webhook trigger node present, assert all HTTP nodes reference environment variables not hardcoded secrets.

2. **Execution integration test**: start a stripped `docker-compose` (postgres + n8n only) in CI, import the workflow, then call `n8n execute --file=n8n/workflows/podcast.json` (verify flag against n8n version pinned in compose). Stub external endpoints via a FastAPI shim running on the same Docker network.

   *Caveat*: `n8n execute --file` flag availability varies by n8n version. Pin `n8nio/n8n:1.x` in `docker-compose.yml` and document the exact flag in a comment.

### Tests → AC mapping

| Test name | AC | Assertion shape |
|-----------|-----|-----------------|
| `test_workflow_has_no_hardcoded_credential_ids` | critique L2 | JSON walk finds no `"credentials"` key with a non-empty `id` value in exported file |
| `test_workflow_node_count_within_limit` | scope risk | `len(workflow["nodes"]) <= 10` |
| `test_webhook_trigger_node_present` | AC1.4 | Node with `type` matching `"webhook"` exists |
| `test_n8n_posts_payload_to_worker_stub` | AC1.4 | Stub captures POST; asserts body has `interaction_id, subject, mode` |
| `test_n8n_posts_result_back_to_discord` | AC5.1 | After worker stub returns artifact URL, n8n calls Discord stub with `content` field |
| `test_pipeline_failure_posts_french_error_no_stack_trace` | AC5.3 | Worker stub returns HTTP 500; Discord stub receives message matching French-error regex; body contains no `Traceback` substring |

---

## 7. Layer 5 — Postgres State

**Framework**: `pytest` + `testcontainers-python` · **Location**: `db/tests/`
**CI command**: `cd db && pytest tests/ -v`

### Container pattern

```python
# db/tests/conftest.py
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def pg():
    # postgres:16-alpine mirrors veille_auto/docker-compose.yml service
    with PostgresContainer("postgres:16-alpine") as c:
        engine = create_engine(c.get_connection_url())
        # Apply init.sql — idempotent CREATE IF NOT EXISTS pattern
        # from refs/veille_auto/scripts/init.sql lines 6–54
        with open("db/init.sql") as f:
            engine.execute(f.read())
        yield engine
```

### Schema note

`db/init.sql` for the podcast pipeline uses schema `podcast` (not `public`), per critique L3:
```sql
CREATE SCHEMA IF NOT EXISTS podcast;
CREATE TABLE IF NOT EXISTS podcast.jobs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    interaction_id TEXT UNIQUE NOT NULL,
    user_id        TEXT NOT NULL,
    subject_hash   TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('pending','running','done','failed')),
    artifact_url   TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, subject_hash)
);
```

### Tests → AC mapping

| Test name | AC / critique | Assertion shape |
|-----------|---------------|-----------------|
| `test_init_sql_applies_cleanly` | ops | `pg` fixture builds without error; `podcast.jobs` exists |
| `test_status_check_constraint_rejects_invalid` | state machine | `INSERT ... status='zombie'` raises `IntegrityError` |
| `test_interaction_id_unique_constraint` | idempotency | Second INSERT with same `interaction_id` raises `UniqueViolation` |
| `test_updated_at_trigger_fires` | schema | UPDATE row; `updated_at` > `created_at` |
| `test_artifact_url_nullable` | AC4.4 | INSERT with `artifact_url=NULL` succeeds |

---

## 8. Layer 6 — Idempotency

**Framework**: `pytest` + same `testcontainers` fixture · **Location**: `tests/idempotency/`
**CI command**: `pytest tests/idempotency/ -v`

### Tests → AC / critique mapping

| Test name | AC / critique | Assertion shape |
|-----------|---------------|-----------------|
| `test_duplicate_subject_hash_not_inserted` | M3 | Two `upsert_job(user_id, subject_hash)` calls; DB contains exactly 1 row; second call returns existing `id` |
| `test_replay_same_interaction_id_is_noop` | M3 | Replay `interaction_id` after `status=done`; row unchanged; worker not re-triggered |
| `test_different_user_same_subject_allowed` | M3 | `(user_a, hash_x)` and `(user_b, hash_x)` both insert; 2 rows exist |
| `test_subject_hash_normalized_before_store` | M3 | Subjects differing only in trailing whitespace produce same hash; single row |

`subject_hash` = `sha256(subject.strip().lower())` (deterministic, case/space insensitive).

---

## 9. Layer 7 — Lint & Quality Gates

**CI command**: see `/preflight` script below.

| Tool | Target | Command | Pass condition |
|------|--------|---------|---------------|
| `ruff` | Python worker/bot/gemini | `ruff check .` | zero findings |
| `pylint` | Python worker/bot/gemini | `pylint worker/ bot/ gemini/ --fail-under=10.00` | score = 10.00/10 |
| `mypy` | Python | `mypy --strict worker/ bot/ gemini/` | zero errors |
| `eslint` | Node (if applicable) | `eslint --max-warnings 0 .` | 0 warnings |
| `tsc` | Node (if applicable) | `tsc --noEmit` | 0 errors |
| `hadolint` | Dockerfiles | `hadolint Dockerfile*` | zero DL-level warnings |
| `yamllint` | docker-compose + configs | `yamllint docker-compose.yml config/` | zero errors |
| `jsonlint` | Workflow JSON + styles | `jsonlint n8n/workflows/*.json config/*.json` | valid JSON |
| `gitleaks` | Secrets scan | `gitleaks detect --no-git` | zero findings |

Suppression rules from `AGENT_CONDUCT.md` §2:
- No `# pylint: disable=` inline; suppressions only in `.pylintrc`.
- No `# noqa`, `# type: ignore`.
- No `eslint-disable` inline.

---

## 10. /preflight Script Outline

**Location**: `scripts/preflight.sh`
**Purpose**: single command before any commit or "feature complete" declaration.

```bash
#!/usr/bin/env bash
# scripts/preflight.sh — run before every commit (AGENT_CONDUCT.md §1.1)
set -euo pipefail

PYTHON_DIRS="worker bot gemini"
N8N_WORKFLOWS="n8n/workflows/*.json"
DOCKER_COMPOSE="docker-compose.yml"

echo "=== [1/8] ruff ==="
ruff check $PYTHON_DIRS

echo "=== [2/8] pylint ==="
pylint $PYTHON_DIRS --fail-under=10.00

echo "=== [3/8] mypy ==="
mypy --strict $PYTHON_DIRS

echo "=== [4/8] hadolint ==="
hadolint Dockerfile*

echo "=== [5/8] yamllint ==="
yamllint $DOCKER_COMPOSE config/

echo "=== [6/8] jsonlint ==="
for f in $N8N_WORKFLOWS config/*.json; do
  python3 -m json.tool "$f" > /dev/null && echo "OK: $f"
done

echo "=== [7/8] gitleaks ==="
gitleaks detect --no-git --source .

echo "=== [8/8] pytest ==="
pytest bot/tests/unit/ gemini/tests/unit/ worker/tests/unit/ \
       db/tests/ tests/idempotency/ \
       worker/tests/integration/ \
       -v --tb=short

echo ""
echo "preflight PASSED"
```

Live NotebookLM E2E (not in preflight, run manually or scheduled):
```bash
NOTEBOOKLM_LIVE=1 pytest worker/tests/integration/ -m live -v
```

---

## 11. veille_auto Reference Reuse

| Pattern | Source | Applied where |
|---------|--------|---------------|
| `openssl rand` env generation | `refs/veille_auto/scripts/setup.sh:46–48` | `scripts/preflight.sh` env-check prologue |
| Idempotent `CREATE TABLE IF NOT EXISTS` + `RAISE NOTICE` | `refs/veille_auto/scripts/init.sql:6–54, 226–233` | `db/init.sql` migration pattern |
| `postgres:16-alpine` + `pg_isready` healthcheck | `refs/veille_auto/docker-compose.yml:6–27` | `docker-compose.yml` service definition + testcontainer image tag |
| `filter_new_urls` / ON CONFLICT dedup pattern | `refs/veille_auto/scripts/init.sql:122–130` | `podcast.jobs` idempotency upsert |
| Gemini JSON parse with `MAX_TOKENS` guard | `refs/veille_auto/workflow-simplified.json` node "Parse AI Filter" | `gemini/tests/unit/test_parse.py` malformed-response fixture |

---

## 12. Coverage Gap Register

| Gap | Risk | When to fill |
|-----|------|-------------|
| Discord `deferReply` timing (H3 critique) | HIGH | Before Phase 1; unit-test that bot calls `defer()` within 3 s budget |
| Google session expiry detection in worker | HIGH | Phase 2; fixture simulating expired cookie → `SessionExpiredError` |
| Artifact > 25 MB → object storage path | MEDIUM | Phase 3; mock `discord.post_file` raises size error; assert fallback URL posted |
| Per-user daily rate-limit enforcement | MEDIUM | Phase 2; `upsert_job` rejects 4th job/day/user |
| `storageState.json` restricted-volume mount | MEDIUM | Deployment checklist; not testable in unit layer |
| n8n workflow credential-ID leak (critique L2) | LOW | Layer 4 schema test already covers this |
