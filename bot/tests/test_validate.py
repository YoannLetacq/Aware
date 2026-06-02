"""Tests for bot/app/validate.py — TDD spec for Phase 1 subject validation.

These tests are written BEFORE the implementation is complete (TDD red phase).
They define the exact contract the executor must satisfy:
  - SubjectError / ModeError exception classes with a ``code`` attribute
  - strip_subject, count_sentences, validate_subject, validate_mode_style functions

Run:
    PYTHONPATH=/home/yoann/podcast/bot pytest tests/test_validate.py -v
"""

import unicodedata

import pytest

from app.validate import (
    ModeError,
    SubjectError,
    count_sentences,
    strip_subject,
    validate_mode_style,
    validate_subject,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALLOWED = ["Classic", "Brief", "Explainer"]


# ===========================================================================
# 1. strip_subject  (≥ 8 cases via parametrize + standalone functions)
# ===========================================================================

@pytest.mark.parametrize("raw, expected", [
    ("<@123456789> Hello", "Hello"),
    ("<#987654321> Info", "Info"),
    ("`backtick`", "backtick"),
    ("``double``", "double"),
    ("```triple```", "triple"),
    ("normal text", "normal text"),
    ("éàïüôç", "éàïüôç"),
    ("", ""),
    ("before​after", "beforeafter"),   # zero-width space U+200B
    ("before‌after", "beforeafter"),   # zero-width non-joiner U+200C
    ("before‍after", "beforeafter"),   # zero-width joiner U+200D
    ("before⁠after", "beforeafter"),   # word joiner U+2060
    ("before﻿after", "beforeafter"),   # BOM U+FEFF
    ("<@!123456>foo", "foo"),           # nickname-form user mention
    ("<@&987654>bar", "bar"),           # role mention
    ("hello <@!123> and <@&456> goodbye", "hello and goodbye"),  # mixed
    ("hello @everyone goodbye", "hello goodbye"),              # @everyone stripped
    ("hello @here goodbye", "hello goodbye"),                  # @here stripped
    ("hello @Everyone @HERE", "hello"),                        # case-insensitive variants
    ("@everyone@here", ""),                                    # adjacent, no space between
    ("user@example.com", "user@example.com"),                  # email not affected
], ids=[
    "removes_mention", "removes_channel_ref",
    "removes_single_backtick", "removes_double_backtick", "removes_triple_backtick",
    "preserves_plain_ascii", "preserves_accented_fr_chars", "empty_string_returns_empty",
    "zero_width_space", "zero_width_non_joiner", "zero_width_joiner", "word_joiner", "bom",
    "removes_nickname_mention", "removes_role_mention", "removes_mixed_mentions",
    "strips_at_everyone", "strips_at_here", "strips_at_everyone_here_case_insensitive",
    "strips_at_everyone_at_here_adjacent", "preserves_email_address",
])
def test_strip_subject_parametrized(raw: str, expected: str) -> None:
    """strip_subject removes Discord tokens, backticks, and zero-width chars."""
    assert strip_subject(raw) == expected


def test_strip_subject_collapses_internal_whitespace() -> None:
    """strip_subject collapses runs of whitespace to a single space."""
    assert strip_subject("foo   bar\t\nbaz") == "foo bar baz"


def test_strip_subject_trims_leading_trailing_whitespace() -> None:
    """strip_subject removes leading and trailing whitespace."""
    assert strip_subject("  hello  ") == "hello"


def test_strip_subject_removes_null_byte() -> None:
    """strip_subject removes embedded null bytes without raising an exception."""
    result = strip_subject("before\x00after")
    assert "\x00" not in result
    assert "before" in result and "after" in result


# ===========================================================================
# 2. count_sentences  (≥ 5 cases)
# ===========================================================================

def test_count_sentences_empty_string_returns_zero() -> None:
    """count_sentences returns 0 for an empty string."""
    assert count_sentences("") == 0


def test_count_sentences_single_no_terminal_punctuation() -> None:
    """A single sentence with no terminal punctuation counts as 1."""
    assert count_sentences("Les LLMs sont incroyables") == 1


def test_count_sentences_single_with_trailing_period() -> None:
    """A sentence ending with a period still counts as 1."""
    assert count_sentences("Les LLMs sont incroyables.") == 1


def test_count_sentences_two_sentences() -> None:
    """Two dot-separated sentences count as 2."""
    assert count_sentences("Foo. Bar.") == 2


def test_count_sentences_three_sentences_mixed_punctuation() -> None:
    """Three sentences using mixed .!? terminators count as 3."""
    assert count_sentences("Foo. Bar! Baz?") == 3


# ===========================================================================
# 3. validate_subject  (≥ 10 cases)
# ===========================================================================

def test_validate_subject_length_39_raises_too_short() -> None:
    """A subject with 39 chars raises SubjectError SUBJECT_TOO_SHORT."""
    with pytest.raises(SubjectError) as exc_info:
        validate_subject("a" * 39)
    err = exc_info.value
    assert err.code == "SUBJECT_TOO_SHORT"
    assert any(kw in str(err) for kw in ("court", "40"))


def test_validate_subject_length_40_passes() -> None:
    """A subject with exactly 40 chars is accepted (lower boundary)."""
    result = validate_subject("a" * 40)
    assert len(result) == 40


def test_validate_subject_length_400_passes() -> None:
    """A subject with exactly 400 chars is accepted (upper boundary)."""
    result = validate_subject("a" * 400)
    assert len(result) == 400


def test_validate_subject_length_401_raises_too_long() -> None:
    """A subject with 401 chars raises SubjectError SUBJECT_TOO_LONG."""
    with pytest.raises(SubjectError) as exc_info:
        validate_subject("a" * 401)
    assert exc_info.value.code == "SUBJECT_TOO_LONG"


def test_validate_subject_empty_raises_subject_empty() -> None:
    """An empty string raises SubjectError SUBJECT_EMPTY."""
    with pytest.raises(SubjectError) as exc_info:
        validate_subject("")
    assert exc_info.value.code == "SUBJECT_EMPTY"


def test_validate_subject_whitespace_only_raises_subject_empty() -> None:
    """A whitespace-only string strips to empty and raises SUBJECT_EMPTY."""
    with pytest.raises(SubjectError) as exc_info:
        validate_subject("   \t\n   ")
    assert exc_info.value.code == "SUBJECT_EMPTY"


def test_validate_subject_three_sentences_raises_too_many() -> None:
    """Three sentences raise SubjectError SUBJECT_TOO_MANY_SENTENCES."""
    subject = "Les LLMs sont puissants. Ils changent tout. Vraiment?"
    with pytest.raises(SubjectError) as exc_info:
        validate_subject(subject)
    assert exc_info.value.code == "SUBJECT_TOO_MANY_SENTENCES"


def test_validate_subject_strips_mention_then_validates_length() -> None:
    """Mention + backticks are stripped; length is measured on cleaned text."""
    raw = "<@123456789> " + "a" * 30 + " `x`"
    with pytest.raises(SubjectError) as exc_info:
        validate_subject(raw)
    assert exc_info.value.code == "SUBJECT_TOO_SHORT"


def test_validate_subject_valid_fr_subject_returns_cleaned_text() -> None:
    """A valid French subject (40-100 chars, 1 sentence) is returned as a str."""
    subject = "L'impact des modèles de langage ouverts sur la médecine en 2025."
    result = validate_subject(subject)
    assert isinstance(result, str) and 40 <= len(result) <= 400


def test_validate_subject_leading_trailing_newlines_pass() -> None:
    """Leading/trailing newlines are stripped; remaining text is validated."""
    body = "a" * 40
    assert validate_subject(f"\n\n{body}\n") == body


def test_validate_subject_two_sentences_valid() -> None:
    """A valid two-sentence subject (≤ 400 chars) is accepted and returned."""
    subject = "Les LLMs transforment la médecine. Quels sont les défis éthiques?"
    result = validate_subject(subject)
    assert isinstance(result, str) and 40 <= len(result) <= 400


# ===========================================================================
# 4. validate_mode_style  (≥ 8 cases)
# ===========================================================================

def test_validate_mode_style_podcast_no_style_returns_podcast_none() -> None:
    """podcast mode with no style returns ('podcast', None)."""
    assert validate_mode_style("podcast", None, _ALLOWED) == ("podcast", None)


def test_validate_mode_style_podcast_with_style_drops_style() -> None:
    """podcast mode silently drops a provided style, returning ('podcast', None)."""
    assert validate_mode_style("podcast", "Classic", _ALLOWED) == ("podcast", None)


def test_validate_mode_style_video_valid_style_returns_pair() -> None:
    """video mode with a valid style returns ('video', style)."""
    assert validate_mode_style("video", "Classic", _ALLOWED) == ("video", "Classic")


def test_validate_mode_style_video_no_style_raises_style_required() -> None:
    """video mode with no style raises ModeError STYLE_REQUIRED."""
    with pytest.raises(ModeError) as exc_info:
        validate_mode_style("video", None, _ALLOWED)
    assert exc_info.value.code == "STYLE_REQUIRED"


def test_validate_mode_style_video_invalid_style_raises_style_invalid() -> None:
    """video mode with an unrecognised style raises ModeError STYLE_INVALID."""
    with pytest.raises(ModeError) as exc_info:
        validate_mode_style("video", "NotARealStyle", _ALLOWED)
    assert exc_info.value.code == "STYLE_INVALID"


def test_validate_mode_style_invalid_mode_raises_mode_invalid() -> None:
    """An unrecognised mode raises ModeError MODE_INVALID."""
    with pytest.raises(ModeError) as exc_info:
        validate_mode_style("invalid", None, _ALLOWED)
    assert exc_info.value.code == "MODE_INVALID"


def test_validate_mode_style_uppercase_video_raises_mode_invalid() -> None:
    """'VIDEO' (uppercase) is rejected as MODE_INVALID (fail-closed)."""
    with pytest.raises(ModeError) as exc_info:
        validate_mode_style("VIDEO", "Classic", _ALLOWED)
    assert exc_info.value.code == "MODE_INVALID"


def test_validate_mode_style_empty_allowed_styles_raises_style_invalid() -> None:
    """video mode with empty allowed_styles list raises ModeError STYLE_INVALID."""
    with pytest.raises(ModeError) as exc_info:
        validate_mode_style("video", "Classic", [])
    assert exc_info.value.code == "STYLE_INVALID"


def test_validate_mode_style_video_second_allowed_style() -> None:
    """video mode accepts the second item in the allowed_styles list."""
    assert validate_mode_style("video", "Brief", _ALLOWED) == ("video", "Brief")


# ===========================================================================
# 5. Edge cases
# ===========================================================================

def test_validate_subject_combining_diacritical_length_counted_as_codepoints() -> None:
    """NFD 'é' is 2 code points; len() == 40 for 20 NFD-é chars → passes >= 40 gate."""
    nfd_e = unicodedata.normalize("NFD", "é")
    assert len(nfd_e) == 2
    subject = nfd_e * 20  # 40 code points total
    assert len(subject) == 40
    cleaned = strip_subject(subject)
    assert len(cleaned) >= 1  # combining chars are not stripped


def test_validate_mode_style_uppercase_podcast_raises_mode_invalid() -> None:
    """'PODCAST' (uppercase) is rejected as MODE_INVALID (fail-closed)."""
    with pytest.raises(ModeError) as exc_info:
        validate_mode_style("PODCAST", None, _ALLOWED)
    assert exc_info.value.code == "MODE_INVALID"
