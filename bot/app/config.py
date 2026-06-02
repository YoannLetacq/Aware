"""Environment configuration loader for the Discord bot.

All required variables are fetched via _required(); no real defaults are
allowed (AGENT_CONDUCT §1.4). Optional variables return None via _optional().
Module-level constants are loaded once at import time.
"""

import os


def _required(name: str) -> str:
    """Return the value of environment variable *name* or raise RuntimeError."""
    value = os.getenv(name)
    if value is None or value == "":
        raise RuntimeError(f"missing or empty env var: {name}")
    return value


def _optional(name: str) -> str | None:
    """Return the value of environment variable *name*, or None if missing/empty."""
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return value


# Discord credentials
DISCORD_BOT_TOKEN: str = _required("DISCORD_BOT_TOKEN")
DISCORD_APP_ID: str = _required("DISCORD_APP_ID")
DISCORD_PUBLIC_KEY: str = _required("DISCORD_PUBLIC_KEY")

# Guild ID for slash-command registration; None = global registration
DISCORD_GUILD_ID: str | None = _optional("DISCORD_GUILD_ID")

# Comma-separated Discord user IDs allowed to trigger /podcast; empty = allow all
DISCORD_ALLOWED_AUTHORS: str = _optional("DISCORD_ALLOWED_AUTHORS") or ""

# n8n webhook endpoint for podcast trigger payloads
N8N_WEBHOOK_URL: str = _required("N8N_WEBHOOK_URL")

# Shared HMAC bearer token for bot → n8n communication
WORKER_SHARED_TOKEN: str = _required("WORKER_SHARED_TOKEN")

# Kill switch: env value "1" enables maintenance mode (enforcement deferred to Phase 5)
KILL_SWITCH: bool = _required("KILL_SWITCH") == "1"

# Rate-limit thresholds (enforcement deferred to Phase 5)
RATE_LIMIT_PER_USER_DAY: int = int(_required("RATE_LIMIT_PER_USER_DAY"))
RATE_LIMIT_GLOBAL_DAY: int = int(_required("RATE_LIMIT_GLOBAL_DAY"))

# Path to notebooklm_styles.json inside the bot container.
# Mount ./config:/app/config:ro on the bot service to use the canonical source.
NOTEBOOKLM_STYLES_PATH: str = (
    _optional("NOTEBOOKLM_STYLES_PATH") or "/app/config/notebooklm_styles.json"
)
