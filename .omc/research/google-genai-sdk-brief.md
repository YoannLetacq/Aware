# google-genai Python SDK — Reference Brief for gemini.py (Phase 2)

**Retrieved:** 2026-05-26  
**SDK version covered:** google-genai 2.6.0 (released 2026-05-22)  
**Sources:** PyPI, github.com/googleapis/python-genai README, ai.google.dev/gemini-api/docs

---

## 1. Install + Import

```bash
pip install google-genai==2.6.0   # pin in worker/pyproject.toml
```

Canonical import (NOT the legacy `google-generativeai`):

```python
from google import genai
from google.genai import types, errors
```

Python requirement: >= 3.10.  
**Source:** https://pypi.org/project/google-genai/ (retrieved 2026-05-26)

---

## 2. Client Creation

```python
import os
from google import genai

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
```

The worker's `_required()` helper already enforces presence of the env var at
startup. Pass the value directly — never hard-code a fallback.  
**Source:** https://github.com/googleapis/python-genai README (retrieved 2026-05-26)

---

## 3. Structured JSON Output — GenerateContentConfig

The correct parameter name in google-genai 2.x is **`response_json_schema`**
(not `response_schema`). Pair with `response_mime_type="application/json"`.

```python
from google.genai import types

response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=prompt,
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_json_schema=MyPydanticModel.model_json_schema(),
        max_output_tokens=5_000,
    ),
)
```

When the schema is satisfied the SDK parses the JSON and exposes it via
`response.parsed` (typed as the Pydantic model when one was passed).
Fall back to `json.loads(response.text)` when using a dict schema.  
**Source:** https://github.com/googleapis/python-genai README (retrieved 2026-05-26)  
**Source:** https://ai.google.dev/gemini-api/docs/structured-output (retrieved 2026-05-26)

---

## 4. Schema Specification — Sources Array

### Option A — Pydantic (preferred, type-checked)

```python
from enum import Enum
from typing import List
from pydantic import BaseModel, Field

class SourceType(str, Enum):
    ARTICLE = "article"
    PAPER = "paper"
    BLOG = "blog"
    DOCUMENTATION = "documentation"
    VIDEO = "video"
    OTHER = "other"

class Language(str, Enum):
    FR = "fr"
    EN = "en"
    OTHER = "other"

class Source(BaseModel):
    url: str
    title: str
    type: SourceType
    relevance_score: float = Field(ge=0.0, le=1.0)
    language: Language
    rationale: str

class SourcesResponse(BaseModel):
    sources: List[Source]

# Pass to config:
config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_json_schema=SourcesResponse.model_json_schema(),
    max_output_tokens=5_000,
)
```

### Option B — dict schema (no Pydantic dependency)

```python
schema = {
    "type": "OBJECT",
    "properties": {
        "sources": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["url", "title", "type", "relevance_score", "language", "rationale"],
                "properties": {
                    "url":             {"type": "STRING"},
                    "title":           {"type": "STRING"},
                    "type":            {"type": "STRING",
                                        "enum": ["article", "paper", "blog",
                                                 "documentation", "video", "other"]},
                    "relevance_score": {"type": "NUMBER"},
                    "language":        {"type": "STRING", "enum": ["fr", "en", "other"]},
                    "rationale":       {"type": "STRING"},
                },
            },
        }
    },
    "required": ["sources"],
}
```

Pydantic option is strongly preferred: it gives IDE completion and catches
schema drift at import time.

---

## 5. Recommended Model (May 2026)

| Model | Use case |
|---|---|
| `gemini-2.5-flash` | Fast structured output, high-volume, best price/perf |
| `gemini-2.5-pro`   | Complex reasoning, higher quality, higher cost |

For the worker's source classification task, **`gemini-2.5-flash`** is the
right default: low latency, cost-efficient, handles JSON schemas reliably.

**Source:** https://ai.google.dev/gemini-api/docs/models (retrieved 2026-05-26)

