"""Database access layer for podcast.jobs CRUD operations.

Provides synchronous helpers around psycopg for the worker BRPOP loop.
Every call is parameterised; no f-string interpolation into SQL.
"""

import json
from typing import Any

import psycopg
import structlog

from app import config

logger = structlog.get_logger(__name__)


def _dsn() -> str:
    """Build the libpq connection string from config (no plain-text default)."""
    return (
        f"host={config.POSTGRES_HOST} port={config.POSTGRES_PORT} "
        f"dbname={config.POSTGRES_DB} user={config.POSTGRES_USER} "
        f"password={config.POSTGRES_PASSWORD}"
    )


def _get_connection() -> psycopg.Connection:
    """Return a new psycopg connection (caller owns the lifecycle)."""
    return psycopg.connect(_dsn())


def get_job(job_id: str) -> dict[str, Any] | None:
    """Fetch a job row by id with FOR UPDATE SKIP LOCKED inside a transaction.

    Returns the row as a dict keyed by column name, or None if not found
    or already locked by another worker.
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, interaction_id, user_id, channel_id, guild_id, "
                "locale, subject, subject_hash, mode, style, status, attempt, "
                "payload, gemini_sources, started_at, finished_at, created_at "
                "FROM podcast.jobs "
                "WHERE id = %s FOR UPDATE SKIP LOCKED",
                (job_id,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            columns = [desc[0] for desc in cur.description]
            return dict(zip(columns, row))


_RUNNING_STATUSES: frozenset[str] = frozenset({"gemini_running"})
_TERMINAL_STATUSES: frozenset[str] = frozenset({"delivered", "failed"})


def update_status(job_id: str, status: str, set_started: bool = False) -> None:
    """Update job status; auto-set started_at or finished_at based on status.

    *set_started* is retained for explicit callers; passing it as True forces
    started_at = NOW() only when it is not yet set (started_at IS NULL).
    Running-state statuses also trigger that guard automatically.
    Terminal statuses set finished_at unconditionally.
    """
    sql = "UPDATE podcast.jobs SET status = %s"
    params: list[Any] = [status]
    if set_started or status in _RUNNING_STATUSES:
        sql += ", started_at = COALESCE(started_at, NOW())"
    if status in _TERMINAL_STATUSES:
        sql += ", finished_at = NOW()"
    sql += " WHERE id = %s"
    params.append(job_id)
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, tuple(params))
    logger.info("db_update_status", job_id=job_id, status=status)


def set_sources(job_id: str, sources: list[dict[str, Any]]) -> None:
    """Persist validated Gemini sources to podcast.jobs.gemini_sources (JSONB)."""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE podcast.jobs SET gemini_sources = %s::jsonb WHERE id = %s",
                (json.dumps(sources), job_id),
            )
    logger.info("db_set_sources", job_id=job_id, source_count=len(sources))


def mark_failed(job_id: str, stage: str, code: str, message: str) -> None:
    """Transition job to failed terminal state with error context."""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE podcast.jobs SET status = 'failed', finished_at = NOW(), "
                "error_stage = %s, error_code = %s, error_message = %s "
                "WHERE id = %s",
                (stage, code, message[:500], job_id),
            )
    logger.info(
        "db_mark_failed", job_id=job_id, stage=stage, code=code,
    )


def write_audit(job_id: str | None, event: str, payload: dict[str, Any]) -> None:
    """Insert an audit_log row for status transitions and notable events."""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO podcast.audit_log (job_id, event, payload) "
                "VALUES (%s, %s, %s::jsonb)",
                (job_id, event, json.dumps(payload)),
            )


def list_recovery_candidates(stale_seconds: int = 30) -> list[str]:
    """Return job_ids in 'queued' status older than *stale_seconds* with no start time."""
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id::text FROM podcast.jobs "
                "WHERE status = 'queued' "
                "AND started_at IS NULL "
                "AND created_at < NOW() - make_interval(secs => %s)",
                (int(stale_seconds),),
            )
            return [row[0] for row in cur.fetchall()]


def mark_delivered(
    job_id: str,
    artifact_path: str,
    artifact_sha256: str,
    artifact_size_bytes: int,
    artifact_duration_s: float | None,
) -> None:
    """Transition job to delivered terminal state and record artifact metadata.

    Executes a single parameterised UPDATE setting status='delivered',
    finished_at=NOW(), and the four artifact columns.  All values are passed
    as %s parameters — no f-string or concatenation into SQL (CWE-89).
    """
    with _get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE podcast.jobs "
                "SET status = 'delivered', finished_at = NOW(), "
                "artifact_path = %s, artifact_sha256 = %s, "
                "artifact_size_bytes = %s, artifact_duration_s = %s "
                "WHERE id = %s",
                (
                    artifact_path,
                    artifact_sha256,
                    artifact_size_bytes,
                    artifact_duration_s,
                    job_id,
                ),
            )
    logger.info("db_mark_delivered", job_id=job_id)
