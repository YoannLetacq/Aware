"""Tests for app.db — podcast.jobs CRUD operations.

Uses a psycopg cursor mock (no Docker / testcontainers required for unit layer).
The _FakeConnection / _FakeCursor fixtures are declared in conftest.py.
Each test verifies one behavior: the SQL query shape, parameter binding, or
state-machine side-effects enforced by the db module.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Import impl — ImportError acceptable until executor lands.
# ---------------------------------------------------------------------------
try:
    import app.db as _db_module
    from app.db import (
        get_job,
        mark_delivered,
        mark_failed,
        set_sources,
        update_status,
        write_audit,
    )
    _IMPL_AVAILABLE = True
except ImportError:
    _IMPL_AVAILABLE = False
    get_job = None  # type: ignore[assignment]
    mark_delivered = None  # type: ignore[assignment]
    mark_failed = None  # type: ignore[assignment]
    set_sources = None  # type: ignore[assignment]
    update_status = None  # type: ignore[assignment]
    write_audit = None  # type: ignore[assignment]
    _db_module = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(
    not _IMPL_AVAILABLE,
    reason="app.db not yet implemented",
)

_JOB_ID = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _any_query_contains(cursor_instance: Any, *keywords: str) -> bool:
    """Return True if any executed query contains all the given keywords."""
    for query, _ in cursor_instance.executed:
        if all(k.upper() in query.upper() for k in keywords):
            return True
    return False


# ---------------------------------------------------------------------------
# update_status — started_at set on first transition
# ---------------------------------------------------------------------------

def test_update_status_first_transition_sets_started_at(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """update_status sets started_at when transitioning to gemini_running."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    update_status(_JOB_ID, "gemini_running")

    cur = postgres_mock.cursor_instance
    assert cur.executed, "Expected at least one SQL call"
    # started_at must appear in the UPDATE when status is a running state.
    assert _any_query_contains(cur, "started_at") or _any_query_contains(
        cur, "gemini_running"
    ), "Expected started_at or status transition in query"


