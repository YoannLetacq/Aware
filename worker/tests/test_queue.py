"""Tests for app.queue — Redis BRPOP job claim logic.

Uses unittest.mock.patch to stub the redis client; no live Redis connection
is made in CI.  The fakeredis fixture from conftest is available for gate-3
docker runs where fakeredis is installed.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Import impl — ImportError acceptable until executor lands.
# ---------------------------------------------------------------------------
try:
    import app.queue as _queue_module
    from app.queue import claim_next_job
    _IMPL_AVAILABLE = True
except ImportError:
    _IMPL_AVAILABLE = False
    claim_next_job = None  # type: ignore[assignment]
    _queue_module = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(
    not _IMPL_AVAILABLE,
    reason="app.queue not yet implemented",
)

_QUEUE_NAME = "podcast:jobs"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_envelope(job_id: str = "test-uuid", interaction_id: str = "i123") -> str:
    """Return a valid JSON envelope string as LPUSH'd by n8n."""
    return json.dumps({"job_id": job_id, "interaction_id": interaction_id})


def _mock_redis_brpop(return_value: tuple | None) -> MagicMock:
    """Return a mock Redis client whose brpop() returns the given value."""
    mock_client = MagicMock()
    mock_client.brpop.return_value = return_value
    return mock_client


# ---------------------------------------------------------------------------
# claim_next_job — happy path
# ---------------------------------------------------------------------------

def test_claim_next_job_parses_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    """claim_next_job returns the parsed dict when BRPOP returns a valid envelope."""
    envelope = _make_envelope("uuid-001", "interact-001")
    mock_client = _mock_redis_brpop((_QUEUE_NAME, envelope))
    monkeypatch.setattr(_queue_module, "_get_redis_client", lambda: mock_client)

    result = claim_next_job(timeout=1)

    assert result is not None
    assert result["job_id"] == "uuid-001"
    assert result["interaction_id"] == "interact-001"


def test_claim_next_job_returns_correct_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """claim_next_job result contains job_id and interaction_id keys."""
    envelope = _make_envelope("uuid-002", "interact-002")
    mock_client = _mock_redis_brpop((_QUEUE_NAME, envelope))
    monkeypatch.setattr(_queue_module, "_get_redis_client", lambda: mock_client)

    result = claim_next_job(timeout=1)

    assert result is not None
    assert "job_id" in result
    assert "interaction_id" in result


def test_claim_next_job_passes_timeout_to_brpop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """claim_next_job forwards the timeout argument to the redis brpop call."""
    envelope = _make_envelope("uuid-003", "interact-003")
    mock_client = _mock_redis_brpop((_QUEUE_NAME, envelope))
    monkeypatch.setattr(_queue_module, "_get_redis_client", lambda: mock_client)

    claim_next_job(timeout=30)

    mock_client.brpop.assert_called_once()
    call_args = mock_client.brpop.call_args
    # The timeout value 30 must appear in positional or keyword args.
    all_args = list(call_args.args) + list(call_args.kwargs.values())
    assert any(30 == a or 30 in (a if isinstance(a, (list, tuple)) else []) for a in all_args), (
        "Expected timeout=30 to be forwarded to brpop"
    )


# ---------------------------------------------------------------------------
# claim_next_job — timeout (empty queue)
# ---------------------------------------------------------------------------

def test_claim_next_job_timeout_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """claim_next_job returns None when BRPOP times out (returns None)."""
    mock_client = _mock_redis_brpop(None)
    monkeypatch.setattr(_queue_module, "_get_redis_client", lambda: mock_client)

    result = claim_next_job(timeout=1)

    assert result is None


# ---------------------------------------------------------------------------
# claim_next_job — poison message (malformed JSON)
# ---------------------------------------------------------------------------

def test_claim_next_job_malformed_json_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """claim_next_job raises an exception for a non-JSON poison message."""
    mock_client = _mock_redis_brpop((_QUEUE_NAME, "not-valid-json{{"))
    monkeypatch.setattr(_queue_module, "_get_redis_client", lambda: mock_client)

    with pytest.raises((json.JSONDecodeError, ValueError, Exception)):
        claim_next_job(timeout=1)


# ---------------------------------------------------------------------------
# claim_next_job — missing required field
# ---------------------------------------------------------------------------

def test_claim_next_job_missing_field_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """claim_next_job raises an exception for an envelope missing job_id."""
    mock_client = _mock_redis_brpop(
        (_QUEUE_NAME, json.dumps({"interaction_id": "i1"}))
    )
    monkeypatch.setattr(_queue_module, "_get_redis_client", lambda: mock_client)

    with pytest.raises((KeyError, ValueError, Exception)):
        claim_next_job(timeout=1)
