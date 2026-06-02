#!/usr/bin/env bash
# ==========================================================================
# SEED-GOOGLE-SESSION — Operator runbook for capturing a Google/NotebookLM
#                       authenticated session into data/session/storageState.json.
#
# This script is documentation only. It echoes step-by-step instructions
# and exits 0. It never automates login (credentials must be entered by the
# operator interactively).
#
# Run this once on initial setup and whenever Google forces re-authentication.
#
# Usage: ./scripts/seed-google-session.sh
# ==========================================================================

set -euo pipefail

# --------------------------------------------------------------------------
# Color helpers
# --------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "=========================================="
echo " PODCAST PIPELINE — SEED GOOGLE SESSION"
echo "=========================================="
echo ""

cat <<'EOF'
RUNBOOK: Capture a NotebookLM authenticated session state
==========================================================

PURPOSE
-------
Playwright browser-worker authenticates to notebooklm.google.com using a
stored session (storageState.json). This runbook produces that file by
running an interactive Playwright codegen session under the operator's own
display, logging in with the designated burner Google Workspace account,
and dumping the resulting browser context state.

PREREQUISITES
-------------
1. A burner Google Workspace account (not a personal account).
   - Email and password stored in .env as GOOGLE_BURNER_EMAIL /
     GOOGLE_BURNER_PASSWORD.
   - 2FA configured; TOTP seed stored in .env as TOTP_SEED.
2. A host with a graphical display (X11 or Xvfb). Options:
   a. Local Linux/macOS desktop — run directly on host.
   b. Headless server — start a virtual display first:
        Xvfb :99 -screen 0 1280x1024x24 &
        export DISPLAY=:99
3. Docker installed (for the container path below).

OPTION A — Run Playwright on the host directly
-----------------------------------------------
  pip install playwright
  playwright install chromium
  python3 - <<'PYEOF'
  import asyncio
  from playwright.async_api import async_playwright

  async def main():
      async with async_playwright() as p:
          browser = await p.chromium.launch(headless=False)
          context = await browser.new_context()
          page = await context.new_page()
          await page.goto("https://notebooklm.google.com")
          # ----------------------------------------------------------------
          # ACTION: Log in with the burner Workspace account + 2FA.
          # Wait until you are on the NotebookLM home page, then run the
          # next line in a Python REPL or uncomment and continue the script.
          # ----------------------------------------------------------------
          input("Press ENTER after completing login in the browser window...")
          await context.storage_state(path="data/session/storageState.json")
          await browser.close()
          print("Session saved.")

  asyncio.run(main())
  PYEOF

OPTION B — Run inside the official Playwright Docker image
-----------------------------------------------------------
  docker run --rm -it \
    --net=host \
    -e DISPLAY="${DISPLAY:-:0}" \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v "$(pwd)/data/session:/app/session" \
    mcr.microsoft.com/playwright/python:v1.50.0-noble bash

  # Inside the container:
  python3 - <<'PYEOF'
  import asyncio
  from playwright.async_api import async_playwright

  async def main():
      async with async_playwright() as p:
          browser = await p.chromium.launch(headless=False)
          context = await browser.new_context()
          page = await context.new_page()
          await page.goto("https://notebooklm.google.com")
          # ACTION: complete login + 2FA interactively in the browser window.
          input("Press ENTER after completing login...")
          await context.storage_state(path="/app/session/storageState.json")
          await browser.close()
          print("Session saved to /app/session/storageState.json")

  asyncio.run(main())
  PYEOF

POST-CAPTURE VERIFICATION
--------------------------
From the project root on the host:

  ls -la data/session/storageState.json

Expected output (permissions must be exactly -rw-------):
  -rw------- 1 <user> <group> <size> <date> data/session/storageState.json

If permissions are wrong, fix them:
  chmod 600 data/session/storageState.json
  chmod 700 data/session/

ROTATION
--------
Google sessions expire after a period of inactivity or when Google forces
re-authentication (CAPTCHA, suspicious-login challenge, etc.).

Signs of expiry:
  - Worker logs show SESSION_EXPIRED error code.
  - Operator receives a Discord DM via OPERATOR_DISCORD_WEBHOOK.

When expiry is detected: re-run this runbook to capture a fresh session,
then restart the worker:
  docker compose restart worker

SECURITY NOTES
--------------
- storageState.json is equivalent to a session cookie. Treat it as a
  secret: never commit it, never log its contents.
- The data/session/ directory is gitignored and mounted read-write only
  in the worker service (see docker-compose.yml).
- Encrypted backups are created by backup.sh using BACKUP_PASSPHRASE.

EOF

echo -e "${GREEN}[OK] Runbook displayed. No automated action taken.${NC}"
echo ""
exit 0
