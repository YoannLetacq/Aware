"""Tests for app.gemini — call_gemini, Source, and SourcesEnvelope contracts.

All tests use monkeypatch to replace _get_gemini_client; no live API calls in CI.
The executor imports `from google import genai` at module level in app/gemini.py
and routes all calls through the lazy-singleton _get_gemini_client() factory.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Pydantic is a hard dep (in pyproject.toml) — import directly.
# ---------------------------------------------------------------------------
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Import impl — ImportError acceptable until executor lands.
# ---------------------------------------------------------------------------
try:
    import app.gemini as _gemini_module
    from app.gemini import (
        GeminiError,
        Source,
        SourcesEnvelope,
        call_gemini,
    )
    _IMPL_AVAILABLE = True
except ImportError:
    _IMPL_AVAILABLE = False
    Source = None  # type: ignore[assignment,misc]
    SourcesEnvelope = None  # type: ignore[assignment,misc]
    call_gemini = None  # type: ignore[assignment]
    GeminiError = None  # type: ignore[assignment,misc]
    _gemini_module = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(
    not _IMPL_AVAILABLE,
    reason="app.gemini not yet implemented",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_SOURCES_PAYLOAD: list[dict[str, Any]] = [
    {
        "url": "https://arxiv.org/abs/2401.00001",
        "title": "LLM Survey",
        "type": "paper",
        "relevance_score": 0.95,
        "language": "en",
        "rationale": "Authoritative survey paper.",
    },
    {
        "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "title": "Open-Source LLMs Explained",
        "type": "youtube",
        "relevance_score": 0.88,
        "language": "fr",
        "rationale": "French overview video.",
    },
    {
        "url": "https://huggingface.co/blog/open-llm-leaderboard",
        "title": "Open LLM Leaderboard",
        "type": "article",
        "relevance_score": 0.82,
        "language": "en",
        "rationale": "Comprehensive ranking article.",
    },
    {
        "url": "https://blog.mistral.ai/mistral-7b",
        "title": "Mistral 7B",
        "type": "article",
        "relevance_score": 0.79,
        "language": "en",
        "rationale": "Official model announcement.",
    },
    {
        "url": "https://vimeo.com/987654321",
        "title": "LLM Benchmark Deep Dive",
        "type": "video_other",
        "relevance_score": 0.71,
        "language": "en",
        "rationale": "Technical benchmark walkthrough.",
    },
    {
        "url": "https://ted.com/talks/open_source_ai_2025",
        "title": "Open Source AI: Next Frontier",
        "type": "video_other",
        "relevance_score": 0.68,
        "language": "en",
        "rationale": "TED talk on open AI ecosystem.",
    },
    {
        "url": "https://www.lemonde.fr/ia/article/2025/01/modeles.html",
        "title": "Modèles open-source et IA",
        "type": "article",
        "relevance_score": 0.74,
        "language": "fr",
        "rationale": "French press coverage.",
    },
    {
        "url": "https://conference.example.com/2025/llm-panel",
        "title": "LLMs in Production Panel",
        "type": "video_other",
        "relevance_score": 0.65,
        "language": "fr",
        "rationale": "Conference panel on production.",
    },
]


def _make_mock_response(text: str, finish_reason: str = "STOP") -> MagicMock:
    """Build a minimal mock that mimics a google-genai GenerateContentResponse."""
    response = MagicMock()
    response.text = text
    # Candidates structure used for MAX_TOKENS / SAFETY detection.
    candidate = MagicMock()
    candidate.finish_reason = finish_reason
    response.candidates = [candidate]
    response.prompt_feedback = MagicMock()
    response.prompt_feedback.block_reason = None
    return response


def _make_fake_client(response: MagicMock) -> MagicMock:
    """Build a fake genai.Client whose generate_content returns *response*."""
    fake_client = MagicMock()
    fake_client.models.generate_content.return_value = response
    return fake_client


# ---------------------------------------------------------------------------
# Source model — field-level validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "field,bad_value",
    [
        ("type", "blog"),
        ("language", "de"),
        ("relevance_score", 1.5),
        ("relevance_score", -0.1),
        ("url", "http://insecure.example.com/page"),  # http, not https
    ],
)
def test_source_model_rejects_invalid_field(field: str, bad_value: Any) -> None:
    """Source raises ValidationError for each invalid field value."""
    data = dict(_VALID_SOURCES_PAYLOAD[0])
    data[field] = bad_value
    with pytest.raises(ValidationError):
        Source(**data)


def test_source_model_accepts_valid_data() -> None:
    """Source model instantiates cleanly from a valid dict."""
    src = Source(**_VALID_SOURCES_PAYLOAD[0])
    assert src.type == "paper"
    assert 0.0 <= src.relevance_score <= 1.0


def test_sources_envelope_accepts_valid_list() -> None:
    """SourcesEnvelope wraps a list of Source objects without error."""
    envelope = SourcesEnvelope(sources=[Source(**d) for d in _VALID_SOURCES_PAYLOAD])
    assert len(envelope.sources) == len(_VALID_SOURCES_PAYLOAD)


# ---------------------------------------------------------------------------
# call_gemini — happy path
# ---------------------------------------------------------------------------

def test_call_gemini_returns_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    """call_gemini returns a SourcesEnvelope when the API returns valid JSON."""
    payload = json.dumps({"sources": _VALID_SOURCES_PAYLOAD})
    response = _make_mock_response(payload)
    fake_client = _make_fake_client(response)
    monkeypatch.setattr(_gemini_module, "_get_gemini_client", lambda: fake_client)

    result = call_gemini(
        subject="Les modèles de langage open-source en 2025",
        mode="podcast",
        language_hint="fr",
    )

    assert isinstance(result, SourcesEnvelope)
    assert len(result.sources) == len(_VALID_SOURCES_PAYLOAD)


def test_call_gemini_source_fields_correct(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each Source in the returned envelope has all required fields."""
    payload = json.dumps({"sources": _VALID_SOURCES_PAYLOAD})
    response = _make_mock_response(payload)
    fake_client = _make_fake_client(response)
    monkeypatch.setattr(_gemini_module, "_get_gemini_client", lambda: fake_client)

    result = call_gemini("Test subject for LLMs", "podcast", "en")

    for src in result.sources:
        assert src.url is not None
        assert src.title
        assert src.type in ("paper", "youtube", "article", "video_other")
        assert 0.0 <= src.relevance_score <= 1.0
        assert src.language in ("fr", "en", "other")
        assert src.rationale


