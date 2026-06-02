# QA Runbook — Podcast Pipeline Smoke Tests
# Date: 2026-05-26 | Env: local docker-compose

## Preconditions (one-time setup, not repeated per run)
- Discord application created; bot token in `.env` as `DISCORD_BOT_TOKEN`
- `DISCORD_APP_ID`, `DISCORD_GUILD_ID`, `DISCORD_TEST_CHANNEL_ID` set in `.env`
- `GEMINI_API_KEY`, `NOTEBOOKLM_SESSION_COOKIE` set in `.env`
- `DISCORD_ALLOWED_AUTHORS` contains your test user ID
- AWS credentials set if S3 fallback is exercised
- tmux >= 3.0 installed: `tmux -V`

---

## 1. Cold-Start

```bash
# 1.1 — Start stack
tmux new-session -d -s qa-cold-$(date +%s)
tmux send-keys -t qa-cold-* \
  "cd /home/yoann/podcast && docker compose up -d 2>&1 | tee /tmp/qa-compose-up.log" Enter

# 1.2 — Wait for all containers healthy (60 s timeout)
until docker compose ps --format json 2>/dev/null \
  | jq -e '[.[].Health] | all(. == "healthy")' &>/dev/null; do
  sleep 3; done
tmux capture-pane -t qa-cold-* -p | grep -E "healthy|running"
```
**Success**: every container row shows `healthy`. Log line: `Network podcast_default  Created`.

```bash
# 1.3 — n8n UI reachable
curl -sf http://localhost:5678/healthz | jq .status
```
**Success**: HTTP 200, body `{"status":"ok"}`.

```bash
# 1.4 — Import workflow JSON
curl -sf -X POST http://localhost:5678/api/v1/workflows/import \
  -H "Content-Type: application/json" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  --data @workflow.json | jq .id
```
**Success**: HTTP 200, response contains `"id": "<uuid>"`. Note the id.

```bash
# 1.5 — Link credentials (n8n REST)
curl -sf -X POST http://localhost:5678/api/v1/credentials \
  -H "Content-Type: application/json" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" \
  --data '{"name":"GeminiKey","type":"geminiApi","data":{"apiKey":"'"$GEMINI_API_KEY"'"}}' | jq .id
```
**Success**: HTTP 200, credential id returned. Repeat for `discordBotToken` and `notebooklmSession`.

```bash
# 1.6 — Activate workflow
curl -sf -X POST "http://localhost:5678/api/v1/workflows/<id>/activate" \
  -H "X-N8N-API-KEY: $N8N_API_KEY" | jq .active
```
**Success**: `true`.

---

## 2. Discord Trigger Smoke

```bash
# 2.1 — Register slash command (one-time per guild; idempotent)
curl -sf -X POST \
  "https://discord.com/api/v10/applications/$DISCORD_APP_ID/guilds/$DISCORD_GUILD_ID/commands" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{
    "name":"podcast",
    "description":"Generate a podcast or video overview",
    "options":[
      {"type":3,"name":"subject","description":"Topic","required":true},
      {"type":3,"name":"mode","description":"podcast|video","required":true,
       "choices":[{"name":"podcast","value":"podcast"},{"name":"video","value":"video"}]},
      {"type":3,"name":"style","description":"Style preset","required":false}
    ]}' | jq '.id,.name'
```
**Success**: HTTP 200 or 201; `"name": "podcast"` and a numeric command id.

```bash
# 2.2 — Fire minimal command from test channel (via Discord API bot-send simulation)
# In practice: manually type /podcast subject:"test" mode:podcast in $DISCORD_TEST_CHANNEL_ID
# Then poll for deferred interaction ACK within 3 s:
START=$(date +%s)
until curl -sf \
  "https://discord.com/api/v10/webhooks/$DISCORD_APP_ID/$INTERACTION_TOKEN/messages/@original" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN" | jq -e '.type == 5' &>/dev/null; do
  [[ $(($(date +%s)-START)) -gt 5 ]] && echo "FAIL: no ACK within 5s" && break
  sleep 1; done
```
**Success**: within 3 s the original interaction message is type 5 (DEFERRED_CHANNEL_MESSAGE). Discord channel shows spinner/`<bot> is thinking…`.

