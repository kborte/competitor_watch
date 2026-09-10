"""Step 1 of the crawl: grounded search, then verify what it cited.

Gemini's google_search tool cannot be combined with strict structured output in
one call, so this step only gathers raw material — a free-text research summary
plus the real source URLs grounding cites — and independently fetches each cited
page. structure.py turns that into clean Finding objects in a second call.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from google import genai
from google.genai import types

from . import config, llm
from .fetch import fetch_page

log = logging.getLogger(__name__)

client = genai.Client()

PROMPT_TEMPLATE = """Research recent developments for "{keyword}" in the context of the \
Qatar/GCC insurance market. Cover anything relevant across these angles: new or changed \
insurance products, marketing campaigns or promotions, discounts or pricing changes, press/news \
coverage, regulatory filings, social sentiment (reviews, social media, forum mentions), and \
website/app releases or other digital and non-insurance products.

Be specific and cite sources for every claim — write several distinct, concrete items rather \
than a general overview. If there's genuinely nothing recent, say so plainly."""


@dataclass
class ResolvedSource:
    """One cited source, resolved to a real URL and fetched where possible."""

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
    """Searches for one keyword and resolves every source it cites.
    Returns (free_text_summary, resolved_sources)."""
    # Scoping the search to the last N days stops an old article the crawler
    # only just discovered from reading as fresh. The read API's published_at
    # freshness filtering catches whatever still slips through.
    search_kwargs = {}
    if time_range_days is not None:
        # Whole seconds only — the API rejects sub-second precision with
        # "Granularity of nano is not supported", and datetime.now()
        # carries microseconds.
        now = datetime.now(UTC).replace(microsecond=0)
        search_kwargs["time_range_filter"] = types.Interval(
            start_time=now - timedelta(days=time_range_days), end_time=now,
        )

    window_note = f" (window: last {time_range_days}d)" if time_range_days else ""
    log.info("[%s] calling Gemini with search grounding...%s", keyword, window_note)
    response = llm.generate(
        client,
        model=config.MODEL,
        contents=PROMPT_TEMPLATE.format(keyword=keyword),
        request_config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch(**search_kwargs))],
            max_output_tokens=config.DISCOVER_MAX_OUTPUT_TOKENS,
            thinking_config=types.ThinkingConfig(
                thinking_budget=config.DISCOVER_THINKING_BUDGET,
            ),
            http_options=types.HttpOptions(timeout=config.DISCOVER_TIMEOUT_MS),
        ),
        label=keyword,
    )
    summary_text = response.text or ""

    grounding_metadata = response.candidates[0].grounding_metadata if response.candidates else None
    chunks = [c for c in (grounding_metadata.grounding_chunks if grounding_metadata else None) or []
              if c.web and c.web.uri]

    # Cap before fetching, not after: every extra source costs a page fetch and
    # roughly 750 prompt tokens downstream, and grounding occasionally returns
    # dozens. Dropped sources are logged rather than silently discarded.
    if len(chunks) > config.MAX_SOURCES_PER_KEYWORD:
        log.warning(
            "[%s] %d grounded sources, capping at %d — %d dropped",
            keyword, len(chunks), config.MAX_SOURCES_PER_KEYWORD,
            len(chunks) - config.MAX_SOURCES_PER_KEYWORD,
        )
        chunks = chunks[:config.MAX_SOURCES_PER_KEYWORD]

    total = len(chunks)
    log.info("[%s] search returned %d chars, %d grounded source(s) to verify",
             keyword, len(summary_text), total)

    # Fetched concurrently: serially, 15s per page meant the sources alone could
    # exhaust the per-company budget in crawler.py before structuring began.
    with ThreadPoolExecutor(max_workers=config.FETCH_CONCURRENCY) as pool:
        results = list(pool.map(lambda c: fetch_page(c.web.uri), chunks))

    resolved = []
    for i, (chunk, result) in enumerate(zip(chunks, results, strict=True), 1):
        if result is None:
            # Truly unresolvable (DNS/timeout/connection error, or refused by
            # the URL guard) — no real URL exists to show a human, so this
            # source is dropped entirely rather than ever citing Gemini's raw
            # grounding redirect link (vertexaisearch.cloud.google.com/...) as
            # a "source."
            log.info("[%s] source %d/%d (%s): unresolvable — dropped, not citable",
                     keyword, i, total, chunk.web.title)
            continue

        if result.clean_text is None:
            log.info("[%s] source %d/%d (%s): resolved to %s but content fetch failed — "
                     "citable, unverified", keyword, i, total, chunk.web.title, result.final_url)
        else:
            log.info("[%s] source %d/%d (%s): fetched %d chars from %s",
                     keyword, i, total, chunk.web.title, len(result.clean_text), result.final_url)

        resolved.append(ResolvedSource(
            domain_title=chunk.web.title or "", resolved_url=result.final_url,
            clean_text=result.clean_text, raw_html=result.raw_html,
            og_title=result.og_title, og_image_url=result.og_image_url,
            og_description=result.og_description, og_site_name=result.og_site_name,
            published_date=result.published_date,
        ))

    return summary_text, resolved