# ---------------------------------------------------------------------------
# call_gemini — schema validation failure
# ---------------------------------------------------------------------------

def test_call_gemini_schema_validation_error_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """call_gemini raises ValidationError or GeminiError for malformed JSON."""
    malformed = json.dumps({"sources": [{"url": "not-a-url", "type": "blog"}]})
    response = _make_mock_response(malformed)
    fake_client = _make_fake_client(response)
    monkeypatch.setattr(_gemini_module, "_get_gemini_client", lambda: fake_client)

    with pytest.raises((ValidationError, GeminiError)):
        call_gemini("Test subject", "podcast", "fr")


def test_call_gemini_empty_response_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """call_gemini raises GeminiError(code='EMPTY_RESPONSE') when text is empty."""
    response = _make_mock_response("")
    fake_client = _make_fake_client(response)
    monkeypatch.setattr(_gemini_module, "_get_gemini_client", lambda: fake_client)

    with pytest.raises(GeminiError) as exc_info:
        call_gemini("Test subject", "podcast", "fr")
    assert exc_info.value.code == "EMPTY_RESPONSE"


# ---------------------------------------------------------------------------
# call_gemini — MAX_TOKENS truncation
# ---------------------------------------------------------------------------

def test_call_gemini_max_tokens_truncation_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """call_gemini raises GeminiError when finish_reason is MAX_TOKENS."""
    truncated = json.dumps({"sources": _VALID_SOURCES_PAYLOAD[:3]})
    response = _make_mock_response(truncated, finish_reason="MAX_TOKENS")
    fake_client = _make_fake_client(response)
    monkeypatch.setattr(_gemini_module, "_get_gemini_client", lambda: fake_client)

    with pytest.raises(GeminiError):
        call_gemini("Test subject for truncation", "podcast", "en")


# ---------------------------------------------------------------------------
# call_gemini — safety block
# ---------------------------------------------------------------------------

def test_call_gemini_safety_blocked_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """call_gemini raises GeminiError when prompt_feedback.block_reason is SAFETY."""
    response = _make_mock_response("")
    response.prompt_feedback.block_reason = "SAFETY"
    fake_client = _make_fake_client(response)
    monkeypatch.setattr(_gemini_module, "_get_gemini_client", lambda: fake_client)

    with pytest.raises(GeminiError):
        call_gemini("Problematic subject", "podcast", "fr")


# ---------------------------------------------------------------------------
# call_gemini — 429 retry logic
# ---------------------------------------------------------------------------

def test_call_gemini_429_retried_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """call_gemini retries on rate-limit error and succeeds on 3rd attempt."""
    import app.gemini as mod

    monkeypatch.setattr(mod, "_BACKOFF_SECONDS", (0.0, 0.0))

    call_count = 0
    valid_payload = json.dumps({"sources": _VALID_SOURCES_PAYLOAD})

    def _flaky_generate(*args: object, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise mod._GeminiRateLimitError("429 RESOURCE_EXHAUSTED: rate limit")
        return _make_mock_response(valid_payload)

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = _flaky_generate
    monkeypatch.setattr(mod, "_get_gemini_client", lambda: fake_client)

    result = call_gemini("Retry subject", "podcast", "fr")

    assert call_count == 3
    assert isinstance(result, SourcesEnvelope)


def test_call_gemini_429_exceeds_budget_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """call_gemini raises GeminiError after exhausting the retry budget (3 attempts)."""
    import app.gemini as mod

    monkeypatch.setattr(mod, "_BACKOFF_SECONDS", (0.0, 0.0))

    call_count = 0

    def _always_429(*args: object, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        raise mod._GeminiRateLimitError("429 RESOURCE_EXHAUSTED: rate limit")

    fake_client = MagicMock()
    fake_client.models.generate_content.side_effect = _always_429
    monkeypatch.setattr(mod, "_get_gemini_client", lambda: fake_client)

    with pytest.raises(GeminiError):
        call_gemini("Budget exceeded subject", "podcast", "fr")

    # Budget = 1 initial + 2 retries = 3 total calls.
    assert call_count == 3
