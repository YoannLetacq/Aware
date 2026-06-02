"""Subject and input validation -- length, sentence count, strip rules.

Guards against prompt injection (critique M1): strips mention tags, plain-text
mass-mention keywords (@everyone, @here), backticks, and zero-width characters
before forwarding to n8n.

All functions are pure with zero side effects.
"""

import re
import unicodedata

# Regex for Discord mention and channel reference tags. Covers all four forms:
#   <@USER_ID>   — plain user mention
#   <@!USER_ID>  — nickname-form user mention
#   <@&ROLE_ID>  — role mention
#   <#CHANNEL_ID> — channel reference
_RE_MENTION = re.compile(r"<[@#](?:[!&])?\d+>")

# Plain-text Discord mass-mention keywords that bypass bracket-form stripping.
# Case-insensitive to catch @Everyone, @HERE, etc.
_RE_AT_TEXT = re.compile(r"@(?:everyone|here)\b", re.IGNORECASE)

# Zero-width and invisible Unicode characters:
# U+0000 (null byte)
# U+200B-U+200F (zero-width space through right-to-left mark)
# U+2028-U+202F (line/paragraph separators and formatting chars)
# U+2060 (word joiner)
# U+FEFF (byte-order mark / zero-width no-break space)
_RE_ZERO_WIDTH = re.compile(
    "[\x00\u200b-\u200f\u2028-\u202f\u2060\ufeff]"
)

# Sentence boundary: punctuation [.!?] followed by whitespace or end of string
_RE_SENTENCE_BOUNDARY = re.compile(r"[.!?](?:\s|$)")


class SubjectError(ValueError):
    """Raised when a subject fails validation rules.

    Attributes:
        code: Machine-readable English error code.
    """

    def __init__(self, message: str, code: str) -> None:
        """Initialise with a French user message and an English error code."""
        super().__init__(message)
        self.code = code


class ModeError(ValueError):
    """Raised when mode/style combination is invalid.

    Attributes:
        code: Machine-readable English error code.
    """

    def __init__(self, message: str, code: str) -> None:
        """Initialise with a French user message and an English error code."""
        super().__init__(message)
        self.code = code


def strip_subject(text: str) -> str:
    """Remove Discord artefacts and normalise whitespace from *text*.

    Removes:
    - Discord mention tags: ``<@USER_ID>`` (plain), ``<@!USER_ID>`` (nickname),
      ``<@&ROLE_ID>`` (role), and ``<#CHANNEL_ID>`` (channel reference).
    - Plain-text mass-mention keywords: ``@everyone``, ``@here`` (case-insensitive).
    - Backtick characters.
    - Zero-width and invisible Unicode characters (U+0000, U+200B-U+200F,
      U+2028-U+202F, U+2060, U+FEFF).

    Normalises:
    - Runs of whitespace collapsed to a single space.
    - Leading/trailing whitespace trimmed.

    Returns the cleaned string.
    """
    text = _RE_MENTION.sub("", text)
    text = _RE_AT_TEXT.sub("", text)
    text = _RE_ZERO_WIDTH.sub("", text)
    text = text.replace("`", "")
    text = unicodedata.normalize("NFC", text)
    # Collapse any whitespace run (space, tab, non-breaking space, etc.) to a single space
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def count_sentences(text: str) -> int:
    """Count sentences in *text* by splitting on terminal punctuation.

    Splits on ``.``, ``!``, or ``?`` that is followed by whitespace or end of
    string. Ignores trailing punctuation that is not followed by content.
    Always returns at least 1 for any non-empty string.

    Returns an integer >= 1.
    """
    stripped = text.strip()
    if not stripped:
        return 0
    # Count sentence-terminating punctuation followed by whitespace or EOS
    boundaries = _RE_SENTENCE_BOUNDARY.findall(stripped)
    if not boundaries:
        # No terminal punctuation found -- treat whole text as one sentence
        return 1
    # Check whether the last sentence has no terminal punctuation
    trailing = re.search(r"[.!?]\s*$", stripped)
    count = len(boundaries)
    if trailing is None:
        # Last sentence has no terminal punctuation -- add 1 for it
        count += 1
    return max(1, count)


def validate_subject(text: str) -> str:
    """Validate *text* as a podcast subject and return the cleaned version.

    Applies :func:`strip_subject` first, then enforces:
    - Length 40 <= len <= 400.
    - Sentence count 1 <= sentences <= 2.

    Raises:
        SubjectError: With a French message and an English ``code`` attribute
            when any rule is violated.

    Returns the cleaned subject string on success.
    """
    if not text or not text.strip():
        raise SubjectError(
            "Le sujet ne peut pas être vide.",
            "SUBJECT_EMPTY",
        )

    cleaned = strip_subject(text)

    if not cleaned:
        raise SubjectError(
            "Le sujet ne peut pas être vide.",
            "SUBJECT_EMPTY",
        )

    if len(cleaned) < 40:
        raise SubjectError(
            "Le sujet est trop court (minimum 40 caractères). "
            "Veuillez formuler votre sujet en 1 à 2 phrases précises.",
            "SUBJECT_TOO_SHORT",
        )

    if len(cleaned) > 400:
        raise SubjectError(
            "Le sujet est trop long (maximum 400 caractères). "
            "Veuillez résumer votre sujet en 1 à 2 phrases.",
            "SUBJECT_TOO_LONG",
        )

    sentences = count_sentences(cleaned)
    if sentences > 2:
        raise SubjectError(
            "Le sujet contient trop de phrases (maximum 2 phrases autorisées). "
            "Veuillez formuler votre sujet en 1 à 2 phrases précises.",
            "SUBJECT_TOO_MANY_SENTENCES",
        )

    return cleaned


def validate_mode_style(
    mode: str,
    style: str | None,
    allowed_styles: list[str],
) -> tuple[str, str | None]:
    """Validate the mode/style combination and return (mode, effective_style).

    Rules:
    - ``mode`` must be ``"podcast"`` or ``"video"``.
    - For ``mode="video"``: ``style`` must be present and in *allowed_styles*.
    - For ``mode="podcast"``: ``style`` is silently dropped (ignored).

    Raises:
        ModeError: With a French message and an English ``code`` attribute
            when ``mode`` is invalid, or when ``mode="video"`` and ``style``
            is missing or not in *allowed_styles*.

    Returns a ``(mode, style)`` tuple where ``style`` is ``None`` for podcast mode.
    """
    if mode not in ("podcast", "video"):
        raise ModeError(
            "Mode invalide. Veuillez choisir « podcast » ou « vidéo ».",
            "MODE_INVALID",
        )

    if mode == "podcast":
        return mode, None

    # mode == "video"
    if style is None or style == "":
        raise ModeError(
            "Le style est obligatoire pour le mode vidéo. "
            "Veuillez sélectionner un style dans la liste.",
            "STYLE_REQUIRED",
        )

    if style not in allowed_styles:
        raise ModeError(
            "Style invalide. Veuillez sélectionner un style dans la liste proposée.",
            "STYLE_INVALID",
        )

    return mode, style
