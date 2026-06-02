"""NotebookLM generation orchestrator — public seam for Phase 3 automation.

This module defines the typed interface (``GenerationResult``, ``NotebookLMError``)
and the ``run_generation`` seam function that the main worker loop (US-004) and
tests (US-005) call.  The production body intentionally raises ``NotebookLMError``
with code ``NOT_IMPLEMENTED``; Phase 3 will replace that body with the full
Playwright-driven automation.

Do NOT import playwright or write DOM/selector/login logic here — see
RISK_MANAGEMENT.md §3.1 (Critical account-ban risk).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GenerationResult:
    """Immutable result returned by a successful NotebookLM generation run.

    Attributes:
        artifact_path:       Absolute local path to the downloaded artifact file.
        artifact_sha256:     Hex-encoded SHA-256 digest of the artifact file.
        artifact_size_bytes: File size in bytes.
        artifact_duration_s: Audio/video duration in seconds, or ``None`` when
                             the format does not carry duration metadata.
    """

    artifact_path: str
    artifact_sha256: str
    artifact_size_bytes: int
    artifact_duration_s: float | None


class NotebookLMError(Exception):
    """Raised when the NotebookLM automation stage fails.

    Attributes:
        code: Machine-readable error code (e.g. ``NOT_IMPLEMENTED``,
              ``SESSION_EXPIRED``, ``GENERATION_TIMEOUT``).
    """

    def __init__(self, code: str, message: str) -> None:
        """Store ``code`` as an attribute and delegate ``message`` to ``Exception``."""
        super().__init__(message)
        self.code = code


def run_generation(
    job: dict[str, Any],
    sources: list[dict[str, Any]],
) -> GenerationResult:
    """Drive NotebookLM to produce a podcast/video artifact for *job*.

    This is the **Phase 3 seam**.  The current body raises
    ``NotebookLMError("NOT_IMPLEMENTED", ...)`` unconditionally.  Phase 3 will
    replace this body with the full Playwright automation (login validation,
    notebook creation, source upload, generation trigger, artifact download).

    Do NOT add Playwright imports, DOM selectors, or login logic to this
    function until Phase 3 is explicitly in scope — see RISK_MANAGEMENT.md §3.1.

    Args:
        job:     Job row dict as returned by ``db.get_job`` (must include at
                 minimum ``job_id``, ``subject``, ``mode``, ``channel_id``).
        sources: Validated source list produced by the Gemini stage (list of
                 dicts with keys ``url``, ``title``, ``type``, etc.).

    Returns:
        A :class:`GenerationResult` with the artifact path, hash, size, and
        optional duration.

    Raises:
        NotebookLMError: Always raised in Phase 1/2 with code ``NOT_IMPLEMENTED``.
                         Phase 3 will raise this for session expiry, timeouts,
                         and other automation failures.
    """
    raise NotebookLMError(
        "NOT_IMPLEMENTED",
        "NotebookLM automation pending Phase 3",
    )
