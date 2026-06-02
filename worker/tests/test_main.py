"""Tests for app.main — _process_job lifecycle (US-005).

Covers the full job state machine from queued through delivered, plus the
three failure branches: gemini error, validation error, NotebookLM error,
and the job-not-found (None) early-exit.

All external dependencies (db, gemini, delivery, orchestrator) are
monkeypatched; no live Postgres, Redis, Gemini, or Playwright connections
are made.  Style follows test_queue.py: try/except ImportError guard,
pytestmark skipif, monkeypatch + MagicMock.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import guard — ImportError acceptable until executor lands.
# ---------------------------------------------------------------------------
try:
    import app.main as _main_module
    from app.main import _process_job
    from app.notebooklm.orchestrator import GenerationResult, NotebookLMError

    _IMPL_AVAILABLE = True
except ImportError:
    _IMPL_AVAILABLE = False
    _main_module = None  # type: ignore[assignment]
    _process_job = None  # type: ignore[assignment]
    GenerationResult = None  # type: ignore[assignment]
    NotebookLMError = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(
    not _IMPL_AVAILABLE,
    reason="app.main not yet implemented",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_JOB_ID = "job-uuid-001"
_CHANNEL_ID = "ch-123"


def _make_job(job_id: str = _JOB_ID, channel_id: str = _CHANNEL_ID) -> dict[str, Any]:
    """Return a minimal valid job dict as returned by db.get_job."""
    return {
        "id": job_id,
        "job_id": job_id,
        "channel_id": channel_id,
        "subject": "L'IA générative",
        "mode": "podcast",
        "locale": "fr",
        "style": None,
        "user_id": "user-1",
    }


def _make_generation_result():
    """Return a GenerationResult-like MagicMock with the required attributes."""
    return GenerationResult(
        artifact_path="/data/artifacts/out.mp3",
        artifact_sha256="abc123def456",
        artifact_size_bytes=4096,
        artifact_duration_s=120.5,
    )


# ---------------------------------------------------------------------------
# (a) Happy path — delivered
# ---------------------------------------------------------------------------


def test_happy_path_delivered(monkeypatch: pytest.MonkeyPatch) -> None:
    """_process_job drives gemini -> notebooklm stages and ends at delivered."""
    job = _make_job()
    result = _make_generation_result()

    mock_db = MagicMock()
    mock_db.get_job.return_value = job
    mock_gemini = MagicMock()
    mock_validators = MagicMock()
    mock_delivery = MagicMock()
    mock_delivery.post_success.return_value = True
    mock_orchestrator = MagicMock()
    mock_orchestrator.run_generation.return_value = result

    monkeypatch.setattr(_main_module, "db", mock_db)
    monkeypatch.setattr(_main_module, "gemini", mock_gemini)
    monkeypatch.setattr(_main_module, "validators", mock_validators)
    monkeypatch.setattr(_main_module, "delivery", mock_delivery)
    monkeypatch.setattr(_main_module, "orchestrator", mock_orchestrator)

    _process_job(_JOB_ID)

    # Status transitions must occur in order.
    status_calls = [c for c in mock_db.update_status.call_args_list]
    statuses = [c[0][1] for c in status_calls]
    assert "gemini_running" in statuses
    assert "gemini_done" in statuses
    assert "notebooklm_uploading" in statuses
    assert "notebooklm_generating" in statuses

    # gemini_running must precede notebooklm_uploading.
    assert statuses.index("gemini_running") < statuses.index("notebooklm_uploading")
    assert statuses.index("notebooklm_uploading") < statuses.index("notebooklm_generating")

    # mark_delivered called exactly once with artifact data.
    mock_db.mark_delivered.assert_called_once_with(
        _JOB_ID,
        result.artifact_path,
        result.artifact_sha256,
        result.artifact_size_bytes,
        result.artifact_duration_s,
    )

    # delivery.post_success called exactly once with job's channel_id.
    mock_delivery.post_success.assert_called_once()
    call_channel_id = mock_delivery.post_success.call_args[0][0]
    assert call_channel_id == _CHANNEL_ID

    # No failure delivery.
    mock_delivery.post_failure.assert_not_called()


def test_happy_path_audit_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """Audit rows are written for all stage transitions in the happy path."""
    job = _make_job()
    result = _make_generation_result()

    mock_db = MagicMock()
    mock_db.get_job.return_value = job
    mock_orchestrator = MagicMock()
    mock_orchestrator.run_generation.return_value = result

    monkeypatch.setattr(_main_module, "db", mock_db)
    monkeypatch.setattr(_main_module, "gemini", MagicMock())
    monkeypatch.setattr(_main_module, "validators", MagicMock())
    monkeypatch.setattr(_main_module, "delivery", MagicMock())
    monkeypatch.setattr(_main_module, "orchestrator", mock_orchestrator)

    _process_job(_JOB_ID)

    audit_events = [c[0][1] for c in mock_db.write_audit.call_args_list]
    assert "gemini_running" in audit_events
    assert "gemini_done" in audit_events
    assert "notebooklm_uploading" in audit_events
    assert "notebooklm_generating" in audit_events
    assert "delivered" in audit_events


def test_happy_path_run_generation_receives_job_and_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_generation is called with the full job dict and the source list."""
    job = _make_job()
    result = _make_generation_result()
    fake_sources = [{"url": "https://example.com", "title": "Test"}]

    mock_db = MagicMock()
    mock_db.get_job.return_value = job
    mock_gemini = MagicMock()
    mock_validators = MagicMock()
    mock_validators.sanity_check_sources.return_value = []
    mock_orchestrator = MagicMock()
    mock_orchestrator.run_generation.return_value = result

    # _gemini_stage returns sources via validators; patch at a higher level.
    with patch.object(_main_module, "_gemini_stage", return_value=fake_sources):
        monkeypatch.setattr(_main_module, "db", mock_db)
        monkeypatch.setattr(_main_module, "gemini", mock_gemini)
        monkeypatch.setattr(_main_module, "validators", mock_validators)
        monkeypatch.setattr(_main_module, "delivery", MagicMock())
        monkeypatch.setattr(_main_module, "orchestrator", mock_orchestrator)

        _process_job(_JOB_ID)

    mock_orchestrator.run_generation.assert_called_once_with(job, fake_sources)


