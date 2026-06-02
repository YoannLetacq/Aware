# veille_auto — Live Inventory
Generated: 2026-05-27. Read-only facts with file:line citations.

---

## 1. docker-compose.yml Service Inventory

Source: `/home/yoann/veille_auto/docker-compose.yml`

### Service: postgres
- **container_name**: veille-postgres (line 7)
- **image**: postgres:16-alpine (line 6) — no digest pin
- **restart**: unless-stopped (line 8)
- **networks**: veille-network (line 30)
- **ports**: 127.0.0.1:${POSTGRES_PORT:-5433}:5432 (line 18)
- **env vars (names)**: POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, TZ (lines 10–13)
- **depends_on**: none
- **healthcheck**: `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}` interval=10s timeout=5s retries=5 (lines 19–23)
- **volumes**:
  - ./data/postgres:/var/lib/postgresql/data (bind-mount, line 15)
  - ./scripts/init.sql:/docker-entrypoint-initdb.d/init.sql:ro (bind-mount, line 16)
- **logging**: json-file, max-size=10m, max-file=3 (lines 24–27)

### Service: n8n
- **container_name**: veille-n8n (line 37)
- **image**: n8nio/n8n:latest (line 36) — no pin; runtime version 2.1.4
- **restart**: unless-stopped (line 38)
- **networks**: veille-network (line 93)
- **ports**: 127.0.0.1:${N8N_PORT:-5678}:5678 (line 77)
- **env vars (names)**: N8N_ENCRYPTION_KEY, DB_TYPE, DB_POSTGRESDB_HOST, DB_POSTGRESDB_PORT, DB_POSTGRESDB_DATABASE, DB_POSTGRESDB_USER, DB_POSTGRESDB_PASSWORD, N8N_BASIC_AUTH_ACTIVE, N8N_BASIC_AUTH_USER, N8N_BASIC_AUTH_PASSWORD, WEBHOOK_URL, N8N_WEBHOOK_URL, DISCORD_WEBHOOK_URL, DISCORD_WEBHOOK_TECH_NEWS, DISCORD_WEBHOOK_COMPANIES, DISCORD_WEBHOOK_REDDIT, DISCORD_WEBHOOK_OTHERS, DISCORD_BOT_TOKEN, DISCORD_ALLOWED_AUTHORS, GEMINI_API_KEY, GEMINI_MODEL, N8N_PAYLOAD_SIZE_MAX, N8N_METRICS, N8N_HOST, N8N_PORT, N8N_PROTOCOL, N8N_EDITOR_BASE_URL, N8N_RUNNERS_MODE, TZ, GENERIC_TIMEZONE, N8N_BLOCK_ENV_ACCESS_IN_NODE, N8N_API_KEY, N8N_RESTRICT_FILE_ACCESS_TO, N8N_ENV_VARS (lines 40–75)
- **depends_on**: postgres (condition: service_healthy) (lines 84–86)
- **healthcheck**: none defined
- **volumes**:
  - ./data/n8n:/home/node/.n8n (bind-mount, line 82)
  - ./rss_sources.json:/home/node/rss_sources.json:ro (bind-mount, line 83)
- **dns**: 1.1.1.1, 8.8.8.8 (lines 78–80)
- **logging**: json-file, max-size=10m, max-file=3

### Service: rsshub
- **container_name**: veille-rsshub (line 99)
- **image**: diygod/rsshub:latest (line 99) — no pin
- **restart**: unless-stopped (line 100)
- **networks**: veille-network (line 115)
- **ports**: 127.0.0.1:1200:1200 (line 108)
- **env vars (names)**: NODE_ENV, CACHE_TYPE, CACHE_EXPIRE, TZ (lines 103–106)
- **depends_on**: none
- **healthcheck**: none defined
- **volumes**: none
- **logging**: json-file, max-size=10m, max-file=3

### Service: redis
- **container_name**: veille-redis (line 121)
- **image**: redis:7-alpine (line 121) — no pin
- **restart**: unless-stopped (line 122)
- **networks**: veille-network (line 140)
- **ports**: none exposed to host
- **env vars (names)**: TZ (line 125)
- **depends_on**: none
- **healthcheck**: `redis-cli ping` interval=10s timeout=5s retries=5 (lines 129–133)
- **volumes**:
  - ./data/redis:/data (bind-mount, line 127)
- **command**: redis-server --appendonly yes (line 128)
- **logging**: json-file, max-size=10m, max-file=3

