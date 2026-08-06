"""Step 2: structure the raw discovery material into clean Finding
objects. No search tool here, no novelty judgment — this call's only job
is to read what discover.py already found and shape it correctly. It's
told to quote source_excerpt verbatim from the fetched page text, not
paraphrase, so grounding survives into the actual stored record."""

from datetime import datetime, timezone

from google import genai
from google.genai import types

from . import config
from .discover import ResolvedSource
from .schemas import FindingsBatch

client = genai.Client()

PROMPT_TEMPLATE = """Below is a research summary about "{keyword}" plus the actual fetched \
text of each source it cited. Turn this into a list of distinct findings.

For each finding:
- category: exactly one of product, marketing, news, social_sentiment, regulatory, other — a \
factual bucket, not a judgment about importance.
- company: normalized name (e.g. "Bupa Arabia", not "bupa").
- platform: e.g. "Google Play", "X", "Trustpilot" — or omit for ordinary news/press pages.
- source_url: must be exactly one of the source URLs listed below.
- source_excerpt: a VERBATIM substring copied from that source's fetched text below — not a \
paraphrase. If a claim's source has no fetched text (fetch failed), you may summarize instead \
and note in the excerpt that the page couldn't be independently verified.
- published_at: YYYY-MM-DD if it's mentioned anywhere in the source text, else omit.

Report everything relevant, including routine items — do not filter for importance.

--- Research summary ---
{summary}

--- Sources ---
{sources}
"""


def _format_sources(sources: list[ResolvedSource]) -> str:
    blocks = []
    for s in sources:
        text = s.clean_text[:3000] if s.clean_text else "(fetch failed — no page text available)"
        blocks.append(f"URL: {s.resolved_url}\nDomain: {s.domain_title}\nFetched text:\n{text}")
    return "\n\n".join(blocks) if blocks else "(no sources were successfully grounded)"


def structure(keyword: str, summary: str, sources: list[ResolvedSource]) -> FindingsBatch:
    print(f"  [{keyword}] structuring into findings...", flush=True)
    prompt = PROMPT_TEMPLATE.format(keyword=keyword, summary=summary, sources=_format_sources(sources))
    response = client.models.generate_content(
        model=config.MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=FindingsBatch,
        ),
    )
    batch = response.parsed
    now = datetime.now(timezone.utc)
    html_by_url = {s.resolved_url: s.raw_html for s in sources}
    for finding in batch.findings:
        finding.keyword = keyword
        finding.retrieved_at = now
        finding.source_html = html_by_url.get(finding.source_url)
    print(f"  [{keyword}] structured {len(batch.findings)} finding(s): "
          + ", ".join(f"{f.category}" for f in batch.findings), flush=True)
    return batch
