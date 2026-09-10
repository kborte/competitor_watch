"""The one LLM call in the backend: judging a single finding.

No agent, no tools, no loop — structured output forces the verdict fields
directly. Primarily a materiality judge, it also re-reads the crawler's category
as a second opinion and reports whether the excerpt really supports the summary.
Only findings that survive dedup and are not QIC reference rows get here
(ingest.py), so classifications are sparse relative to findings.
"""

import logging
import time

from google import genai
from google.genai import types

from . import config
from .schemas import Classification

log = logging.getLogger(__name__)

client = genai.Client()  # reads GEMINI_API_KEY from the environment

MODEL = config.GEMINI_MODEL

# Statuses worth another attempt: rate limiting and transient unavailability.
# Everything else — a bad key, a malformed request — fails the same way on every
# retry, so retrying only delays the error and spends quota.
_RETRYABLE_STATUSES = (429, 500, 502, 503, 504)

# The category bucket definitions are condensed from the crawler's fuller
# taxonomy (research_crawler/structure.py). Without them the model would still
# be constrained to the eight enum values by the response schema, but would be
# choosing among them with no idea what they mean.
PROMPT_TEMPLATE = """A competitor-watch routine found this item. Classify it.

Company: {company}
Category (as tagged by the routine): {category}
Title: {title}
Summary (routine's paraphrase): {summary}
Verbatim excerpt from the source: "{source_excerpt}"

Judge:
- category: the factual bucket this belongs in. The routine's tag above is a starting point,
  not an answer — pick the one that actually fits:
  - product: a change to what's offered — coverage, features, pricing structure.
  - marketing: campaigns, promotions, sponsorships, brand pushes.
  - news: general press coverage not covered by a more specific bucket.
  - social_sentiment: reviews, social media, forum mentions.
  - regulatory: about compliance/licensing/conduct itself — a regulator merely being
    involved is not enough.
  - investment_or_acquisition: M&A, stake changes, funding, new subsidiaries.
  - financial_results: earnings, profit/loss, dividends, capital raises — still financial
    even when a regulator had to approve the raise.
  - other: fits none of the above.
- materiality: how much this matters competitively (low / medium / high)
- confidence: your confidence in this classification, 0 to 1
- grounded: does the excerpt actually support the summary, or does the summary overstate or misread it
- evidence_quote: the exact span from the excerpt that supports your materiality judgment
- rationale: one sentence on why
"""


def _status_of(exc: Exception) -> int | None:
    """HTTP status carried by a Gemini SDK error, or None if it isn't one."""
    for attr in ("code", "status_code"):
        value = getattr(exc, attr, None)
        if isinstance(value, int):
            return value
    response = getattr(exc, "response", None)
    value = getattr(response, "status_code", None)
    return value if isinstance(value, int) else None


def _usage_of(response) -> dict:
    """Token counts for one response, empty when the SDK reports none."""
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return {}
    return {
        "input_tokens": getattr(usage, "prompt_token_count", None),
        "output_tokens": getattr(usage, "candidates_token_count", None),
        "total_tokens": getattr(usage, "total_token_count", None),
    }


def _generate(prompt: str):
    """Calls the model, retrying only transient failures with linear backoff."""
    request_config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=Classification,
        # Bounded output and no thinking budget: this is a short structured
        # verdict over an excerpt already in the prompt. Left unbounded, a
        # single degenerate response can cost many times a normal one.
        max_output_tokens=config.CLASSIFY_MAX_OUTPUT_TOKENS,
        thinking_config=types.ThinkingConfig(thinking_budget=config.CLASSIFY_THINKING_BUDGET),
        # Innermost timeout in the chain, so this gives up before the crawler
        # stops waiting and long before the server drops the request.
        http_options=types.HttpOptions(timeout=config.CLASSIFY_TIMEOUT_MS),
    )
    last: Exception | None = None
    for attempt in range(1, config.GEMINI_MAX_ATTEMPTS + 1):
        try:
            return client.models.generate_content(
                model=MODEL, contents=prompt, config=request_config,
            )
        except Exception as exc:
            status = _status_of(exc)
            if status not in _RETRYABLE_STATUSES or attempt == config.GEMINI_MAX_ATTEMPTS:
                raise
            last = exc
            delay = config.GEMINI_BACKOFF_SECONDS * attempt
            log.warning(
                "classify attempt %d/%d failed with %s, retrying in %.1fs",
                attempt, config.GEMINI_MAX_ATTEMPTS, status, delay,
            )
            time.sleep(delay)
    raise last  # unreachable: the loop either returns or raises


def classify(finding) -> tuple[Classification, str, str, dict]:
    """Judges one finding. Returns (classification, prompt, raw_output, usage) —
    the last three are for the audit log and spend accounting."""
    prompt = PROMPT_TEMPLATE.format(
        company=finding.company, category=finding.category, title=finding.title,
        summary=finding.summary, source_excerpt=finding.source_excerpt,
    )
    response = _generate(prompt)
    parsed = response.parsed
    if parsed is None:
        # `.parsed` is None whenever the response could not be read into the
        # schema — a safety block, or output truncated at the token limit. It is
        # not an exception, so without this the None travels on and surfaces
        # much later as an AttributeError inside the database layer, pointing at
        # the wrong component entirely.
        raise ValueError(
            f"model returned no parseable classification: {(response.text or '')[:200]!r}"
        )
    return parsed, prompt, response.text, _usage_of(response)