---

## 6. Retry + Rate-Limit Handling

The SDK raises two concrete exception types from `google.genai.errors`:

- **`errors.ClientError`** (4xx) — includes 429 RESOURCE_EXHAUSTED
- **`errors.ServerError`** (5xx) — 500, 502, 503, 504

Both inherit from `errors.APIError`. Access `.code` (int) and `.message` (str).

The SDK ships **built-in retry** via `HttpRetryOptions` on the client. Default
constants from `_api_client.py`:

```
attempts=5, initial_delay=1.0s, max_delay=60.0s, exp_base=2,
jitter=1, http_status_codes=(408, 429, 500, 502, 503, 504)
```

The worker's requirements.md specifies `retries=2`. Override built-in retry
and apply your own budget with `tenacity`:

```python
import time
from google.genai import errors

def call_with_retry(client, model, contents, config, retries=2):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=config
            )
        except errors.ClientError as exc:
            if exc.code == 429 and attempt < retries:
                wait = min(4 ** attempt, 60)
                time.sleep(wait)
                last_exc = exc
            else:
                raise
        except errors.ServerError as exc:
            if attempt < retries:
                time.sleep(2 ** attempt)
                last_exc = exc
            else:
                raise
    raise last_exc
```

Or with tenacity (cleaner, matches the SDK internals):

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

def _is_retryable(exc):
    return isinstance(exc, (errors.ClientError, errors.ServerError)) and \
           exc.code in (429, 500, 502, 503, 504)

@retry(stop=stop_after_attempt(3),   # 1 initial + 2 retries
       wait=wait_exponential(multiplier=1, min=1, max=60),
       retry=retry_if_exception(_is_retryable))
def _generate(client, model, contents, config):
    return client.models.generate_content(
        model=model, contents=contents, config=config
    )
```

**Source:** https://github.com/googleapis/python-genai `_api_client.py` (retrieved 2026-05-26)  
**Source:** https://github.com/googleapis/python-genai/issues/1875 (retrieved 2026-05-26)

---

## 7. Cost Ceiling — 50k Input + 5k Output

Enforce via `max_output_tokens` in `GenerateContentConfig`. The input side
is controlled by what you send (truncate or summarise the transcript before
calling). The SDK does not expose a max_input_tokens guard — that constraint
must be applied by the caller before building `contents`.

```python
config = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_json_schema=SourcesResponse.model_json_schema(),
    max_output_tokens=5_000,   # hard ceiling per requirements.md §Cost ceiling
)
```

---

## 8. Token Usage in Response

```python
response = client.models.generate_content(...)

meta = response.usage_metadata
prompt_tokens    = meta.prompt_token_count      # int
candidate_tokens = meta.candidates_token_count  # int
total_tokens     = meta.total_token_count       # int (prompt + candidates)
```

Log these after every call to feed the cost-tracking system.  
**Source:** https://ai.google.dev/api/generate-content#v1beta.GenerateContentResponse (retrieved 2026-05-26)

---

## 9. Async Support

`google-genai` ships an async client accessible via `client.aio`:

```python
response = await client.aio.models.generate_content(...)
```

The worker runs a **single-threaded BRPOP loop** — sync is correct and simpler.
Use `client.models.generate_content(...)` (sync). No async overhead needed.

---

## 10. Common Pitfalls

**A. Empty `response.text`**  
Occurs when the model returns no candidates or the first candidate has empty
content. Always guard:

```python
if not response.candidates:
    raise ValueError("No candidates in Gemini response")
text = response.text  # raises if text is None/empty — wrap as needed
```

**B. MAX_TOKENS truncation (truncated JSON)**  
Check `finish_reason` before parsing:

```python
from google.genai.types import FinishReason

candidate = response.candidates[0]
if candidate.finish_reason == FinishReason.MAX_TOKENS:
    raise ValueError("Gemini response truncated: increase max_output_tokens or shorten input")