### Service: webdis
- **container_name**: veille-webdis (line 146)
- **image**: nicolas/webdis:latest (line 147) — no pin
- **restart**: unless-stopped (line 148)
- **networks**: veille-network (line 159)
- **ports**: none exposed to host (internal 7379/tcp)
- **env vars (names)**: REDIS_HOST (line 150)
- **depends_on**: redis (condition: service_healthy) (lines 151–153)
- **healthcheck**: none defined
- **volumes**: none
- **logging**: json-file, max-size=10m, max-file=3

### Services commented out (not active)
- prometheus: prom/prometheus:latest — lines 163–179 (commented)
- grafana: grafana/grafana:latest — lines 182–199 (commented)

---

## 2. N8N_ENV_VARS Whitelist

Source: `/home/yoann/veille_auto/docker-compose.yml` line 75

```
N8N_ENV_VARS=DISCORD_WEBHOOK_URL,DISCORD_WEBHOOK_TECH_NEWS,DISCORD_WEBHOOK_COMPANIES,
DISCORD_WEBHOOK_REDDIT,DISCORD_WEBHOOK_OTHERS,DISCORD_BOT_TOKEN,DISCORD_ALLOWED_AUTHORS,
GEMINI_API_KEY,GEMINI_MODEL,POSTGRES_USER,POSTGRES_PASSWORD,POSTGRES_DB,WEBHOOK_URL,N8N_API_KEY
```

14 variables total. `N8N_BLOCK_ENV_ACCESS_IN_NODE=false` (line 72).

---

## 3. veille_auto/.env Key Names

Source: `/home/yoann/veille_auto/.env` (62 lines)

Keys present (values redacted):
```
POSTGRES_USER        (line 10)
POSTGRES_PASSWORD    (line 11)
POSTGRES_DB          (line 12)
POSTGRES_PORT        (line 13)
N8N_ENCRYPTION_KEY   (line 19)
N8N_BASIC_AUTH_ACTIVE (line 21)
N8N_BASIC_AUTH_USER  (line 22)
N8N_BASIC_AUTH_PASSWORD (line 24)
N8N_API_KEY          (line 26)
N8N_HOST             (line 28)
N8N_PORT             (line 29)
WEBHOOK_URL          (line 30)
DISCORD_WEBHOOK_REDDIT   (line 36)
DISCORD_WEBHOOK_COMPANIES (line 37)
DISCORD_WEBHOOK_TECH_NEWS (line 38)
DISCORD_WEBHOOK_OTHERS   (line 39)
DISCORD_BOT_TOKEN    (line 40)
GRAFANA_PASSWORD     (line 46)
RSSHUB_CACHE_EXPIRE  (line 51)
RSSHUB_CACHE_TYPE    (line 52)
TZ                   (line 57)
GEMINI_API_KEY       (line 59)
GEMINI_MODEL         (line 61)
```

Note: `DISCORD_WEBHOOK_URL` is declared as an env var in docker-compose.yml (line 52) but is NOT present as a key in `.env`. The compose line 75 includes it in `N8N_ENV_VARS` but it will resolve empty.

### Overlap with podcast/.env (from env.template)

**Keys present in BOTH veille_auto and podcast**:
POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT, N8N_ENCRYPTION_KEY, N8N_API_KEY, N8N_PORT, WEBHOOK_URL, DISCORD_BOT_TOKEN, DISCORD_ALLOWED_AUTHORS, GEMINI_API_KEY, GEMINI_MODEL, TZ

**Keys in veille_auto ONLY** (not in podcast):
N8N_BASIC_AUTH_ACTIVE, N8N_BASIC_AUTH_USER, N8N_BASIC_AUTH_PASSWORD, DISCORD_WEBHOOK_REDDIT, DISCORD_WEBHOOK_COMPANIES, DISCORD_WEBHOOK_TECH_NEWS, DISCORD_WEBHOOK_OTHERS, GRAFANA_PASSWORD, RSSHUB_CACHE_EXPIRE, RSSHUB_CACHE_TYPE

**Keys in podcast ONLY** (not in veille_auto):
BACKUP_PASSPHRASE, DISCORD_APP_ID, DISCORD_GUILD_ID, DISCORD_PUBLIC_KEY, GOOGLE_BURNER_EMAIL, GOOGLE_BURNER_PASSWORD, GOOGLE_BURNER_TOTP_SEED, KILL_SWITCH, NOTEBOOKLM_STORAGE_STATE_PATH, OPERATOR_DISCORD_WEBHOOK, RATE_LIMIT_GLOBAL_DAY, RATE_LIMIT_PER_USER_DAY, REDIS_PORT, WORKER_SHARED_TOKEN, N8N_WEBHOOK_URL