def test_update_status_queues_parameterised_query(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """update_status issues a parameterised UPDATE (no f-string interpolation)."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    update_status(_JOB_ID, "gemini_done")

    cur = postgres_mock.cursor_instance
    assert cur.executed
    query, params = cur.executed[-1]
    # The job_id must appear in params, not hard-coded into the SQL string.
    assert _JOB_ID not in query, (
        "job_id must be passed as a parameter, not interpolated into SQL"
    )
    assert any(_JOB_ID in str(p) for p in params), (
        "job_id must be in the query parameters"
    )


# ---------------------------------------------------------------------------
# update_status — finished_at set on terminal states
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("terminal_status", ["delivered", "failed"])
def test_update_status_terminal_sets_finished_at(
    terminal_status: str,
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """update_status sets finished_at when transitioning to a terminal status."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    update_status(_JOB_ID, terminal_status)

    cur = postgres_mock.cursor_instance
    assert _any_query_contains(cur, "finished_at") or _any_query_contains(
        cur, terminal_status
    ), f"Expected finished_at or {terminal_status} in query"


# ---------------------------------------------------------------------------
# set_sources — jsonb serialisation
# ---------------------------------------------------------------------------

def test_set_sources_jsonb_serialization(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
    sample_sources_data: list[dict],
) -> None:
    """set_sources serialises the sources list as JSON in a parameterised query."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    set_sources(_JOB_ID, sample_sources_data)

    cur = postgres_mock.cursor_instance
    assert cur.executed, "Expected at least one SQL call from set_sources"
    # The sources must be passed as a parameter (JSON string or list), not
    # interpolated into the query string.
    for query, params in cur.executed:
        if "gemini_sources" in query.lower() or "sources" in query.lower():
            # Params must contain something serialisable to JSON.
            assert params, "Expected non-empty params for set_sources query"
            break
    else:
        pytest.fail("No query referencing sources found in executed SQL")


def test_set_sources_parameterised_not_interpolated(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
    sample_sources_data: list[dict],
) -> None:
    """set_sources must not interpolate the sources JSON into the SQL string."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    set_sources(_JOB_ID, sample_sources_data)

    cur = postgres_mock.cursor_instance
    for query, _ in cur.executed:
        # Raw URL strings from fixture should not appear in the SQL itself.
        assert "arxiv.org" not in query, (
            "Source data must be parameterised, not interpolated into SQL"
        )


# ---------------------------------------------------------------------------
# mark_failed — error columns persisted
# ---------------------------------------------------------------------------

def test_mark_failed_writes_error_columns(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mark_failed persists stage, code, and message as query parameters."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    mark_failed(
        _JOB_ID,
        stage="gemini",
        code="EMPTY_RESPONSE",
        message="Gemini returned an empty response body.",
    )

    cur = postgres_mock.cursor_instance
    assert cur.executed, "Expected at least one SQL call from mark_failed"
    all_params: list[Any] = []
    for _, params in cur.executed:
        all_params.extend(str(p) for p in params)
    params_str = " ".join(all_params)
    assert "gemini" in params_str, "stage 'gemini' must appear in parameters"
    assert "EMPTY_RESPONSE" in params_str, "code must appear in parameters"
    assert "Gemini returned" in params_str, "message must appear in parameters"


def test_mark_failed_sets_status_failed(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mark_failed transitions the job to status='failed'."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    mark_failed(_JOB_ID, stage="source_validation", code="INSUFFICIENT_COUNT",
                message="Only 3 live sources remained.")

    cur = postgres_mock.cursor_instance
    assert cur.executed
    all_params: list[Any] = []
    for _, params in cur.executed:
        all_params.extend(str(p) for p in params)
    params_str = " ".join(all_params)
    assert "failed" in params_str or _any_query_contains(cur, "failed"), (
        "mark_failed must set status to 'failed'"
    )


# ---------------------------------------------------------------------------
# write_audit — row appended
# ---------------------------------------------------------------------------

def test_write_audit_appends_row(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """write_audit executes an INSERT INTO podcast.audit_log."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    write_audit(
        _JOB_ID,
        event="status_transition",
        payload={"from": "queued", "to": "gemini_running"},
    )

    cur = postgres_mock.cursor_instance
    assert cur.executed, "Expected at least one SQL call from write_audit"
    assert _any_query_contains(cur, "INSERT") or _any_query_contains(
        cur, "audit"
    ), "Expected INSERT into audit_log"


def test_write_audit_parameterised_not_interpolated(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """write_audit must not interpolate job_id or payload into the SQL string."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    write_audit(_JOB_ID, event="test_event", payload={"key": "value"})

    cur = postgres_mock.cursor_instance
    for query, _ in cur.executed:
        assert _JOB_ID not in query, (
            "job_id must be parameterised, not interpolated into SQL"
        )


# ---------------------------------------------------------------------------
# mark_delivered — artifact columns persisted, parameterised UPDATE
# ---------------------------------------------------------------------------

_ARTIFACT_PATH = "/data/artifacts/job1/audio.wav"
_ARTIFACT_SHA256 = "abc123def456" * 4  # 48-char hex stand-in
_ARTIFACT_SIZE = 4_321_000
_ARTIFACT_DURATION = 142.5


def test_mark_delivered_sql_shape(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mark_delivered issues UPDATE podcast.jobs … status='delivered'."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    mark_delivered(
        _JOB_ID,
        artifact_path=_ARTIFACT_PATH,
        artifact_sha256=_ARTIFACT_SHA256,
        artifact_size_bytes=_ARTIFACT_SIZE,
        artifact_duration_s=_ARTIFACT_DURATION,
    )

    cur = postgres_mock.cursor_instance
    assert cur.executed, "Expected at least one SQL call from mark_delivered"
    assert _any_query_contains(cur, "UPDATE podcast.jobs"), (
        "Expected 'UPDATE podcast.jobs' in SQL"
    )
    assert _any_query_contains(cur, "delivered"), (
        "Expected 'delivered' in SQL"
    )


def test_mark_delivered_params_order(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mark_delivered passes the 5 values in correct order, job_id last."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    mark_delivered(
        _JOB_ID,
        artifact_path=_ARTIFACT_PATH,
        artifact_sha256=_ARTIFACT_SHA256,
        artifact_size_bytes=_ARTIFACT_SIZE,
        artifact_duration_s=_ARTIFACT_DURATION,
    )

    cur = postgres_mock.cursor_instance
    assert cur.executed
    _, params = cur.executed[-1]
    # Expect exactly 5 positional params:
    # artifact_path, artifact_sha256, artifact_size_bytes, artifact_duration_s, job_id
    assert len(params) == 5, (
        f"Expected 5 parameters, got {len(params)}: {params}"
    )
    assert params[0] == _ARTIFACT_PATH, "params[0] must be artifact_path"
    assert params[1] == _ARTIFACT_SHA256, "params[1] must be artifact_sha256"
    assert params[2] == _ARTIFACT_SIZE, "params[2] must be artifact_size_bytes"
    assert params[3] == _ARTIFACT_DURATION, "params[3] must be artifact_duration_s"
    assert params[4] == _JOB_ID, "params[4] (last) must be job_id"


def test_mark_delivered_job_id_not_interpolated(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mark_delivered must not interpolate job_id into the SQL string."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    mark_delivered(
        _JOB_ID,
        artifact_path=_ARTIFACT_PATH,
        artifact_sha256=_ARTIFACT_SHA256,
        artifact_size_bytes=_ARTIFACT_SIZE,
        artifact_duration_s=_ARTIFACT_DURATION,
    )

    cur = postgres_mock.cursor_instance
    for query, _ in cur.executed:
        assert _JOB_ID not in query, (
            "job_id must be parameterised, not interpolated into SQL"
        )


def test_mark_delivered_duration_none(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mark_delivered accepts None for artifact_duration_s (nullable column)."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    mark_delivered(
        _JOB_ID,
        artifact_path=_ARTIFACT_PATH,
        artifact_sha256=_ARTIFACT_SHA256,
        artifact_size_bytes=_ARTIFACT_SIZE,
        artifact_duration_s=None,
    )

    cur = postgres_mock.cursor_instance
    assert cur.executed, "Expected SQL call even with duration_s=None"
    _, params = cur.executed[-1]
    assert len(params) == 5
    assert params[3] is None, "params[3] must be None when duration_s is None"
    assert params[4] == _JOB_ID


# ---------------------------------------------------------------------------
# update_status — strict SQL shape assertions (parity tests)
# ---------------------------------------------------------------------------

def test_update_status_delivered_contains_finished_at(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """update_status with 'delivered' must include finished_at in the SQL."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    update_status(_JOB_ID, "delivered")

    cur = postgres_mock.cursor_instance
    assert cur.executed, "Expected at least one SQL call"
    query, params = cur.executed[-1]
    assert "finished_at" in query, (
        "SQL must contain 'finished_at' for terminal status 'delivered'"
    )
    assert _JOB_ID not in query, "job_id must be a parameter, not interpolated into SQL"
    assert _JOB_ID in params, "job_id must be passed as a parameter"


def test_update_status_gemini_running_contains_started_at(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """update_status with 'gemini_running' must include started_at in the SQL."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    update_status(_JOB_ID, "gemini_running")

    cur = postgres_mock.cursor_instance
    assert cur.executed, "Expected at least one SQL call"
    query, params = cur.executed[-1]
    assert "started_at" in query, (
        "SQL must contain 'started_at' for running status 'gemini_running'"
    )
    assert _JOB_ID not in query, "job_id must be a parameter, not interpolated into SQL"
    assert _JOB_ID in params, "job_id must be passed as a parameter"


def test_update_status_non_terminal_non_running_omits_timestamps(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """update_status with a plain intermediate status sets neither timestamp column."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    update_status(_JOB_ID, "notebooklm_uploading", set_started=False)

    cur = postgres_mock.cursor_instance
    assert cur.executed, "Expected at least one SQL call"
    query, _ = cur.executed[-1]
    assert "finished_at" not in query, (
        "SQL must NOT contain 'finished_at' for non-terminal status"
    )
    assert "started_at" not in query, (
        "SQL must NOT contain 'started_at' for non-running status with set_started=False"
    )


# ---------------------------------------------------------------------------
# mark_failed — strict SQL shape and param-order assertions (parity tests)
# ---------------------------------------------------------------------------

def test_mark_failed_sql_contains_status_failed_and_finished_at(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mark_failed SQL must contain status='failed' literal and finished_at."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    mark_failed(_JOB_ID, stage="gemini", code="TIMEOUT", message="Request timed out.")

    cur = postgres_mock.cursor_instance
    assert cur.executed, "Expected at least one SQL call"
    query, _ = cur.executed[-1]
    assert "status = 'failed'" in query, (
        "SQL must contain literal status = 'failed'"
    )
    assert "finished_at" in query, (
        "SQL must contain 'finished_at' for terminal mark_failed"
    )


def test_mark_failed_params_order_and_job_id_last(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mark_failed passes (stage, code, message, job_id) in that order."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    stage = "source_validation"
    code = "INSUFFICIENT_COUNT"
    message = "Only 3 sources remained after filtering."

    mark_failed(_JOB_ID, stage=stage, code=code, message=message)

    cur = postgres_mock.cursor_instance
    assert cur.executed
    _, params = cur.executed[-1]
    assert len(params) == 4, f"Expected 4 params (stage, code, message, job_id), got {len(params)}"
    assert params[0] == stage, "params[0] must be stage"
    assert params[1] == code, "params[1] must be code"
    assert params[2] == message, "params[2] must be message"
    assert params[3] == _JOB_ID, "params[3] (last) must be job_id"


def test_mark_failed_message_truncated_to_500(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mark_failed truncates messages longer than 500 chars to exactly 500."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    long_message = "x" * 600

    mark_failed(_JOB_ID, stage="gemini", code="LONG_ERR", message=long_message)

    cur = postgres_mock.cursor_instance
    assert cur.executed
    _, params = cur.executed[-1]
    # params[2] is the message parameter
    assert len(params[2]) == 500, (
        f"Message must be truncated to 500 chars, got {len(params[2])}"
    )


# ---------------------------------------------------------------------------
# write_audit — strict target table and param forwarding (parity tests)
# ---------------------------------------------------------------------------

def test_write_audit_targets_audit_log_table(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """write_audit SQL must reference podcast.audit_log."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    write_audit(
        _JOB_ID,
        event="status_transition",
        payload={"from": "queued", "to": "gemini_running"},
    )

    cur = postgres_mock.cursor_instance
    assert cur.executed, "Expected at least one SQL call"
    query, _ = cur.executed[-1]
    assert "podcast.audit_log" in query, (
        "SQL must target 'podcast.audit_log'"
    )


def test_write_audit_params_forward_job_id_event_payload(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """write_audit passes (job_id, event, json_payload) as parameters."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    event = "source_validated"
    payload = {"count": 7, "mode": "podcast"}

    write_audit(_JOB_ID, event=event, payload=payload)

    cur = postgres_mock.cursor_instance
    assert cur.executed
    _, params = cur.executed[-1]
    assert len(params) == 3, f"Expected 3 params (job_id, event, payload), got {len(params)}"
    assert params[0] == _JOB_ID, "params[0] must be job_id"
    assert params[1] == event, "params[1] must be event"
    # payload is JSON-serialised before being passed
    assert json.loads(params[2]) == payload, (
        "params[2] must be the JSON-serialised payload"
    )


# ---------------------------------------------------------------------------
# set_sources — strict SQL shape and param forwarding (parity tests)
# ---------------------------------------------------------------------------

def test_set_sources_sql_contains_gemini_sources_and_jsonb(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
    sample_sources_data: list[dict],
) -> None:
    """set_sources SQL must reference gemini_sources and ::jsonb cast."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    set_sources(_JOB_ID, sample_sources_data)

    cur = postgres_mock.cursor_instance
    assert cur.executed, "Expected at least one SQL call"
    query, _ = cur.executed[-1]
    assert "gemini_sources" in query, "SQL must contain 'gemini_sources'"
    assert "::jsonb" in query, "SQL must contain '::jsonb' cast"


def test_set_sources_params_forward_json_and_job_id(
    postgres_mock: Any,
    monkeypatch: pytest.MonkeyPatch,
    sample_sources_data: list[dict],
) -> None:
    """set_sources passes (json_sources, job_id) as parameters."""
    monkeypatch.setattr(_db_module, "_get_connection", lambda: postgres_mock)

    set_sources(_JOB_ID, sample_sources_data)

    cur = postgres_mock.cursor_instance
    assert cur.executed
    _, params = cur.executed[-1]
    assert len(params) == 2, f"Expected 2 params (json_sources, job_id), got {len(params)}"
    # params[0] is the JSON-serialised sources list
    assert json.loads(params[0]) == sample_sources_data, (
        "params[0] must be the JSON-serialised sources list"
    )
    assert params[1] == _JOB_ID, "params[1] must be job_id"
