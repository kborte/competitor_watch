"""Shared Gemini call wrapper for the crawler's two model calls.

Applies the retry policy and reads token usage in one place, so discover.py and
structure.py differ only in the prompt and the response schema. Deliberately not
imported from the backend, which has its own copy: the two are deployed
separately and agree on behaviour, not on code.
"""

import logging
import time

from . import config

log = logging.getLogger(__name__)

# Statuses worth another attempt: rate limiting and transient unavailability.
# Anything else — a bad key, a malformed request — fails identically on every
# retry, so retrying only delays the error and burns quota.
RETRYABLE_STATUSES = (429, 500, 502, 503, 504)


def status_of(exc: Exception) -> int | None:
    """HTTP status carried by a Gemini SDK error, or None if it isn't one."""
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def usage_of(response) -> dict:
    """Token counts for one response, empty when the SDK reports none."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {}
    return {
        "input_tokens": getattr(usage, "prompt_token_count", None),
        "output_tokens": getattr(usage, "candidates_token_count", None),
        "total_tokens": getattr(usage, "total_token_count", None),
    }


def generate(client, *, model: str, contents: str, request_config, label: str):
    """Calls the model, retrying only transient failures with linear backoff."""
    last: Exception | None = None
    for attempt in range(1, config.LLM_MAX_ATTEMPTS + 1):
        try:
            return client.models.generate_content(
                model=model, contents=contents, config=request_config,
            )
        except Exception as exc:
            status = status_of(exc)
            if status not in RETRYABLE_STATUSES or attempt == config.LLM_MAX_ATTEMPTS:
                raise
            last = exc
            delay = config.LLM_BACKOFF_SECONDS * attempt
            log.warning(
                "[%s] attempt %d/%d failed with %s, retrying in %.1fs",
                label, attempt, config.LLM_MAX_ATTEMPTS, status, delay,
            )
            time.sleep(delay)
    raise last  # unreachable: the loop either returns or raises
