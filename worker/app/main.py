"""Worker entrypoint — Redis BRPOP queue listener (Phase 2 + US-004).

The main loop:
1. Runs a recovery tick to surface jobs whose LPUSH was lost (ARCH §2.2).
2. BRPOPs the next envelope from list ``podcast:jobs`` with a 30 s timeout.
3. Drives the job through the full lifecycle:
   gemini_running -> gemini_done -> notebooklm_uploading ->
   notebooklm_generating -> delivered (or failed at any stage).
"""

import json
from typing import Any

import psycopg
import redis
import structlog

from app import db, delivery, gemini, observability, queue, validators
from app.notebooklm import orchestrator

logger = structlog.get_logger(__name__)


def _gemini_stage(job: dict[str, Any]) -> list[dict[str, Any]]:
    """Run Gemini + validators; return the JSON-serialisable source list."""
    envelope = gemini.call_gemini(
        subject=job["subject"],
        mode=job["mode"],
        language_hint=job.get("locale") or "fr",
    )
    validated = validators.sanity_check_sources(envelope.sources)
    return [json.loads(src.model_dump_json()) for src in validated]


def _notebooklm_stage(job: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    """Run the NotebookLM generation stage and persist the result.

    Transitions: notebooklm_uploading -> notebooklm_generating -> delivered.
    On NotebookLMError, transitions to failed and posts a French failure message.
    Delivery is confirmed BEFORE the terminal 'delivered' state: if the Discord
    post fails, the job is marked failed at stage='delivery' rather than reported
    as a false success (RISK_MANAGEMENT §3.1).
    channel_id is read strictly from the stored job dict (RISK_MANAGEMENT §4.1).
    """
    job_id: str = job["id"]
    channel_id: str = job["channel_id"]
    log = logger.bind(job_id=job_id)

    db.update_status(job_id, "notebooklm_uploading")
    db.write_audit(job_id, "notebooklm_uploading", {})
    db.update_status(job_id, "notebooklm_generating")
    db.write_audit(job_id, "notebooklm_generating", {})

    try:
        result = orchestrator.run_generation(job, sources)
    except orchestrator.NotebookLMError as exc:
        log.warning("notebooklm_generation_failed", code=exc.code)
        db.mark_failed(job_id, "notebooklm", exc.code, str(exc))
        db.write_audit(job_id, "failed", {"stage": "notebooklm", "code": exc.code})
        delivery.post_failure(channel_id, "Désolé, la génération a échoué.")
        return

    delivered = delivery.post_success(
        channel_id, result.artifact_path, "Voici ton contenu généré !"
    )
    if not delivered:
        db.mark_failed(
            job_id,
            "delivery",
            "DELIVERY_FAILED",
            f"artifact generated but Discord post failed: {result.artifact_path}",
        )
        db.write_audit(job_id, "failed", {"stage": "delivery", "code": "DELIVERY_FAILED"})
        log.error("delivery_failed_after_generation", artifact_path=result.artifact_path)
        return

    db.mark_delivered(
        job_id,
        result.artifact_path,
        result.artifact_sha256,
        result.artifact_size_bytes,
        result.artifact_duration_s,
    )
    db.write_audit(job_id, "delivered", {
        "artifact_path": result.artifact_path,
        "artifact_sha256": result.artifact_sha256,
        "artifact_size_bytes": result.artifact_size_bytes,
    })
    log.info("job_delivered", artifact_path=result.artifact_path)


def _process_job(job_id: str) -> None:
    """Run a single job through the full lifecycle (gemini + notebooklm) or fail it."""
    log = logger.bind(job_id=job_id)
    job = db.get_job(job_id)
    if job is None:
        log.info("job_skipped_locked_or_missing")
        return

    channel_id = job["channel_id"]
    db.update_status(job_id, "gemini_running", set_started=True)
    db.write_audit(job_id, "gemini_running", {})

    try:
        sources = _gemini_stage(job)
    except validators.SourcesError as exc:
        log.warning("gemini_validation_failed", code=exc.code, error=str(exc))
        db.mark_failed(job_id, "source_validation", exc.code, str(exc))
        db.write_audit(job_id, "failed", {"stage": "source_validation", "code": exc.code})
        delivery.post_failure(
            channel_id,
            "Désolé, je n'ai pas pu trouver assez de sources pertinentes pour ce sujet.",
        )
        return
    except gemini.GeminiError as exc:
        log.warning("gemini_call_failed_final", code=exc.code)
        db.mark_failed(job_id, "gemini", exc.code, exc.code)
        db.write_audit(job_id, "failed", {"stage": "gemini", "code": exc.code})
        delivery.post_failure(
            channel_id,
            "Désolé, le service de curation est temporairement indisponible.",
        )
        return

    db.set_sources(job_id, sources)
    db.update_status(job_id, "gemini_done")
    db.write_audit(job_id, "gemini_done", {"source_count": len(sources)})
    log.info("gemini_done", source_count=len(sources))

    _notebooklm_stage(job, sources)


def _recovery_pass() -> None:
    """Log any jobs flagged by the recovery tick (Phase 2: surface only)."""
    stale = queue.recovery_tick()
    if stale:
        logger.warning("queue_recovery_candidates", job_ids=stale)


def main() -> None:
    """Worker main loop — blocking BRPOP with KeyboardInterrupt-safe exit."""
    observability.configure_logging()
    logger.info("worker_started")
    while True:
        try:
            _recovery_pass()
            envelope = queue.claim_next_job(timeout=30)
            if envelope is None:
                continue
            _process_job(envelope["job_id"])
        except KeyboardInterrupt:
            logger.info("worker_shutdown_keyboard_interrupt")
            break
        except (OSError, ValueError, RuntimeError, redis.RedisError, psycopg.Error) as exc:
            logger.exception("worker_loop_unhandled", error=str(exc))


if __name__ == "__main__":
    main()