```

Truncated JSON will cause `json.loads()` / Pydantic parse to fail with a
cryptic error — catching finish_reason first gives a clear error message.

**C. Safety-blocked output**  
When the prompt itself is blocked, `response.prompt_feedback.block_reason`
is set and `response.candidates` is empty:

```python
if response.prompt_feedback and response.prompt_feedback.block_reason:
    raise ValueError(
        "Prompt blocked by Gemini safety filter: %s",
        response.prompt_feedback.block_reason
    )
```

When a candidate is blocked mid-generation, `finish_reason == FinishReason.SAFETY`.

**FinishReason enum values:** `STOP` (normal), `MAX_TOKENS`, `SAFETY`,
`RECITATION`, `OTHER`.  
**Source:** https://ai.google.dev/api/generate-content#v1beta.GenerateContentResponse (retrieved 2026-05-26)

---

## Recommended Worker Call Pattern

Canonical 15-line Python skeleton the executor can adapt for `gemini.py`:

```python
"""Gemini structured-output call for source classification."""

import os
import json
import logging
from google import genai
from google.genai import types, errors
from google.genai.types import FinishReason

logger = logging.getLogger(__name__)

_CLIENT = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
_MODEL  = "gemini-2.5-flash"
_CONFIG = types.GenerateContentConfig(
    response_mime_type="application/json",
    response_json_schema=SourcesResponse.model_json_schema(),  # defined in §4
    max_output_tokens=5_000,
)


def classify_sources(prompt: str) -> SourcesResponse:
    """Call Gemini to classify sources; return validated SourcesResponse."""
    response = _call_with_retry(prompt)
    _check_finish_reason(response)
    _check_safety(response)
    data = json.loads(response.text)
    result = SourcesResponse.model_validate(data)
    _log_usage(response.usage_metadata)
    return result


def _call_with_retry(prompt: str, retries: int = 2):
    """Invoke generate_content with exponential backoff on 429/5xx."""
    last_exc = None
    for attempt in range(retries + 1):
        try:
            return _CLIENT.models.generate_content(
                model=_MODEL, contents=prompt, config=_CONFIG
            )
        except errors.ClientError as exc:
            if exc.code == 429 and attempt < retries:
                import time
                time.sleep(min(4 ** attempt, 60))
                last_exc = exc
            else:
                raise
        except errors.ServerError as exc:
            if attempt < retries:
                import time
                time.sleep(2 ** attempt)
                last_exc = exc
            else:
                raise
    raise last_exc


def _check_finish_reason(response) -> None:
    """Raise on truncated or safety-stopped responses."""
    if not response.candidates:
        raise ValueError("No candidates returned by Gemini")
    reason = response.candidates[0].finish_reason
    if reason == FinishReason.MAX_TOKENS:
        raise ValueError("Gemini response truncated: raise max_output_tokens or shorten input")
    if reason == FinishReason.SAFETY:
        raise ValueError("Gemini candidate blocked by safety filter")


def _check_safety(response) -> None:
    """Raise if the prompt itself was blocked."""
    fb = response.prompt_feedback
    if fb and fb.block_reason:
        raise ValueError("Prompt blocked by Gemini: %s" % fb.block_reason)


def _log_usage(meta) -> None:
    """Log token counts for cost tracking."""
    logger.info(
        "gemini usage: prompt=%s candidates=%s total=%s",
        meta.prompt_token_count,
        meta.candidates_token_count,
        meta.total_token_count,
    )
```

**Notes for executor:**
- Import `_required()` from the worker's config module for the API key rather than raw `os.environ`.
- `_CLIENT` and `_CONFIG` are module-level singletons — instantiate once.
- The `import time` inside the retry loop violates AGENT_CONDUCT §1.2 (no lazy imports). Move `import time` to module top before committing.
- Pylint 10/10 requires module and class docstrings; lazy %-format logger calls (shown above).
