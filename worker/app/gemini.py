"""Gemini source-curation call with structured-output JSON schema enforcement.

Builds the system + user prompt per requirements.md §Gemini Prompt Contract,
calls google-genai with response_json_schema = SourcesEnvelope.model_json_schema(),
and retries twice on transient failures (5s / 20s backoff) per ARCH §6 F5.
"""

import time
from typing import Literal

import pydantic
import structlog
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app import config

logger = structlog.get_logger(__name__)

_MAX_SUBJECT_LEN = 500


class GeminiError(Exception):
    """Raised when the Gemini call fails after the retry budget is exhausted."""

    def __init__(self, message: str, code: str = "GEMINI_ERROR") -> None:
        """Store a machine-readable error code alongside the message."""
        super().__init__(message)
        self.code = code


class _GeminiRateLimitError(Exception):
    """Raised internally when the Gemini API returns a 429 rate-limit signal."""


def _https_url(value: pydantic.HttpUrl) -> pydantic.HttpUrl:
    """Reject non-https URLs — Gemini prompt contract requires https sources."""
    if str(value).startswith("http://"):
        raise ValueError("URL must use https scheme, got http")
    return value


class Source(pydantic.BaseModel):
    """One curated source — schema mirrors ARCHITECTURE.md §3.3."""

    url: pydantic.HttpUrl
    title: str = pydantic.Field(min_length=1, max_length=300)
    type: Literal["paper", "youtube", "article", "video_other"]
    relevance_score: float = pydantic.Field(ge=0.0, le=1.0)
    language: Literal["fr", "en", "other"]
    rationale: str = pydantic.Field(min_length=1, max_length=280)

    @pydantic.field_validator("url")
    @classmethod
    def _validate_url(cls, value: pydantic.HttpUrl) -> pydantic.HttpUrl:
        """Delegate to module-level https guard."""
        return _https_url(value)


class SourcesEnvelope(pydantic.BaseModel):
    """Top-level Gemini response wrapper containing the curated source list."""

    sources: list[Source]


_SYSTEM_PROMPT = (
    "You are a research curator. Given a subject (1-2 sentences) and an output "
    "mode, return a JSON object with key 'sources' containing 8 high-quality "
    "sources suitable for ingestion by NotebookLM. Each source must be publicly "
    "accessible without authentication and have textual or transcribable content. "
    "Prefer recency (<= 24 months) unless the subject is historical. "
    "Constraints: no paywalled domains (nytimes.com, ft.com, wsj.com, "
    "sciencedirect.com without open-access flag, similar); no social-media posts; "
    "no homepages (must be deep links); at least one academic source (type=paper) "
    "and at least one video source (type=youtube or type=video_other). "
    "Each source has: url (https), title, type in {paper, youtube, article, "
    "video_other}, relevance_score in [0.0, 1.0], language in {fr, en, other}, "
    "and a one-sentence English rationale."
)


def _build_user_prompt(subject: str, mode: str, language_hint: str) -> str:
    """Compose the user-message body sent alongside the system prompt."""
    if len(subject) > _MAX_SUBJECT_LEN:
        logger.warning(
            "subject_truncated",
            original_len=len(subject),
            max_len=_MAX_SUBJECT_LEN,
        )
        subject = subject[:_MAX_SUBJECT_LEN]
    return (
        f"subject: {subject}\n"
        f"mode: {mode}\n"
        f"language_hint: {language_hint}\n"
        f"target_count: {config.SOURCE_COUNT_TARGET}\n"
    )


def _check_response_integrity(response: object) -> None:
    """Raise GeminiError for safety-blocked or token-truncated responses."""
    feedback = getattr(response, "prompt_feedback", None)
    if feedback is not None and getattr(feedback, "block_reason", None):
        raise GeminiError(
            f"prompt blocked by safety filter: {feedback.block_reason}",
            code="SAFETY_BLOCKED",
        )
    candidates = getattr(response, "candidates", None) or []
    if candidates:
        finish_reason = getattr(candidates[0], "finish_reason", None)
        if finish_reason == "MAX_TOKENS":
            raise GeminiError(
                "Gemini response truncated at MAX_TOKENS",
                code="MAX_TOKENS",
            )


class _GeminiClientHolder:
    """Module-scoped lazy holder for the Gemini client singleton."""

    instance: genai.Client | None = None


def _get_gemini_client() -> genai.Client:
    """Lazy-singleton Gemini client (one HTTP session per worker process)."""
    if _GeminiClientHolder.instance is None:
        _GeminiClientHolder.instance = genai.Client(api_key=config.GEMINI_API_KEY)
    return _GeminiClientHolder.instance


def _call_once(subject: str, mode: str, language_hint: str) -> SourcesEnvelope:
    """Single Gemini call without retry — raises on any failure."""
    client = _get_gemini_client()
    user_prompt = _build_user_prompt(subject, mode, language_hint)
    try:
        response = client.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=[_SYSTEM_PROMPT, user_prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_json_schema=SourcesEnvelope.model_json_schema(),
                max_output_tokens=config.GEMINI_MAX_OUTPUT_TOKENS,
            ),
        )
    except genai_errors.ClientError as exc:
        if exc.code == 429:
            raise _GeminiRateLimitError(str(exc)) from exc
        raise
    _check_response_integrity(response)
    text = response.text
    if text is None or text == "":
        raise GeminiError("empty response text from Gemini", code="EMPTY_RESPONSE")
    return SourcesEnvelope.model_validate_json(text)


_BACKOFF_SECONDS: tuple[float, ...] = (5.0, 20.0)


def call_gemini(subject: str, mode: str, language_hint: str = "fr") -> SourcesEnvelope:
    """Call Gemini with 2 retries on transient failures (5s / 20s backoff).

    Raises GeminiError after the final attempt fails. The retry budget here
    mirrors requirements.md §Retry budget and ARCH §6 F5.
    """
    last_error: Exception | None = None
    for attempt, delay in enumerate((0.0,) + _BACKOFF_SECONDS):
        if delay > 0:
            time.sleep(delay)
        try:
            return _call_once(subject, mode, language_hint)
        except GeminiError:
            # Semantic failures (empty response, safety block, MAX_TOKENS,
            # schema validation) are not transient — re-raise immediately.
            raise
        except _GeminiRateLimitError as exc:
            last_error = exc
            logger.warning(
                "gemini_call_rate_limited",
                attempt=attempt,
                error=str(exc),
            )
        except pydantic.ValidationError as exc:
            last_error = exc
            logger.warning(
                "gemini_call_failed",
                attempt=attempt,
                error=str(exc),
                error_type=type(exc).__name__,
            )
        except (ValueError, OSError) as exc:
            last_error = exc
            logger.warning(
                "gemini_call_transport_failed",
                attempt=attempt,
                error=str(exc),
                error_type=type(exc).__name__,
            )
    raise GeminiError(
        f"gemini call failed after retries: {last_error}",
        code="RETRY_EXHAUSTED",
    ) from last_error
