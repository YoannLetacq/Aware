"""HTTP client for POSTing Discord trigger payloads to the n8n webhook.

Uses httpx.AsyncClient with a 5-second timeout and Bearer authentication.
Raises httpx.HTTPError on transport failure — callers are responsible for
catching and handling that exception.
"""

import httpx
import structlog

from app import config

logger = structlog.get_logger(__name__)


async def post_trigger(payload: dict) -> int:
    """POST *payload* as JSON to the n8n webhook and return the HTTP status code.

    Sends an ``Authorization: Bearer <WORKER_SHARED_TOKEN>`` header.
    Logs one info event per call.  Never logs the token value.

    Args:
        payload: The trigger payload dict (see ARCHITECTURE.md §3.1).

    Returns:
        The HTTP response status code (e.g. 200, 202).

    Raises:
        httpx.HTTPError: On any transport-level failure (connection refused,
            timeout, etc.).  Non-2xx HTTP responses are returned as status
            codes — the caller decides whether to treat them as errors.
    """
    interaction_id = payload.get("interaction_id", "unknown")
    logger.info(
        "bot_post_trigger",
        interaction_id=interaction_id,
        url=config.N8N_WEBHOOK_URL,
    )

    headers = {
        "Authorization": f"Bearer {config.WORKER_SHARED_TOKEN}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            config.N8N_WEBHOOK_URL,
            json=payload,
            headers=headers,
        )

    return response.status_code