---

## 4. Network Topology

Live network (from `docker network ls`):
- **Name**: veille_auto_veille-network
- **Driver**: bridge
- **Scope**: local
- **ID**: 3e04648b9cd5

All 5 running services are on this single bridge network: veille-postgres, veille-n8n, veille-rsshub, veille-redis, veille-webdis (source: docker-compose.yml lines 30, 93, 115, 140, 159).

Internal service DNS names (within veille-network): `postgres`, `n8n`, `rsshub`, `redis`, `webdis`.

Podcast network: does not yet exist (podcast containers not running at time of snapshot).

---

## 5. Live Runtime State

Output of `docker ps --filter 'name=veille'` at time of snapshot:

| Name | Image | Ports | Status |
|------|-------|-------|--------|
| veille-webdis | nicolas/webdis:latest | 7379/tcp | Up 49 minutes |
| veille-n8n | n8nio/n8n:latest | 127.0.0.1:5678->5678/tcp | Up 49 minutes |
| veille-postgres | postgres:16-alpine | 127.0.0.1:5433->5432/tcp | Up 49 minutes (healthy) |
| veille-rsshub | diygod/rsshub:latest | 127.0.0.1:1200->1200/tcp | Up 49 minutes |
| veille-redis | redis:7-alpine | 6379/tcp | Up 49 minutes (healthy) |

All 5 services running. Claim confirmed.

---

## 6. Workflow: workflow-simplified.json

Source: `/home/yoann/veille_auto/workflow-simplified.json` (825 lines)

### Node count
28 nodes total.

### Node type breakdown
- 12x n8n-nodes-base.code
- 8x n8n-nodes-base.httpRequest
- 3x n8n-nodes-base.postgres
- 1x n8n-nodes-discord-trigger.discordTrigger
- 1x n8n-nodes-base.if
- 1x n8n-nodes-base.wait
- 1x n8n-nodes-base.rssFeedRead
- 1x n8n-nodes-base.readWriteFile

### Webhook paths registered
**None**. There are no `n8n-nodes-base.webhook` nodes. The workflow is triggered by a Discord bot mention (node "Discord Bot mention1", type `n8n-nodes-discord-trigger.discordTrigger`). No `/webhook/podcast` conflict.

### Postgres credential connection target
All 3 postgres nodes reference credential id `DO0poBoS0C0ayj8K` named "Postgres account":
- node: "Check existing articles1"
- node: "Insert into Database1"
- node: "Mark Sent"

The n8n service connects to postgres via `DB_POSTGRESDB_HOST=postgres` (internal DNS, compose line 43), `DB_POSTGRESDB_PORT=5432` (line 44), `DB_POSTGRESDB_DATABASE=${POSTGRES_DB}` (line 45). The credentials stored in n8n's encrypted database (`data/n8n/`) map to these same values. No plaintext host/database visible outside encrypted store.

### Redis usage
**No `n8n-nodes-base.redis` nodes**. Redis is accessed indirectly via **Webdis REST API** (HTTP requests to `http://webdis:7379/`):
- node "Acquire Lock1": `http://webdis:7379/SET/veille_lock/{{ $execution.id }}/NX/EX/900`
- node "Release lock": `http://webdis:7379/EVAL/...` (Lua CAS delete)

### Discord webhook URLs (env names used)
Webhook URLs are not hardcoded. In node "Sort Split & Limit" (Code node), `$env.DISCORD_WEBHOOK_TECH_NEWS`, `$env.DISCORD_WEBHOOK_COMPANIES`, `$env.DISCORD_WEBHOOK_REDDIT`, `$env.DISCORD_WEBHOOK_OTHERS` are read and attached as metadata to items. Node "Send to Discord" (HTTP Request) then POSTs to `{{ $json.webhook_url }}` — i.e. the value is passed through the pipeline from the Code node.

Discord Bot API calls (not webhooks) use `https://discord.com/api/v10/channels/...` directly (nodes: "Send already running message1", "DELETE already running message1", "Send processing message1").

Gemini calls use `https://generativelanguage.googleapis.com/v1beta/models/{{ $env.GEMINI_MODEL }}:generateContent` (nodes: "Gemini AI Filter", "Gemini Summarize").

### Code nodes reading `$env.X`
| Node | Variables read |
|------|----------------|
| Authorize Mention | `$env.DISCORD_ALLOWED_AUTHORS` |
| Sort Split & Limit | `$env.DISCORD_WEBHOOK_COMPANIES`, `$env.DISCORD_WEBHOOK_OTHERS`, `$env.DISCORD_WEBHOOK_REDDIT`, `$env.DISCORD_WEBHOOK_TECH_NEWS` |