```bash
# 2.3 — Verify followup arrives (60 s budget)
START=$(date +%s)
until curl -sf \
  "https://discord.com/api/v10/webhooks/$DISCORD_APP_ID/$INTERACTION_TOKEN/messages/@original" \
  -H "Authorization: Bot $DISCORD_BOT_TOKEN" | jq -e '.content | length > 0' &>/dev/null; do
  [[ $(($(date +%s)-START)) -gt 60 ]] && echo "FAIL: no followup in 60s" && break
  sleep 3; done
```
**Success**: message content non-empty; n8n execution log shows `Workflow execution finished` with status `success`.

---

## 3. Happy-Path — Podcast

```bash
# Fire: /podcast subject:"Quantum error correction breakthroughs in 2026" mode:podcast
# Timing budget: 8–12 minutes end-to-end
```

| Stage | Expected log line (docker compose logs) | Timeout |
|---|---|---|
| Gemini sources returned | `[gemini-worker] sources_count=\d+` | 90 s |
| Playwright session started | `[browser-worker] notebooklm_session=open` | 3 min |
| NotebookLM job queued | `[browser-worker] job_id=\S+ status=queued` | 4 min |
| MP3 download complete | `[browser-worker] artifact_path=.*\.mp3 size_bytes=\d+` | 10 min |
| Discord reply sent | `[discord] message_id=\d+ attachment=.*\.mp3` | 12 min |

**Success**: Discord message in test channel contains an `.mp3` attachment or embed. Message text matches pattern: `Here is your podcast overview on Quantum error correction`.

---

## 4. Happy-Path — Video

```bash
# Fire: /podcast subject:"Quantum error correction breakthroughs in 2026" mode:video style:Explainer
# Timing budget: 12–18 minutes end-to-end
```

| Stage | Expected log line | Timeout |
|---|---|---|
| Style preset resolved | `[n8n] style=Explainer preset_loaded=true` | 10 s |
| Gemini sources returned | `[gemini-worker] sources_count=\d+` | 90 s |
| NotebookLM video job queued | `[browser-worker] job_id=\S+ type=video status=queued` | 4 min |
| MP4 download complete | `[browser-worker] artifact_path=.*\.mp4 size_bytes=\d+` | 15 min |
| Discord reply sent | `[discord] message_id=\d+ attachment=.*\.mp4` | 18 min |

**Success**: Discord message contains `.mp4` attachment or S3 link. Message text matches: `Here is your video overview on Quantum error correction`.

---

## 5. Error Paths

### 5.1 Invalid Style
```bash
# Fire: /podcast subject:"Quantum error correction..." mode:podcast style:InvalidXYZ
```
**Expected Discord reply** (within 5 s): `Unknown style preset 'InvalidXYZ'. Valid presets: [list].`
**Expected n8n log**: `[n8n] error=invalid_style preset=InvalidXYZ`

### 5.2 Vague Subject (<10 chars)
```bash
# Fire: /podcast subject:"AI" mode:podcast
```
**Expected Discord reply** (within 5 s): `Subject must be at least 10 characters.`
**Expected n8n log**: `[n8n] error=subject_too_short length=2`

### 5.3 Unauthorized User
```bash
# Fire from a Discord account whose ID is NOT in DISCORD_ALLOWED_AUTHORS
```
**Expected Discord reply** (within 5 s): `You are not authorized to use this command.`
**Expected n8n log**: `[n8n] error=unauthorized user_id=\d+`

