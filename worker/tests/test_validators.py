"""Tests for app.validators — normalize_url and sanity_check_sources.

Covers: URL normalisation, dedup, liveness HEAD checks (mocked via
httpx.MockTransport), type-mix diversity checks, count bounds, and
SourcesError codes.

All network calls are intercepted — no live requests in CI.
httpx is a hard project dependency (pyproject.toml); no importorskip needed.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Import impl — ImportError acceptable until executor lands.
# ---------------------------------------------------------------------------
try:
    from app.validators import SourcesError, normalize_url, sanity_check_sources
    _IMPL_AVAILABLE = True
except ImportError:
    _IMPL_AVAILABLE = False
    normalize_url = None  # type: ignore[assignment]
    sanity_check_sources = None  # type: ignore[assignment]
    SourcesError = None  # type: ignore[assignment]

pytestmark = pytest.mark.skipif(
    not _IMPL_AVAILABLE,
    reason="app.validators not yet implemented",
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_source(overrides: dict | None = None) -> dict:
    """Return a minimal valid source dict, optionally overridden."""
    base: dict = {
        "url": "https://arxiv.org/abs/2401.00001",
        "title": "A Survey",
        "type": "paper",
        "relevance_score": 0.9,
        "language": "en",
        "rationale": "Solid academic reference.",
    }
    if overrides:
        base.update(overrides)
    return base


def _make_sources(
    n: int,
    source_type: str = "article",
    base_url: str = "https://example.com/article-",
) -> list[dict]:
    """Return n source dicts of the given type with unique URLs."""
    return [
        _make_source({"url": f"{base_url}{i}", "type": source_type})
        for i in range(n)
    ]


def _all_200_transport(urls: list[str]) -> httpx.MockTransport:
    """Return a MockTransport that responds 200 to all given URLs."""
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)
    return httpx.MockTransport(_handler)


def _mixed_transport(dead_urls: set[str]) -> httpx.MockTransport:
    """Return a MockTransport responding 404 for dead URLs, 200 for others."""
    def _handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        if any(dead in url_str for dead in dead_urls):
            return httpx.Response(404)
        return httpx.Response(200)
    return httpx.MockTransport(_handler)


def _patch_httpx(transport: httpx.MockTransport):
    """Return a context manager that patches httpx.Client to use the transport."""
    return patch(
        "httpx.Client",
        return_value=httpx.Client(transport=transport),
    )


# ---------------------------------------------------------------------------
# normalize_url
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        # lowercase host
        ("https://ArXiv.ORG/abs/2401.00001", "https://arxiv.org/abs/2401.00001"),
        # strip trailing slash on path root
        ("https://example.com/", "https://example.com"),
        # strip utm_ tracking params
        (
            "https://blog.example.com/post?utm_source=twitter&utm_medium=social",
            "https://blog.example.com/post",
        ),
        # preserve v= for YouTube, strip utm_
        (
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&utm_source=share",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        ),
        # idempotent — already normalized
        (
            "https://arxiv.org/abs/2401.00001",
            "https://arxiv.org/abs/2401.00001",
        ),
        # strip t= param but keep v= for YouTube
        (
            "https://www.youtube.com/watch?v=abc123&t=30s",
            "https://www.youtube.com/watch?v=abc123",
        ),
        # no trailing slash on non-root path
        (
            "https://example.com/article/slug",
            "https://example.com/article/slug",
        ),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    """normalize_url returns the expected canonical form for each input."""
    assert normalize_url(raw) == expected


def test_normalize_url_is_idempotent() -> None:
    """Calling normalize_url twice returns the same result as calling it once."""
    url = "https://Blog.EXAMPLE.com/post?utm_campaign=x"
    once = normalize_url(url)
    twice = normalize_url(once)
    assert once == twice


# ---------------------------------------------------------------------------
# sanity_check_sources — count bounds
# ---------------------------------------------------------------------------

def test_sanity_check_count_min_raises() -> None:
    """sanity_check_sources raises SourcesError(INSUFFICIENT_COUNT) for 4 sources."""
    sources = (
        [_make_source({"type": "paper", "url": "https://arxiv.org/abs/0001"})]
        + _make_sources(1, "youtube", "https://youtube.com/watch?v=v")
        + _make_sources(2, "article", "https://blog.example.com/art-")
    )
    transport = _all_200_transport([s["url"] for s in sources])
    with _patch_httpx(transport):
        with pytest.raises(SourcesError) as exc_info:
            sanity_check_sources(sources)
    assert exc_info.value.code == "INSUFFICIENT_COUNT"


def test_sanity_check_count_exactly_five_passes() -> None:
    """sanity_check_sources accepts exactly 5 sources (lower bound)."""
    sources = (
        [_make_source({"type": "paper", "url": "https://arxiv.org/abs/0001"})]
        + _make_sources(1, "youtube", "https://youtube.com/watch?v=v")
        + _make_sources(3, "article", "https://blog.example.com/art-")
    )
    transport = _all_200_transport([s["url"] for s in sources])
    with _patch_httpx(transport):
        result = sanity_check_sources(sources)
    assert len(result) == 5


def test_sanity_check_count_max_16_truncates_or_raises() -> None:
    """sanity_check_sources handles 16 sources after dedup (truncate or raise)."""
    sources = (
        [_make_source({"type": "paper", "url": "https://arxiv.org/abs/0001",
                       "relevance_score": 0.99})]
        + _make_sources(1, "youtube", "https://youtube.com/watch?v=vid")
        + _make_sources(14, "article", "https://blog.example.com/art-")
    )
    for idx, src in enumerate(sources):
        if src["type"] == "article":
            src["relevance_score"] = round(0.8 - idx * 0.01, 2)
    transport = _all_200_transport([s["url"] for s in sources])
    with _patch_httpx(transport):
        try:
            result = sanity_check_sources(sources)
            assert len(result) <= 15
        except SourcesError as err:
            assert err.code in ("INSUFFICIENT_COUNT", "INSUFFICIENT_DIVERSITY")


# ---------------------------------------------------------------------------
# sanity_check_sources — diversity
# ---------------------------------------------------------------------------

def test_sanity_check_diversity_missing_academic_raises() -> None:
    """INSUFFICIENT_DIVERSITY when no paper source is present."""
    sources = (
        _make_sources(3, "article", "https://blog.example.com/art-")
        + _make_sources(3, "youtube", "https://youtube.com/watch?v=v")
        + _make_sources(2, "video_other", "https://vimeo.com/vid-")
    )
    transport = _all_200_transport([s["url"] for s in sources])
    with _patch_httpx(transport):
        with pytest.raises(SourcesError) as exc_info:
            sanity_check_sources(sources)
    assert exc_info.value.code == "INSUFFICIENT_DIVERSITY"


def test_sanity_check_diversity_missing_video_raises() -> None:
    """INSUFFICIENT_DIVERSITY when neither youtube nor video_other is present."""
    sources = (
        _make_sources(1, "paper", "https://arxiv.org/abs/")
        + _make_sources(7, "article", "https://blog.example.com/art-")
    )
    transport = _all_200_transport([s["url"] for s in sources])
    with _patch_httpx(transport):
        with pytest.raises(SourcesError) as exc_info:
            sanity_check_sources(sources)
    assert exc_info.value.code == "INSUFFICIENT_DIVERSITY"


# ---------------------------------------------------------------------------
# sanity_check_sources — dedup
# ---------------------------------------------------------------------------

def test_sanity_check_dedup_youtube_query_param() -> None:
    """Two YouTube URLs differing only in t= param are deduped to one."""
    base_yt = "https://www.youtube.com/watch?v=abc123"
    sources = [
        _make_source({"url": base_yt, "type": "youtube"}),
        _make_source({"url": base_yt + "&t=10s", "type": "youtube",
                      "title": "Duplicate YouTube"}),
        _make_source({"type": "paper", "url": "https://arxiv.org/abs/0001"}),
        _make_source({"type": "article",
                      "url": "https://blog.example.com/a1"}),
        _make_source({"type": "article",
                      "url": "https://blog.example.com/a2"}),
        _make_source({"type": "article",
                      "url": "https://blog.example.com/a3"}),
        _make_source({"type": "video_other",
                      "url": "https://vimeo.com/12345"}),
    ]
    transport = _all_200_transport([normalize_url(s["url"]) for s in sources])
    with _patch_httpx(transport):
        result = sanity_check_sources(sources)
    result_urls = [str(s.url) for s in result]
    normalized_yt = normalize_url(base_yt)
    assert result_urls.count(normalized_yt) <= 1


# ---------------------------------------------------------------------------
# sanity_check_sources — liveness (dead link handling)
# ---------------------------------------------------------------------------

def test_sanity_check_dead_link_dropped_still_passes() -> None:
    """A single 404 URL is dropped; remaining >=5 sources pass validation."""
    dead_url = "https://dead.example.com/gone"
    live_sources = (
        [_make_source({"type": "paper", "url": "https://arxiv.org/abs/0001"})]
        + _make_sources(1, "youtube", "https://youtube.com/watch?v=vid")
        + _make_sources(5, "article", "https://blog.example.com/art-")
    )
    all_sources = (
        [_make_source({"url": dead_url, "type": "article", "title": "Dead"})]
        + live_sources
    )
    transport = _mixed_transport({dead_url})
    with _patch_httpx(transport):
        result = sanity_check_sources(all_sources)
    result_urls = [str(s.url) for s in result]
    assert not any(dead_url in u for u in result_urls)


def test_sanity_check_dead_link_threshold_exceeded_raises() -> None:
    """DEAD_LINKS_EXCEED_THRESHOLD when half of sources (4/8) are dead."""
    dead_urls = {f"https://dead.example.com/page-{i}" for i in range(4)}
    live_sources = [
        _make_source({"type": "paper", "url": "https://arxiv.org/abs/0001"}),
        _make_source({"type": "youtube", "url": "https://youtube.com/watch?v=v1"}),
        _make_source({"type": "article", "url": "https://blog.example.com/a1"}),
        _make_source({"type": "article", "url": "https://blog.example.com/a2"}),
    ]
    dead_sources = [
        _make_source({"url": u, "type": "article", "title": f"Dead {i}"})
        for i, u in enumerate(dead_urls)
    ]
    transport = _mixed_transport(dead_urls)
    with _patch_httpx(transport):
        with pytest.raises(SourcesError) as exc_info:
            sanity_check_sources(live_sources + dead_sources)
    assert exc_info.value.code in (
        "DEAD_LINKS_EXCEED_THRESHOLD", "INSUFFICIENT_COUNT"
    )


def test_sanity_check_dead_link_dropped_below_min_raises() -> None:
    """INSUFFICIENT_COUNT raised when dead-link removal drops below minimum."""
    dead_urls = {f"https://dead.example.com/p-{i}" for i in range(4)}
    live_sources = [
        _make_source({"type": "paper", "url": "https://arxiv.org/abs/0001"}),
        _make_source({"type": "youtube", "url": "https://youtube.com/watch?v=v1"}),
    ]
    dead_sources = [
        _make_source({"url": u, "type": "article"}) for u in dead_urls
    ]
    transport = _mixed_transport(dead_urls)
    with _patch_httpx(transport):
        with pytest.raises(SourcesError) as exc_info:
            sanity_check_sources(live_sources + dead_sources)
    assert exc_info.value.code in (
        "INSUFFICIENT_COUNT",
        "DEAD_LINKS_EXCEED_THRESHOLD",
        "INSUFFICIENT_DIVERSITY",
    )


# ---------------------------------------------------------------------------
# SourcesError contract
# ---------------------------------------------------------------------------

def test_sources_error_has_code_attribute() -> None:
    """SourcesError instances expose a .code string attribute."""
    err = SourcesError("INSUFFICIENT_COUNT")
    assert hasattr(err, "code")
    assert err.code == "INSUFFICIENT_COUNT"


def test_sources_error_is_exception() -> None:
    """SourcesError is a subclass of Exception and is raise-able."""
    err = SourcesError("TEST_CODE")
    with pytest.raises(SourcesError):
        raise err
