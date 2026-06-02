"""Shared pytest fixtures for Phase 2 worker tests.

Covers: sample_sources_data, gemini_response_fixture, postgres_mock.
All fixtures function-scoped unless data is provably immutable.

app.config evaluates _required() at import time, so collecting any test that
imports app.* would raise RuntimeError when the environment is unset (e.g.
``uv run pytest`` with no .env exported). To keep collection green without
real secrets, we seed dummy values via os.environ.setdefault BEFORE any
``app.*`` import runs. setdefault means a real env / CI value always wins;
these placeholders are non-secret stand-ins used only when nothing is set.
"""

import json
import os
from typing import Any

import pytest

# Dummy env defaults for every variable worker/app/config.py requires via
# _required(). Parse-safe values (int-castable ports/limits, "0" kill switch).
# Real env / CI values take precedence because setdefault never overwrites.
_DUMMY_ENV: dict[str, str] = {
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_USER": "test_user",
    "POSTGRES_PASSWORD": "test_password",
    "POSTGRES_DB": "test_db",
    "REDIS_HOST": "localhost",
    "REDIS_PASSWORD": "test_redis_password",
    "GEMINI_API_KEY": "test_gemini_key",
    "GEMINI_MODEL": "gemini-test",
    "OPERATOR_DISCORD_WEBHOOK": "https://discord.invalid/webhook",
    "DISCORD_BOT_TOKEN": "test_bot_token",
    "KILL_SWITCH": "0",
    "RATE_LIMIT_PER_USER_DAY": "3",
    "RATE_LIMIT_GLOBAL_DAY": "20",
    "WORKER_SHARED_TOKEN": "test_shared_token",
}
for _name, _value in _DUMMY_ENV.items():
    os.environ.setdefault(_name, _value)


# ---------------------------------------------------------------------------
# 8-source dataset: 1 paper, 1 youtube, 3 article, 3 video_other.
# Generated programmatically; specific URLs are not load-bearing.
# ---------------------------------------------------------------------------

def _build_source(
    src_type: str, idx: int, score: float = 0.8, lang: str = "en"
) -> dict[str, Any]:
    """Return a minimal valid source dict for the given type and index."""
    url_map = {
        "paper": f"https://arxiv.org/abs/2401.{idx:05d}",
        "youtube": f"https://www.youtube.com/watch?v=vid{idx:04d}",
        "article": f"https://blog.example.com/article-{idx}",
        "video_other": f"https://vimeo.com/{1000000 + idx}",
    }
    return {
        "url": url_map[src_type],
        "title": f"{src_type.capitalize()} source {idx}",
        "type": src_type,
        "relevance_score": round(score - idx * 0.01, 3),
        "language": lang,
        "rationale": f"Reference for {src_type} source {idx}.",
    }


_SAMPLE_SOURCES_DATA: list[dict[str, Any]] = (
    [_build_source("paper", 0, 0.95)]
    + [_build_source("youtube", 1, 0.88, "fr")]
    + [_build_source("article", i, 0.80) for i in range(2, 5)]
    + [_build_source("video_other", i, 0.70) for i in range(5, 8)]
)


@pytest.fixture()
def sample_sources_data() -> list[dict[str, Any]]:
    """Return raw dicts for 8 canonical sample sources (no Pydantic dep)."""
    return [dict(item) for item in _SAMPLE_SOURCES_DATA]


@pytest.fixture()
def gemini_response_fixture() -> str:
    """Return a JSON string matching the SourcesEnvelope schema."""
    return json.dumps({"sources": _SAMPLE_SOURCES_DATA})


# ---------------------------------------------------------------------------
# Postgres mock — lightweight psycopg cursor mock (no Docker required).
# ---------------------------------------------------------------------------

class _FakeCursor:
    """Minimal psycopg cursor stand-in for db.py unit tests."""

    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []
        self._rows: list[tuple[Any, ...]] = []
        self.rowcount: int = 0

    def execute(self, query: str, params: tuple[Any, ...] = ()) -> None:
        """Record the executed query and params."""
        self.executed.append((query, params))
        self.rowcount = 1

    def fetchone(self) -> tuple[Any, ...] | None:
        """Return the first staged row or None."""
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        """Return all staged rows."""
        return list(self._rows)

    def __enter__(self) -> "_FakeCursor":
        """Support use as a context manager (mirrors psycopg cursor)."""
        return self

    def __exit__(self, *args: object) -> None:
        """No-op exit — no resources to release."""


class _FakeConnection:
    """Minimal psycopg connection stand-in."""

    def __init__(self) -> None:
        self.cursor_instance = _FakeCursor()
        self._committed = False

    def cursor(self):
        """Return the shared fake cursor."""
        return self.cursor_instance

    def commit(self) -> None:
        """Record commit call."""
        self._committed = True

    def rollback(self) -> None:
        """No-op rollback."""

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        pass


@pytest.fixture()
def postgres_mock() -> _FakeConnection:
    """Return a fake psycopg connection for db.py unit tests."""
    return _FakeConnection()
