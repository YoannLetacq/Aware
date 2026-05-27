"""Redis job queue — BRPOP envelope claim and recovery tick helpers.

Envelope contract (ARCHITECTURE.md §2.2): n8n LPUSHes a JSON object
``{"job_id": "<uuid>", "interaction_id": "<snowflake>"}`` onto list
``podcast:jobs``. The worker BRPOPs, JSON-parses, and returns the dict.
"""

import json
from typing import Any

import redis
import structlog

from app import config, db

logger = structlog.get_logger(__name__)

JOB_LIST_KEY = "podcast:jobs"


class PoisonMessageError(ValueError):
    """Raised when a message popped from the queue cannot be processed.

    Distinguishes malformed envelopes from a BRPOP timeout (which returns None).
    """


class _ClientHolder:
    """Module-scoped lazy holder for the Redis client singleton."""

    instance: redis.Redis | None = None


def _get_redis_client() -> redis.Redis:
    """Lazy-singleton Redis client (one TCP connection per worker process)."""
    if _ClientHolder.instance is None:
        _ClientHolder.instance = redis.Redis(
            host=config.REDIS_HOST,
            port=config.REDIS_PORT,
            db=config.REDIS_DB,
            password=config.REDIS_PASSWORD,
            decode_responses=True,
        )
    return _ClientHolder.instance


def claim_next_job(timeout: int = 30) -> dict[str, Any] | None:
    """Block on BRPOP for *timeout* seconds; return parsed envelope or None.

    Returns None only on BRPOP timeout (empty queue).
    Raises PoisonMessageError for malformed JSON or missing job_id so the
    main loop can distinguish a bad message from a queue-empty condition.
    """
    popped = _get_redis_client().brpop([JOB_LIST_KEY], timeout=timeout)
    if popped is None:
        return None
    _, raw = popped
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("queue_poison_message", raw=raw, error=str(exc))
        db.write_audit(None, "queue_poison_message", {"raw": raw, "error": str(exc)})
        raise PoisonMessageError(
            f"poison message in podcast:jobs: {raw!r}"
        ) from exc
    if not isinstance(envelope, dict) or "job_id" not in envelope:
        logger.error("queue_bad_envelope", envelope=envelope)
        db.write_audit(None, "queue_bad_envelope", {"envelope": envelope})
        raise PoisonMessageError(
            f"poison message in podcast:jobs: {raw!r}"
        )
    return envelope


def recovery_tick() -> list[str]:
    """Return job_ids stuck in 'queued' beyond the recovery window (ARCH §2.2 step 3)."""
    return db.list_recovery_candidates(stale_seconds=30)