All 5 variables are present in the `N8N_ENV_VARS` whitelist (line 75). `$env.GEMINI_MODEL` is read inline in HTTP URL expressions (not in Code nodes per se).

### Discord trigger details
- Node: "Discord Bot mention1"
- Guild ID: 1267071323864301589
- Channel IDs: 1448308430795313263, 1448308549162631188, 1448308621652922441, 1450443575354724494
- Pattern: botMention
- Credential: "Discord Bot Trigger account" (id: 0LtsnxnI50JdDSAA)

---

## 7. scripts/ Directory

Source: `/home/yoann/veille_auto/scripts/`

| Script | Summary |
|--------|---------|
| setup.sh | Initial install: checks Docker, creates .env from env.template with generated passwords, creates data/ subdirs |
| start.sh | `docker compose up -d`, waits 30 s, prints status |
| stop.sh | `docker compose down` |
| restart.sh | `docker compose restart`, waits 10 s, prints status |
| status.sh | Prints container status + SQL stats from rss_articles table + disk usage + last 5 log lines per service |
| backup.sh | pg_dump to backups/, tars data/n8n, copies .env; prunes files older than 7 days |
| restore.sh | Runs backup.sh first, then `psql < backup.sql`; prompts confirmation |
| logs.sh | `docker compose logs -f --tail=100 [service]`; defaults to n8n |
| rss-sources.sh | Validates rss_sources.json syntax (jq), lists active/inactive sources by category, optionally restarts n8n |
| init.sql | PostgreSQL DDL — creates tables/schema for veille_auto (not a shell script; mounted at container init) |
| RSS-SOURCES.md | Documentation file for RSS source format (not a shell script) |

---

## 8. Data Volumes

### Docker volumes (labeled com.docker.compose.project=veille_auto)
None. veille_auto uses exclusively **bind mounts**, not named Docker volumes.

### Bind-mount paths and sizes
| Path | Size | Notes |
|------|------|-------|
| /home/yoann/veille_auto/data/n8n | 37M | n8n state: workflows, credentials (encrypted), community nodes, event logs |
| /home/yoann/veille_auto/data/postgres | 4.0K | Postgres data dir (sparse, actual data inside container layers) |
| /home/yoann/veille_auto/data/redis | 12K | Redis AOF persistence |
| /home/yoann/veille_auto/data/grafana | 4.0K | Empty (grafana service commented out) |
| /home/yoann/veille_auto/data/prometheus | 4.0K | Empty (prometheus service commented out) |

n8n state lives in `/home/yoann/veille_auto/data/n8n/` (bind-mount of `/home/node/.n8n`). Contains: `config`, `crash.journal`, `n8nEventLog*.log`, `binaryData/`, `git/`, `nodes/`, `ssh/`. Back up this directory before any compose changes.

Community node installed: `n8n-nodes-discord-trigger` (in `data/n8n/nodes/node_modules/`).

---

## 9. Podcast↔veille_auto Naming Collisions

### Container names — no collision
| veille_auto | podcast |
|-------------|---------|
| veille-postgres | podcast-postgres |
| veille-n8n | podcast-n8n |
| veille-redis | podcast-redis |
| veille-webdis | (none) |
| veille-rsshub | (none) |

All container names are unique.

### Internal service DNS hostnames
Both compose files use the bare service names `postgres`, `redis`, `n8n` as internal DNS. These are isolated per network bridge and do not collide as long as the two stacks remain on separate networks.

### Host-bound port conflicts
| Port | veille_auto | podcast |
|------|-------------|---------|
| 5433 | 127.0.0.1:5433→postgres:5432 | 127.0.0.1:${POSTGRES_PORT:-5433}→postgres:5432 |
| 5678 | 127.0.0.1:5678→n8n:5678 | 127.0.0.1:${N8N_PORT:-5678}→n8n:5678 |
| 1200 | 127.0.0.1:1200→rsshub:1200 | (none) |

**Port 5433 and 5678 are bound by veille_auto and would conflict with podcast defaults.** Podcast must use different host ports (POSTGRES_PORT and N8N_PORT must be set to non-conflicting values in podcast/.env before startup).

### Network names
- veille_auto: `veille_auto_veille-network` (bridge)
- podcast: not yet created

No network name collision.

---

## 10. n8n Version

From `docker exec veille-n8n n8n --version`: **2.1.4**

Image tag in compose: `n8nio/n8n:latest` (unpinned) — version reflects whatever was pulled at container creation time.