# ---------------------------------------------------------------------------
# (a') Delivery failure after successful generation — must NOT mark delivered
# ---------------------------------------------------------------------------


def test_delivery_failure_marks_failed_not_delivered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When post_success returns False, the job is failed at stage=delivery.

    The artifact was generated but the Discord post failed; the job must NOT
    reach the terminal 'delivered' state (RISK_MANAGEMENT §3.1 — no false
    success). mark_failed(stage='delivery') is called, mark_delivered is not,
    and no 'delivered' audit row is written.
    """
    job = _make_job()
    result = _make_generation_result()

    mock_db = MagicMock()
    mock_db.get_job.return_value = job
    mock_delivery = MagicMock()
    mock_delivery.post_success.return_value = False
    mock_orchestrator = MagicMock()
    mock_orchestrator.run_generation.return_value = result

    monkeypatch.setattr(_main_module, "db", mock_db)
    monkeypatch.setattr(_main_module, "gemini", MagicMock())
    monkeypatch.setattr(_main_module, "validators", MagicMock())
    monkeypatch.setattr(_main_module, "delivery", mock_delivery)
    monkeypatch.setattr(_main_module, "orchestrator", mock_orchestrator)

    _process_job(_JOB_ID)

    # Not delivered.
    mock_db.mark_delivered.assert_not_called()

    # Failed at stage='delivery'.
    mock_db.mark_failed.assert_called_once()
    failed_args = mock_db.mark_failed.call_args[0]
    assert failed_args[0] == _JOB_ID
    assert failed_args[1] == "delivery"

    # No 'delivered' audit transition.
    audit_events = [c[0][1] for c in mock_db.write_audit.call_args_list]
    assert "delivered" not in audit_events

    # post_success was attempted with the stored channel_id (IDOR scope).
    mock_delivery.post_success.assert_called_once()
    assert mock_delivery.post_success.call_args[0][0] == _CHANNEL_ID


# ---------------------------------------------------------------------------
# (b) Gemini failure — GeminiError
# ---------------------------------------------------------------------------


def test_gemini_error_marks_failed_no_notebooklm(monkeypatch: pytest.MonkeyPatch) -> None:
    """A GeminiError transitions the job to failed; notebooklm stage is never entered."""
    from app import gemini as real_gemini
    from app import validators as real_validators

    job = _make_job()

    mock_db = MagicMock()
    mock_db.get_job.return_value = job
    exc = real_gemini.GeminiError("Gemini service down", code="GEMINI_DOWN")
    mock_orchestrator = MagicMock()
    mock_delivery = MagicMock()

    mock_gemini = MagicMock()
    mock_gemini.GeminiError = real_gemini.GeminiError
    mock_validators = MagicMock()
    mock_validators.SourcesError = real_validators.SourcesError

    with patch.object(_main_module, "_gemini_stage", side_effect=exc):
        monkeypatch.setattr(_main_module, "db", mock_db)
        monkeypatch.setattr(_main_module, "gemini", mock_gemini)
        monkeypatch.setattr(_main_module, "validators", mock_validators)
        monkeypatch.setattr(_main_module, "delivery", mock_delivery)
        monkeypatch.setattr(_main_module, "orchestrator", mock_orchestrator)

        _process_job(_JOB_ID)

    mock_db.mark_failed.assert_called_once()
    call_stage = mock_db.mark_failed.call_args[0][1]
    assert call_stage in ("gemini", "source_validation", "gemini_call")

    # notebooklm stage never started.
    status_calls = [c[0][1] for c in mock_db.update_status.call_args_list]
    assert "notebooklm_uploading" not in status_calls
    assert "notebooklm_generating" not in status_calls
    mock_orchestrator.run_generation.assert_not_called()

    # Failure message posted.
    mock_delivery.post_failure.assert_called_once()
    assert mock_delivery.post_failure.call_args[0][0] == _CHANNEL_ID


# ---------------------------------------------------------------------------
# (b) Gemini failure — SourcesError
# ---------------------------------------------------------------------------


def test_sources_error_marks_failed_no_notebooklm(monkeypatch: pytest.MonkeyPatch) -> None:
    """A SourcesError transitions the job to failed; notebooklm stage is never entered."""
    from app import gemini as real_gemini
    from app import validators as real_validators

    job = _make_job()

    mock_db = MagicMock()
    mock_db.get_job.return_value = job
    exc = real_validators.SourcesError("TOO_FEW_SOURCES", "not enough")
    mock_orchestrator = MagicMock()
    mock_delivery = MagicMock()

    mock_gemini = MagicMock()
    mock_gemini.GeminiError = real_gemini.GeminiError
    mock_validators = MagicMock()
    mock_validators.SourcesError = real_validators.SourcesError

    with patch.object(_main_module, "_gemini_stage", side_effect=exc):
        monkeypatch.setattr(_main_module, "db", mock_db)
        monkeypatch.setattr(_main_module, "gemini", mock_gemini)
        monkeypatch.setattr(_main_module, "validators", mock_validators)
        monkeypatch.setattr(_main_module, "delivery", mock_delivery)
        monkeypatch.setattr(_main_module, "orchestrator", mock_orchestrator)

        _process_job(_JOB_ID)

    mock_db.mark_failed.assert_called_once()
    status_calls = [c[0][1] for c in mock_db.update_status.call_args_list]
    assert "notebooklm_uploading" not in status_calls
    mock_orchestrator.run_generation.assert_not_called()
    mock_delivery.post_failure.assert_called_once()
    assert mock_delivery.post_failure.call_args[0][0] == _CHANNEL_ID


# ---------------------------------------------------------------------------
# (c) NotebookLM failure — NotebookLMError
# ---------------------------------------------------------------------------


def test_notebooklm_error_marks_failed_not_delivered(monkeypatch: pytest.MonkeyPatch) -> None:
    """A NotebookLMError marks the job failed at stage=notebooklm; not delivered."""
    job = _make_job()
    fake_sources = [{"url": "https://example.com"}]

    mock_db = MagicMock()
    mock_db.get_job.return_value = job
    mock_orchestrator = MagicMock()
    mock_orchestrator.NotebookLMError = NotebookLMError
    exc = NotebookLMError("GENERATION_TIMEOUT", "timed out")
    mock_orchestrator.run_generation.side_effect = exc
    mock_delivery = MagicMock()

    with patch.object(_main_module, "_gemini_stage", return_value=fake_sources):
        monkeypatch.setattr(_main_module, "db", mock_db)
        monkeypatch.setattr(_main_module, "gemini", MagicMock())
        monkeypatch.setattr(_main_module, "validators", MagicMock())
        monkeypatch.setattr(_main_module, "delivery", mock_delivery)
        monkeypatch.setattr(_main_module, "orchestrator", mock_orchestrator)

        _process_job(_JOB_ID)

    # mark_failed called with stage=notebooklm and the error code.
    mock_db.mark_failed.assert_called_once()
    failed_args = mock_db.mark_failed.call_args[0]
    assert failed_args[0] == _JOB_ID
    assert failed_args[1] == "notebooklm"
    assert failed_args[2] == "GENERATION_TIMEOUT"

    # Not delivered.
    mock_db.mark_delivered.assert_not_called()

    # Failure delivery posted to correct channel.
    mock_delivery.post_failure.assert_called_once()
    assert mock_delivery.post_failure.call_args[0][0] == _CHANNEL_ID

    # Success delivery not posted.
    mock_delivery.post_success.assert_not_called()


def test_notebooklm_error_audit_row_written(monkeypatch: pytest.MonkeyPatch) -> None:
    """A NotebookLMError writes a 'failed' audit row with stage=notebooklm."""
    job = _make_job()
    fake_sources = [{"url": "https://example.com"}]

    mock_db = MagicMock()
    mock_db.get_job.return_value = job
    mock_orchestrator = MagicMock()
    mock_orchestrator.NotebookLMError = NotebookLMError
    mock_orchestrator.run_generation.side_effect = NotebookLMError("SESSION_EXPIRED", "expired")

    with patch.object(_main_module, "_gemini_stage", return_value=fake_sources):
        monkeypatch.setattr(_main_module, "db", mock_db)
        monkeypatch.setattr(_main_module, "gemini", MagicMock())
        monkeypatch.setattr(_main_module, "validators", MagicMock())
        monkeypatch.setattr(_main_module, "delivery", MagicMock())
        monkeypatch.setattr(_main_module, "orchestrator", mock_orchestrator)

        _process_job(_JOB_ID)

    audit_events = [c[0][1] for c in mock_db.write_audit.call_args_list]
    assert "failed" in audit_events
    failed_payload = [
        c[0][2] for c in mock_db.write_audit.call_args_list if c[0][1] == "failed"
    ]
    assert any(p.get("stage") == "notebooklm" for p in failed_payload)


# ---------------------------------------------------------------------------
# (d) db.get_job returns None — job skipped
# ---------------------------------------------------------------------------


def test_job_none_skips_all_transitions(monkeypatch: pytest.MonkeyPatch) -> None:
    """When db.get_job returns None, no status transitions or deliveries occur."""
    mock_db = MagicMock()
    mock_db.get_job.return_value = None
    mock_delivery = MagicMock()
    mock_orchestrator = MagicMock()

    monkeypatch.setattr(_main_module, "db", mock_db)
    monkeypatch.setattr(_main_module, "gemini", MagicMock())
    monkeypatch.setattr(_main_module, "validators", MagicMock())
    monkeypatch.setattr(_main_module, "delivery", mock_delivery)
    monkeypatch.setattr(_main_module, "orchestrator", mock_orchestrator)

    _process_job(_JOB_ID)

    mock_db.update_status.assert_not_called()
    mock_db.mark_failed.assert_not_called()
    mock_db.mark_delivered.assert_not_called()
    mock_delivery.post_failure.assert_not_called()
    mock_delivery.post_success.assert_not_called()
    mock_orchestrator.run_generation.assert_not_called()


# ---------------------------------------------------------------------------
# Delivery scoping — channel_id always from the stored job (IDOR)
# ---------------------------------------------------------------------------


def test_delivery_channel_id_from_job_not_inbound(monkeypatch: pytest.MonkeyPatch) -> None:
    """post_success and post_failure always use the channel_id from the stored job."""
    stored_channel = "stored-channel-999"
    job = _make_job(channel_id=stored_channel)

    mock_db = MagicMock()
    mock_db.get_job.return_value = job
    mock_orchestrator = MagicMock()
    mock_orchestrator.NotebookLMError = NotebookLMError
    mock_orchestrator.run_generation.side_effect = NotebookLMError("NOT_IMPLEMENTED", "x")
    mock_delivery = MagicMock()

    with patch.object(_main_module, "_gemini_stage", return_value=[]):
        monkeypatch.setattr(_main_module, "db", mock_db)
        monkeypatch.setattr(_main_module, "gemini", MagicMock())
        monkeypatch.setattr(_main_module, "validators", MagicMock())
        monkeypatch.setattr(_main_module, "delivery", mock_delivery)
        monkeypatch.setattr(_main_module, "orchestrator", mock_orchestrator)

        _process_job(_JOB_ID)

    mock_delivery.post_failure.assert_called_once()
    assert mock_delivery.post_failure.call_args[0][0] == stored_channel
