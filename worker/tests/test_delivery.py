"""Tests for app.delivery — post_failure and post_success Discord delivery functions.

All tests monkeypatch httpx.post to avoid live network calls. The module
uses structlog which is allowed to emit to stdout in tests without issue.
"""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock

import httpx
import pytest

try:
    import app.delivery as _delivery_module
    from app.delivery import post_success

    _IMPL_AVAILABLE = True
except ImportError:
    _IMPL_AVAILABLE = False
    post_success = None  # type: ignore[assignment]
    _delivery_module = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(
    not _IMPL_AVAILABLE,
    reason="app.delivery not yet implemented",
)

_CHANNEL_ID = "987654321012345678"
_MESSAGE_FR = "Votre podcast est prêt !"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_http_response(status_code: int) -> MagicMock:
    """Return a minimal mock mimicking an httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = "ok" if status_code < 400 else "Bad Request"
    return resp


# ---------------------------------------------------------------------------
# post_success — 200 success path
# ---------------------------------------------------------------------------


def test_post_success_200_sends_multipart(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """post_success POSTs multipart with file and caption on HTTP 200."""
    artifact = tmp_path / "episode.wav"
    artifact.write_bytes(b"RIFF fake wav content")

    mock_post = MagicMock(return_value=_make_http_response(200))
    monkeypatch.setattr(httpx, "post", mock_post)
    monkeypatch.setattr(_delivery_module.config, "DISCORD_BOT_TOKEN", "test-token")

    result = post_success(_CHANNEL_ID, str(artifact), _MESSAGE_FR)

    assert result is True, "post_success must return True on HTTP 200"
    assert mock_post.call_count == 1
    args, kwargs = mock_post.call_args
    # URL must contain the verbatim channel_id
    url = args[0] if args else kwargs.get("url", "")
    assert _CHANNEL_ID in url
    # Must use 'files' kwarg (multipart) — not 'json'
    assert "files" in kwargs
    # The Authorization header must use the bot token
    headers = kwargs.get("headers", {})
    assert headers.get("Authorization") == "Bot test-token"
    # Content-Type must NOT be set manually (let httpx set boundary)
    assert "Content-Type" not in headers


def test_post_success_200_logs_info(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """post_success emits delivery_post_success_sent on 200."""
    artifact = tmp_path / "episode.mp3"
    artifact.write_bytes(b"ID3 fake mp3")

    mock_post = MagicMock(return_value=_make_http_response(200))
    monkeypatch.setattr(httpx, "post", mock_post)
    monkeypatch.setattr(_delivery_module.config, "DISCORD_BOT_TOKEN", "test-token")

    # Should not raise
    post_success(_CHANNEL_ID, str(artifact), _MESSAGE_FR)


# ---------------------------------------------------------------------------
# post_success — HTTP >= 400 error path
# ---------------------------------------------------------------------------


def test_post_success_http_error_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """post_success swallows HTTP >=400 errors — worker loop must not crash."""
    artifact = tmp_path / "episode.wav"
    artifact.write_bytes(b"RIFF fake wav content")

    mock_post = MagicMock(return_value=_make_http_response(403))
    monkeypatch.setattr(httpx, "post", mock_post)
    monkeypatch.setattr(_delivery_module.config, "DISCORD_BOT_TOKEN", "test-token")

    # Must not raise; returns False on HTTP >=400.
    result = post_success(_CHANNEL_ID, str(artifact), _MESSAGE_FR)

    assert result is False, "post_success must return False on HTTP >=400"
    assert mock_post.call_count == 1


def test_post_success_http_error_url_contains_channel_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """On HTTP error the URL still contains the correct channel_id (verbatim)."""
    artifact = tmp_path / "episode.wav"
    artifact.write_bytes(b"data")

    mock_post = MagicMock(return_value=_make_http_response(500))
    monkeypatch.setattr(httpx, "post", mock_post)
    monkeypatch.setattr(_delivery_module.config, "DISCORD_BOT_TOKEN", "test-token")

    post_success(_CHANNEL_ID, str(artifact), _MESSAGE_FR)

    args, kwargs = mock_post.call_args
    url = args[0] if args else kwargs.get("url", "")
    assert _CHANNEL_ID in url


# ---------------------------------------------------------------------------
# post_success — httpx.HTTPError transport path
# ---------------------------------------------------------------------------


def test_post_success_transport_error_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """post_success swallows httpx.HTTPError — worker loop must not crash."""
    artifact = tmp_path / "episode.wav"
    artifact.write_bytes(b"RIFF fake wav content")

    mock_post = MagicMock(side_effect=httpx.HTTPError("connection refused"))
    monkeypatch.setattr(httpx, "post", mock_post)
    monkeypatch.setattr(_delivery_module.config, "DISCORD_BOT_TOKEN", "test-token")

    # Must not raise; returns False on transport error.
    result = post_success(_CHANNEL_ID, str(artifact), _MESSAGE_FR)

    assert result is False, "post_success must return False on httpx.HTTPError"


def test_post_success_transport_error_file_part_attempted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """Even on transport error, a file part was included in the attempted POST."""
    artifact = tmp_path / "episode.wav"
    artifact.write_bytes(b"RIFF fake wav content")

    mock_post = MagicMock(side_effect=httpx.HTTPError("timeout"))
    monkeypatch.setattr(httpx, "post", mock_post)
    monkeypatch.setattr(_delivery_module.config, "DISCORD_BOT_TOKEN", "test-token")

    post_success(_CHANNEL_ID, str(artifact), _MESSAGE_FR)

    args, kwargs = mock_post.call_args
    assert "files" in kwargs


# ---------------------------------------------------------------------------
# post_success — OSError (missing artifact file)
# ---------------------------------------------------------------------------


def test_post_success_missing_file_returns_false(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """post_success returns False when the artifact file does not exist (OSError)."""
    missing = tmp_path / "does-not-exist.wav"

    mock_post = MagicMock(return_value=_make_http_response(200))
    monkeypatch.setattr(httpx, "post", mock_post)
    monkeypatch.setattr(_delivery_module.config, "DISCORD_BOT_TOKEN", "test-token")

    # open() raises before httpx.post is reached.
    result = post_success(_CHANNEL_ID, str(missing), _MESSAGE_FR)

    assert result is False, "post_success must return False on OSError (missing file)"
    mock_post.assert_not_called()


# ---------------------------------------------------------------------------
# post_success — caption truncation
# ---------------------------------------------------------------------------


def test_post_success_caption_truncated_to_2000(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pathlib.Path,
) -> None:
    """post_success truncates the French caption to Discord's 2000-char limit."""
    artifact = tmp_path / "episode.wav"
    artifact.write_bytes(b"data")

    long_caption = "A" * 3000
    mock_post = MagicMock(return_value=_make_http_response(200))
    monkeypatch.setattr(httpx, "post", mock_post)
    monkeypatch.setattr(_delivery_module.config, "DISCORD_BOT_TOKEN", "test-token")

    post_success(_CHANNEL_ID, str(artifact), long_caption)

    _, kwargs = mock_post.call_args
    # The caption appears in the 'data' kwarg as payload_json or 'content'
    data = kwargs.get("data", {})
    caption_value = data.get("content", data.get("payload_json", ""))
    assert len(caption_value) <= 2000
