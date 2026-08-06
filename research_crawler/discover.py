"""Step 1: grounded search. Gemini's google_search tool can't be combined
with strict structured output in the same call, so this step just gathers
raw material — a free-text research summary plus the real source URLs
grounding cites — and structure.py turns that into clean Finding objects
in a second call."""

from dataclasses import dataclass

from google import genai
from google.genai import types

from . import config
from .fetch import fetch_page

client = genai.Client()

PROMPT_TEMPLATE = """Research recent developments for "{keyword}" in the context of the \
Qatar/GCC insurance market. Cover anything relevant across these angles: new or changed \
insurance products, marketing campaigns or promotions, discounts or pricing changes, press/news \
coverage, regulatory filings, and social sentiment (reviews, social media, forum mentions).

Be specific and cite sources for every claim — write several distinct, concrete items rather \
than a general overview. If there's genuinely nothing recent, say so plainly."""


@dataclass
class ResolvedSource:
    domain_title: str
    resolved_url: str
    clean_text: str | None  # None if the independent fetch failed
    raw_html: str | None  # None if the fetch failed, wasn't HTML, or exceeded the size cap


def discover(keyword: str) -> tuple[str, list[ResolvedSource]]:
    """Returns (free_text_summary, resolved_sources)."""
    print(f"  [{keyword}] calling Gemini with search grounding...", flush=True)
    response = client.models.generate_content(
        model=config.MODEL,
        contents=PROMPT_TEMPLATE.format(keyword=keyword),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    summary_text = response.text or ""

    grounding_metadata = response.candidates[0].grounding_metadata if response.candidates else None
    chunks = grounding_metadata.grounding_chunks if grounding_metadata else None
    print(f"  [{keyword}] search returned {len(summary_text)} chars, "
          f"{len(chunks or [])} grounded source(s) to verify", flush=True)

    resolved = []
    for i, chunk in enumerate(chunks or [], 1):
        if not chunk.web or not chunk.web.uri:
            continue
        result = fetch_page(chunk.web.uri)
        if result is None:
            print(f"  [{keyword}] source {i}/{len(chunks)} ({chunk.web.title}): fetch FAILED", flush=True)
            resolved.append(ResolvedSource(chunk.web.title or "", chunk.web.uri, None, None))
        else:
            print(f"  [{keyword}] source {i}/{len(chunks)} ({chunk.web.title}): "
                  f"fetched {len(result.clean_text)} chars from {result.final_url}", flush=True)
            resolved.append(ResolvedSource(
                chunk.web.title or "", result.final_url, result.clean_text, result.raw_html,
            ))

    return summary_text, resolved
