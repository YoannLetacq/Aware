"""Discord slash-command definitions — /podcast command.

Registers /podcast with subject, mode, and style parameters.
Style choices are loaded at import time from the configured styles JSON file.
All user-facing strings are in French per AGENT_CONDUCT §1.5.
"""

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

import discord
import httpx
import structlog
from discord import app_commands

from app import config, validate, webhook_client

logger = structlog.get_logger(__name__)
_stdlib_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Static choices
# ---------------------------------------------------------------------------

_MODE_CHOICES: list[app_commands.Choice[str]] = [
    app_commands.Choice(name="Podcast", value="podcast"),
    app_commands.Choice(name="Vidéo", value="video"),
]


def _load_style_choices() -> list[app_commands.Choice[str]]:
    """Load style choices from the configured JSON file.

    Returns an empty list and logs a warning if the file is missing or
    malformed — the command will still register without style autocompletion.
    """
    path = config.NOTEBOOKLM_STYLES_PATH
    if not os.path.exists(path):
        _stdlib_logger.warning(
            "styles file not found, style choices will be empty: %s", path
        )
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        styles: list[str] = data.get("styles", [])
        return [app_commands.Choice(name=s, value=s) for s in styles]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        _stdlib_logger.warning(
            "failed to load styles from %s: %s", path, exc
        )
        return []


_STYLE_CHOICES: list[app_commands.Choice[str]] = _load_style_choices()
_ALLOWED_STYLES: list[str] = [c.value for c in _STYLE_CHOICES]

# ---------------------------------------------------------------------------
# Command tree setup
# ---------------------------------------------------------------------------

_intents = discord.Intents.default()
_client = discord.Client(intents=_intents)
tree = app_commands.CommandTree(_client)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _authorize(interaction: discord.Interaction) -> bool:
    """Return True if the user is allowed to run /podcast.

    When DISCORD_ALLOWED_AUTHORS is empty/unset every user is allowed.
    """
    if not config.DISCORD_ALLOWED_AUTHORS:
        return True
    allowed_ids = [uid.strip() for uid in config.DISCORD_ALLOWED_AUTHORS.split(",")]
    return str(interaction.user.id) in allowed_ids


def _validate_input(
    subject: str,
    mode: app_commands.Choice[str],
    style: Optional[app_commands.Choice[str]],
) -> tuple:
    """Validate subject, mode, and style.

    Returns (subject_clean, mode_clean, style_clean) on success,
    or (None, french_error_message, None) on failure.
    """
    try:
        subject_clean = validate.validate_subject(subject)
    except validate.SubjectError as exc:
        return (None, str(exc), None)

    mode_value = mode.value
    style_value = style.value if style is not None else None
    try:
        mode_clean, style_clean = validate.validate_mode_style(
            mode_value, style_value, _ALLOWED_STYLES
        )
    except validate.ModeError as exc:
        return (None, str(exc), None)

    return (subject_clean, mode_clean, style_clean)


def _build_payload(
    interaction: discord.Interaction,
    subject_clean: str,
    mode_clean: str,
    style_clean: Optional[str],
) -> dict:
    """Construct the §3.1 trigger payload."""
    subject_hash = hashlib.sha256(
        subject_clean.lower().strip().encode("utf-8")
    ).hexdigest()
    guild_id = str(interaction.guild_id) if interaction.guild_id is not None else None
    return {
        "interaction_id": str(interaction.id),
        "user_id": str(interaction.user.id),
        "channel_id": str(interaction.channel_id),
        "guild_id": guild_id,
        "locale": "fr",
        "subject": subject_clean,
        "subject_hash": subject_hash,
        "mode": mode_clean,
        "style": style_clean,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _post_and_ack(interaction: discord.Interaction, payload: dict) -> None:
    """POST payload to n8n webhook and send a followup acknowledgement."""
    try:
        status_code = await webhook_client.post_trigger(payload)
    except httpx.HTTPError as exc:
        logger.error(
            "webhook_post_failed",
            interaction_id=str(interaction.id),
            error=str(exc),
        )
        await interaction.followup.send(
            "Erreur interne, réessayez plus tard.", ephemeral=True
        )
        return

    if status_code < 200 or status_code >= 300:
        logger.error(
            "webhook_non_2xx",
            interaction_id=str(interaction.id),
            status_code=status_code,
        )
        await interaction.followup.send(
            "Erreur interne, réessayez plus tard.", ephemeral=True
        )
        return

    await interaction.followup.send(
        "Reçu — génération en cours. Cela peut prendre jusqu'à 15 minutes.",
        ephemeral=True,
    )


# ---------------------------------------------------------------------------
# /podcast command
# ---------------------------------------------------------------------------

@tree.command(
    name="podcast",
    description="Génère un podcast ou une vidéo NotebookLM à partir d'un sujet.",
)
@app_commands.describe(
    subject="Sujet précis en 1–2 phrases (40–400 caractères).",
    mode="Mode de génération : podcast audio ou vidéo.",
    style="Style visuel (obligatoire pour le mode vidéo).",
)
@app_commands.choices(mode=_MODE_CHOICES, style=_STYLE_CHOICES)
async def podcast_command(
    interaction: discord.Interaction,
    subject: str,
    mode: app_commands.Choice[str],
    style: Optional[app_commands.Choice[str]] = None,
) -> None:
    """Handle the /podcast slash command.

    Defers immediately, validates inputs, then posts the trigger payload to n8n.
    """
    await interaction.response.defer(ephemeral=True)

    if not _authorize(interaction):
        await interaction.followup.send(
            "Vous n'êtes pas autorisé à utiliser cette commande.",
            ephemeral=True,
        )
        return

    subject_clean, mode_clean, style_clean = _validate_input(subject, mode, style)
    if subject_clean is None:
        await interaction.followup.send(mode_clean, ephemeral=True)
        return

    payload = _build_payload(interaction, subject_clean, mode_clean, style_clean)
    await _post_and_ack(interaction, payload)


def get_client() -> discord.Client:
    """Return the discord.Client instance owned by this module."""
    return _client


def get_tree() -> app_commands.CommandTree:
    """Return the CommandTree instance for slash-command registration."""
    return tree
