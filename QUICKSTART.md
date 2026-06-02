# QUICKSTART — Podcast Pipeline First-Run Guide

Operator guide for standing up the pipeline from scratch.

## Prerequisites

- Docker 24+ and Docker Compose v2 installed
- Git
- A Discord application with a bot token (`MESSAGE CONTENT` intent enabled,
  `applications.commands` scope granted in your guild)
- A Gemini API key from https://aistudio.google.com/app/apikey
- A dedicated Google Workspace burner account for NotebookLM
  (do NOT use your personal Google account — see § "Google burner session seeding" below)
- NotebookLM plan supporting Video Overview if you plan to use `mode:video`

## Step 1 — Clone and run setup

```bash
git clone <repo-url> podcast
cd podcast
chmod +x scripts/*.sh
./scripts/setup.sh
```

`setup.sh` generates `.env` from `env.template` with random passwords for
`POSTGRES_PASSWORD`, `N8N_ENCRYPTION_KEY`, and `WORKER_SHARED_TOKEN`.
It also creates required directories and sets permissions on `data/session/`.

## Step 2 — Edit .env

Open `.env` and replace **every** `YOUR_*` placeholder:

```
DISCORD_BOT_TOKEN      Discord Developer Portal → Bot → Token
DISCORD_APP_ID         Discord Developer Portal → General Information
DISCORD_PUBLIC_KEY     Discord Developer Portal → General Information
DISCORD_GUILD_ID       Right-click your server → Copy Server ID (developer mode)
OPERATOR_DISCORD_WEBHOOK  Webhook URL for operator alerts (CAPTCHA, session expiry)
GEMINI_API_KEY         https://aistudio.google.com/app/apikey
GEMINI_MODEL           e.g. gemini-2.5-pro
GOOGLE_BURNER_EMAIL    Email of the dedicated Workspace account
GOOGLE_BURNER_PASSWORD App-password preferred if 2FA is enabled
BACKUP_PASSPHRASE      Any strong passphrase for encrypted session backups
```

Leave `KILL_SWITCH=0`, `RATE_LIMIT_PER_USER_DAY=3`, `RATE_LIMIT_GLOBAL_DAY=20`
at their defaults unless you need to change them.

## Step 3 — Start the stack

```bash
./scripts/start.sh
./scripts/status.sh
```

All five services should show `healthy` within ~60 seconds.

## Step 4 — n8n setup wizard

1. Open http://localhost:5678 in your browser.
2. Create the owner account (email + password — these are NOT in `.env`).
3. Import `workflows/pipeline.json` via Settings → Workflows → Import.
4. Wire the Postgres credential (use values from `.env`).
5. Confirm the webhook URL matches `WEBHOOK_URL` in `.env`.

See Phase 1 docs for slash-command registration in your Discord guild.

## Google burner session seeding (Phase 3)

**This step requires a headed browser and operator presence. It cannot be automated.**

Once Phase 3 is implemented, run:

```bash
./scripts/seed-google-session.sh
```

This launches a headed Chromium window. Log in to the burner Google account,
complete any 2FA challenge, then the script saves `storageState.json` to
`data/session/storageState.json` (chmod 600, owned by the worker UID).

**Re-seeding required when:**
- The worker logs `SESSION_EXPIRED` or `CAPTCHA_REQUIRED`.
- You rotate the burner account password.
- Google invalidates the session (typically every few weeks on Workspace accounts).

Encrypted backup of the session file is created automatically by `./scripts/backup.sh`.
To restore: `./scripts/restore.sh --session-only`.

## Verification

```bash
./scripts/status.sh     # all services healthy, podcast.jobs returns 0 rows
```

Register the `/podcast` slash command (Phase 1) and run a test invocation:

```
/podcast subject:"Les modèles de langage open-source en 2025" mode:podcast
```

Expected: ephemeral French acknowledgement within 2 seconds, job row appears in
`podcast.jobs` with `status='queued'`.
