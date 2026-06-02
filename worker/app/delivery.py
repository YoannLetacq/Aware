"""Discord artifact delivery via channel.send (NOT interaction token — critique H3).

Provides two delivery helpers:
- post_failure: send a French error message to the originating channel.
- post_success: attach the generated artifact with a French caption via
  multipart/form-data (Discord Files API).
"""

import pathlib

import httpx
import structlog

from app import config

logger = structlog.get_logger(__name__)

_DISCORD_API_BASE = "https://discord.com/api/v10"


def post_failure(channel_id: str, message_fr: str) -> None:
    """POST a French failure message to the originating Discord channel.

    Uses the bot token (NOT the interaction follow-up webhook) so messages
    survive past the 15-minute interaction window (critique H3). On HTTP
    failure we log and swallow — the worker has already persisted the job
    failure state to Postgres, so a missed Discord post is operational
    noise, not data loss.
    """
    url = f"{_DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = {
        "Authorization": f"Bot {config.DISCORD_BOT_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {"content": message_fr[:2000]}
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=10.0)
        if response.status_code >= 400:
            logger.warning(
                "delivery_post_failure_http_error",
                channel_id=channel_id,
                status_code=response.status_code,
                body=response.text[:200],
            )
        else:
            logger.info("delivery_post_failure_sent", channel_id=channel_id)
    except httpx.HTTPError as exc:
        logger.warning(
            "delivery_post_failure_transport_error",
            channel_id=channel_id,
            error=str(exc),
        )


def post_success(channel_id: str, artifact_path: str, message_fr: str) -> bool:
    """POST the generated artifact with a French caption to the Discord channel.

    Sends a multipart/form-data request attaching the artifact file and a
    payload_json part carrying the caption (truncated to Discord's 2000-char
    limit). The Content-Type boundary is set automatically by httpx — do NOT
    pass it manually.

    channel_id is used VERBATIM from the argument — it comes from the stored
    job context and must never be re-derived (RISK_MANAGEMENT §4.1, CWE-639).

    Returns ``True`` only when the POST succeeded (HTTP status < 400).
    Returns ``False`` — without raising, keeping the worker loop alive — on
    HTTP >=400, httpx.HTTPError, or OSError (e.g. missing artifact file). The
    caller uses this boolean to decide between the terminal 'delivered' and
    'failed' job states (RISK_MANAGEMENT §3.1 — no false success).
    """
    url = f"{_DISCORD_API_BASE}/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {config.DISCORD_BOT_TOKEN}"}
    caption = message_fr[:2000]
    filename = pathlib.Path(artifact_path).name

    try:
        with open(artifact_path, "rb") as artifact_file:
            files = {"files[0]": (filename, artifact_file)}
            data = {"content": caption}
            response = httpx.post(
                url,
                headers=headers,
                files=files,
                data=data,
                timeout=30.0,
            )
        if response.status_code >= 400:
            logger.warning(
                "delivery_post_success_http_error",
                channel_id=channel_id,
                status_code=response.status_code,
                body=response.text[:200],
            )
            return False
        logger.info("delivery_post_success_sent", channel_id=channel_id)
        return True
    except httpx.HTTPError as exc:
        logger.warning(
            "delivery_post_success_transport_error",
            channel_id=channel_id,
            error=str(exc),
        )
        return False
    except OSError as exc:
        logger.warning(
            "delivery_post_success_file_error",
            channel_id=channel_id,
            artifact_path=artifact_path,
            error=str(exc),
        )
        return False