### 5.4 Gemini Timeout
```bash
# Simulate: docker compose stop gemini-worker (or set GEMINI_API_KEY=invalid)
# Fire: /podcast subject:"Quantum error correction..." mode:podcast
```
**Expected Discord reply** (within 2 min): `Source gathering failed. Please try again later.`
**Expected n8n log**: `[gemini-worker] error=timeout after=\d+ms`

### 5.5 NotebookLM Session Expired
```bash
# Simulate: clear NOTEBOOKLM_SESSION_COOKIE in env, restart browser-worker
# docker compose up -d --force-recreate browser-worker
# Fire: /podcast subject:"Quantum error correction..." mode:podcast
```
**Expected log**: `[browser-worker] error=auth_required action=session_refresh`
**Expected Discord reply**: `NotebookLM session expired. An admin must refresh credentials.`

### 5.6 NotebookLM Rate-Limited
```bash
# Simulate: fire 3 concurrent /podcast commands in rapid succession
```
**Expected log**: `[browser-worker] error=rate_limited retry_after=\d+s`
**Expected Discord reply**: `NotebookLM is rate-limited. Your job is queued and will retry automatically.`

### 5.7 Artifact >25 MB (S3 Fallback)
```bash
# Simulate: place a 30 MB dummy file at the artifact path before Discord upload step
# OR configure a test subject known to produce long output
```
**Expected log**: `[discord] artifact_size=\d+ exceeds_limit=true fallback=s3_upload`
**Expected log**: `[discord] s3_url=https://\S+\.s3\.\S+\.amazonaws\.com/\S+`
**Expected Discord reply**: message contains `https://*.s3.*.amazonaws.com/` presigned URL with expiry note.
Discord direct upload must NOT be attempted (no `multipart/form-data` in n8n HTTP node log).

---

## 6. Cleanup

```bash
# 6.1 — Stop stack
cd /home/yoann/podcast && docker compose down

# 6.2 — Archive logs
mkdir -p /home/yoann/podcast/logs
docker compose logs --no-color > /tmp/qa-run.log 2>&1 || true
ARCHIVE=/home/yoann/podcast/logs/qa-$(date +%Y%m%d-%H%M%S).tar.gz
tar -czf "$ARCHIVE" /tmp/qa-compose-up.log /tmp/qa-run.log
echo "Logs archived to $ARCHIVE"

# 6.3 — Kill tmux sessions
tmux list-sessions 2>/dev/null | grep '^qa-' | cut -d: -f1 | xargs -I{} tmux kill-session -t {}
tmux list-sessions 2>/dev/null | grep '^qa-' && echo "WARN: orphan sessions remain" || echo "All qa-* sessions cleaned."
```

**Success**: `docker compose ps` returns empty. Tmux lists no `qa-*` sessions. Archive file present at `$ARCHIVE`.

---

## Summary Table

| # | Test | Timeout | Key Success Signal |
|---|---|---|---|
| 1 | Cold-start + stack health | 2 min | All containers `healthy`, n8n `/healthz` 200 |
| 2 | Slash command trigger + ACK | 5 s / 60 s | Type-5 deferred reply, followup non-empty |
| 3 | Happy-path podcast | 12 min | `.mp3` attachment in Discord |
| 4 | Happy-path video | 18 min | `.mp4` attachment or S3 URL in Discord |
| 5.1 | Invalid style | 5 s | `Unknown style preset` message |
| 5.2 | Vague subject | 5 s | `at least 10 characters` message |
| 5.3 | Unauthorized user | 5 s | `not authorized` message |
| 5.4 | Gemini timeout | 2 min | `Source gathering failed` message |
| 5.5 | NLM session expired | 30 s | `session expired` message + `auth_required` log |
| 5.6 | NLM rate-limited | 30 s | `queued and will retry` message |
| 5.7 | Artifact >25 MB | 2 min | S3 presigned URL in Discord, no direct upload |
| 6 | Cleanup | 30 s | No containers, no orphan sessions, logs archived |
