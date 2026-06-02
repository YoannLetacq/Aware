"""Source list post-validation — dedup, URL liveness, diversity, count.

After Gemini returns a SourcesEnvelope, this module enforces:
- URL normalisation + deduplication;
- HTTP HEAD liveness check (5 s timeout, parallel);
- Type-mix: at least one paper and at least one video;
- Count window 5..15 (config.SOURCE_COUNT_MIN .. SOURCE_COUNT_MAX).

Raises SourcesError variants on violation so the worker can map them onto
error_code values (SUBJECT_TOO_NARROW, INSUFFICIENT_COUNT, INSUFFICIENT_DIVERSITY,
DEAD_LINKS_EXCEED_THRESHOLD).
"""

import ipaddress
import socket
from urllib.parse import urlparse, urlunparse

import httpx
import structlog

from app import config
from app.gemini import Source

logger = structlog.get_logger(__name__)

DEAD_LINK_THRESHOLD = 0.5


class SourcesError(Exception):
    """Raised when the source list fails post-validation."""

    def __init__(self, code: str, message: str = "") -> None:
        """Store error_code on the exception for db.mark_failed mapping."""
        super().__init__(message)
        self.code = code

    def __str__(self) -> str:
        """Return message if set, otherwise the code."""
        msg = super().__str__()
        return msg if msg else self.code


def normalize_url(raw: str) -> str:
    """Lowercase host, drop most query params (keep YouTube v=), trim trailing slash."""
    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    path = parsed.path.rstrip("/")
    query = ""
    if "youtube.com" in host or "youtu.be" in host:
        kept = [p for p in parsed.query.split("&") if p.startswith("v=")]
        query = "&".join(kept)
    return urlunparse((parsed.scheme.lower(), host, path, "", query, ""))


def _is_private_host(host: str) -> bool:
    """Return True if host resolves to a private/loopback IP (SSRF defence).

    DNS failure is treated as non-private (the liveness probe will mark the
    URL dead instead). ValueError from ip_address parsing is also caught.
    """
    try:
        ip_str = socket.gethostbyname(host)
        return ipaddress.ip_address(ip_str).is_private
    except OSError:
        return False
    except ValueError:
        return False


def _dedup(sources: list[Source]) -> list[Source]:
    """Remove duplicate sources based on normalised URL (first occurrence wins)."""
    seen: set[str] = set()
    keep: list[Source] = []
    for src in sources:
        key = normalize_url(str(src.url))
        if key in seen:
            continue
        seen.add(key)
        keep.append(src)
    return keep


def _probe_one(client: httpx.Client, url: str) -> bool:
    """Return True if URL responds with a non-server-error status code.

    HEAD is attempted first; some hosts reject HEAD (405) — we retry with GET
    when that happens. Any transport-level failure marks the URL dead.
    Private-IP targets are treated as dead (SSRF defence, M1).
    """
    parsed = urlparse(url)
    if _is_private_host(parsed.hostname or ""):
        logger.info("source_liveness_private_host", url=url)
        return False
    try:
        resp = client.head(url, follow_redirects=True)
        if resp.status_code == 405:
            resp = client.get(url, follow_redirects=True)
        return resp.status_code < 500 and resp.status_code != 404
    except (httpx.HTTPError, OSError) as exc:
        logger.info("source_liveness_dead", url=url, error=str(exc))
        return False


def _probe_all(sources: list[Source]) -> list[Source]:
    """Run liveness checks sequentially and drop dead URLs."""
    timeout = httpx.Timeout(config.URL_LIVENESS_TIMEOUT_S)
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        max_redirects=3,
    ) as client:
        results = [_probe_one(client, str(src.url)) for src in sources]
    return [src for src, alive in zip(sources, results) if alive]


def _check_diversity(sources: list[Source]) -> None:
    """Enforce at least one academic and at least one video source."""
    types_present = {src.type for src in sources}
    has_paper = "paper" in types_present
    has_video = "youtube" in types_present or "video_other" in types_present
    if not has_paper or not has_video:
        raise SourcesError(
            "INSUFFICIENT_DIVERSITY",
            "sources must include >=1 paper and >=1 video",
        )


def sanity_check_sources(sources: list[Source | dict]) -> list[Source]:
    """Run the full source-validation pipeline; return the cleaned list.

    Accepts Source objects or raw dicts (coerced to Source on entry).
    Raises SourcesError(code=...) on count or diversity violations. The
    caller maps SUBJECT_TOO_NARROW onto an empty / very-short result so the
    worker can surface a French "subject too narrow" message.
    """
    if not sources:
        raise SourcesError("SUBJECT_TOO_NARROW", "Gemini returned no sources")
    normalised: list[Source] = [
        src if isinstance(src, Source) else Source.model_validate(src)
        for src in sources
    ]
    deduped = _dedup(normalised)
    pre_filter_count = len(deduped)
    live = _probe_all(deduped)
    dropped_count = pre_filter_count - len(live)
    if pre_filter_count > 0 and dropped_count / pre_filter_count > DEAD_LINK_THRESHOLD:
        raise SourcesError(
            "DEAD_LINKS_EXCEED_THRESHOLD",
            f"too many dead links: {dropped_count}/{pre_filter_count}",
        )
    if len(live) < config.SOURCE_COUNT_MIN:
        raise SourcesError(
            "INSUFFICIENT_COUNT",
            f"only {len(live)} live sources after dedup/HEAD; "
            f"need >= {config.SOURCE_COUNT_MIN}",
        )
    if len(live) > config.SOURCE_COUNT_MAX:
        live.sort(key=lambda s: s.relevance_score, reverse=True)
        live = live[: config.SOURCE_COUNT_MAX]
    _check_diversity(live)
    return live
