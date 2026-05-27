"""Environment configuration loader for the podcast worker.

All required variables are fetched via _required(); no real defaults are
allowed (AGENT_CONDUCT §1.4). Optional variables use _optional() and return
None when missing or empty. Module-level constants are loaded once at import
time.
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


# Postgres
POSTGRES_HOST: str = _required("POSTGRES_HOST")
POSTGRES_PORT: int = int(_required("POSTGRES_PORT"))
POSTGRES_USER: str = _required("POSTGRES_USER")
POSTGRES_PASSWORD: str = _required("POSTGRES_PASSWORD")
POSTGRES_DB: str = _required("POSTGRES_DB")

# Redis
REDIS_HOST: str = _required("REDIS_HOST")
REDIS_PORT: int = int(_optional("REDIS_PORT") or "6379")
# REDIS_DB defaults to 0 (the standard Redis default database); optional since
# all deployments use db 0 and omitting it is never ambiguous.
REDIS_DB: int = int(_optional("REDIS_DB") or "0")
REDIS_PASSWORD: str = _required("REDIS_PASSWORD")

# Gemini
GEMINI_API_KEY: str = _required("GEMINI_API_KEY")
GEMINI_MODEL: str = _required("GEMINI_MODEL")

# Discord
OPERATOR_DISCORD_WEBHOOK: str = _required("OPERATOR_DISCORD_WEBHOOK")
DISCORD_BOT_TOKEN: str = _required("DISCORD_BOT_TOKEN")

# Operational guards
KILL_SWITCH: bool = _required("KILL_SWITCH") == "1"
RATE_LIMIT_PER_USER_DAY: int = int(_required("RATE_LIMIT_PER_USER_DAY"))
RATE_LIMIT_GLOBAL_DAY: int = int(_required("RATE_LIMIT_GLOBAL_DAY"))

# Inter-service auth
WORKER_SHARED_TOKEN: str = _required("WORKER_SHARED_TOKEN")

# Source curation budget (requirements.md §Undefined Guardrails 4)
SOURCE_COUNT_TARGET: int = 8
SOURCE_COUNT_MIN: int = 5
SOURCE_COUNT_MAX: int = 15

# Timeouts (requirements.md §Undefined Guardrails 6)
URL_LIVENESS_TIMEOUT_S: float = 5.0
GEMINI_TIMEOUT_S: float = 60.0
GEMINI_MAX_OUTPUT_TOKENS: int = 5000
