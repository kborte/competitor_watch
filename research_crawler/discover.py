"""Step 1: grounded search. Gemini's google_search tool can't be combined
with strict structured output in the same call, so this step just gathers
raw material — a free-text research summary plus the real source URLs
grounding cites — and structure.py turns that into clean Finding objects
in a second call."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

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
    og_title: str | None = None
    og_image_url: str | None = None
    og_description: str | None = None
    og_site_name: str | None = None
    published_date: str | None = None


def discover(keyword: str, time_range_days: int | None = None) -> tuple[str, list[ResolvedSource]]:
    """Returns (free_text_summary, resolved_sources). time_range_days, when
    set, scopes the grounded search to only the last N days via Gemini's
    native time_range_filter — reduces how often an old article the
    crawler only just discovered gets treated as fresh. (The other half of
    that fix is the read API's published_at-based freshness filtering,
    which catches whatever still slips through.)"""
    search_kwargs = {}
    if time_range_days is not None:
        # Whole seconds only — the API rejects sub-second precision with
        # "Granularity of nano is not supported", and datetime.now()
        # carries microseconds.
        now = datetime.now(timezone.utc).replace(microsecond=0)
        search_kwargs["time_range_filter"] = types.Interval(
            start_time=now - timedelta(days=time_range_days), end_time=now,
        )

    window_note = f" (window: last {time_range_days}d)" if time_range_days else ""
    print(f"  [{keyword}] calling Gemini with search grounding...{window_note}", flush=True)
    response = client.models.generate_content(
        model=config.MODEL,
        contents=PROMPT_TEMPLATE.format(keyword=keyword),
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch(**search_kwargs))],
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
            # Truly unresolvable (DNS/timeout/connection error) — no real
            # URL exists to show a human, so this source is dropped
            # entirely rather than ever citing Gemini's raw grounding
            # redirect link (vertexaisearch.cloud.google.com/...) as a
            # "source."
            print(f"  [{keyword}] source {i}/{len(chunks)} ({chunk.web.title}): "
                  f"could not be resolved at all — dropped, not citable", flush=True)
            continue

        if result.clean_text is None:
            print(f"  [{keyword}] source {i}/{len(chunks)} ({chunk.web.title}): "
                  f"resolved to {result.final_url} but content fetch failed — "
                  f"citable, unverified", flush=True)
        else:
            print(f"  [{keyword}] source {i}/{len(chunks)} ({chunk.web.title}): "
                  f"fetched {len(result.clean_text)} chars from {result.final_url}", flush=True)

        resolved.append(ResolvedSource(
            domain_title=chunk.web.title or "", resolved_url=result.final_url,
            clean_text=result.clean_text, raw_html=result.raw_html,
            og_title=result.og_title, og_image_url=result.og_image_url,
            og_description=result.og_description, og_site_name=result.og_site_name,
            published_date=result.published_date,
        ))

    return summary_text, resolved
