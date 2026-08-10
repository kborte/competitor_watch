"""Step 2: structure the raw discovery material into clean Finding
objects. No search tool here, no novelty judgment — this call's only job
is to read what discover.py already found and shape it correctly. It's
told to quote source_excerpt verbatim from the fetched page text, not
paraphrase, so grounding survives into the actual stored record."""

from datetime import date, datetime, timezone

from google import genai
from google.genai import types

from . import config
from .discover import ResolvedSource
from .schemas import FindingsBatch

client = genai.Client()

PROMPT_TEMPLATE = """Below is a research summary about "{keyword}" plus the actual fetched \
text of each source it cited. Turn this into a list of distinct findings.

For each finding:
- title: a concise, specific headline describing the actual finding. For social_sentiment, put \
the common sentiment and its concrete cause directly in the title (for example, "Sukoon \
customers report delays in medical approvals and motor repairs"). Do not use generic labels \
such as "Customer Reviews", "User Feedback", "App Review", or "Reddit Discussion".
- line: exactly one of: motor, health, travel, marine, energy, aviation, pab (personal accident \
and business), home, yacht, market_wide, outside_our_lines. Website and app are channels, not \
lines: use the underlying insurance line when specific, market_wide for a cross-line platform \
change, and outside_our_lines for a genuinely non-insurance product or a cover QIC does not write.
- category: exactly one of these factual buckets (not a judgment about importance):
  - product: a change to what's actually offered — new coverage, features, pricing structure.
  - marketing: campaigns, promotions, sponsorships, brand pushes.
  - news: general press coverage not covered by a more specific bucket below.
  - social_sentiment: reviews, social media, forum mentions.
  - regulatory: compliance, licensing, conduct frameworks, disclosure requirements — a \
regulator being involved is not sufficient on its own; the finding must be *about* compliance/ \
licensing itself, not merely announced through a regulatory process.
  - investment_or_acquisition: M&A, stake changes, funding rounds, new subsidiary formation.
  - financial_results: earnings, profit/loss, dividends, capital raises — even when a regulator \
had to approve the raise itself, the story is financial, not regulatory.
  - other: doesn't fit any of the above.
- company: normalized name (e.g. "Bupa Arabia", not "bupa"). For a company-specific search \
this is overridden afterwards to the company actually being searched for regardless of what \
you put here — so focus your judgment on genuinely market-wide research, where this should \
name whichever specific company (if any) a finding is really about.
- platform: e.g. "Google Play", "X", "Trustpilot" — or omit for ordinary news/press pages.
- source_url: must be exactly one of the source URLs listed below.
- source_excerpt: a VERBATIM substring copied from that source's fetched text below — not a \
paraphrase. If a claim's source has no fetched text (fetch failed), summarize the claim from \
the research summary instead — no need to caveat this in the text, that's tracked separately.
- source_location: a short human-readable location for the excerpt when the fetched text makes \
one identifiable (for example, "Third paragraph under Renewals" or "Opening paragraph"); omit \
it rather than guessing when the location is unclear.
- tone: for social_sentiment findings, exactly one of positive, negative, neutral, or mixed. \
Omit it for other categories.
- published_at: YYYY-MM-DD if it's mentioned anywhere in the source text, else omit. (Used only \
as a fallback — a page's real publish-date metadata is extracted separately and takes priority \
over this guess when available.)

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
    sources_by_url = {s.resolved_url: s for s in sources}
    for finding in batch.findings:
        finding.keyword = keyword
        finding.retrieved_at = now
        # We already know definitively which competitor a named-keyword
        # search was for — no need to trust the LLM's independent guess,
        # which has mistagged findings to some other company merely
        # mentioned in the article (e.g. a partner bank) instead of the
        # one actually being tracked.
        if keyword == config.QIC_REFERENCE_KEYWORD:
            finding.company = "Qatar Insurance Company"
            finding.is_reference = True
        elif keyword != config.MARKET_WIDE_KEYWORD:
            finding.company = keyword
        source = sources_by_url.get(finding.source_url)
        finding.source_html = source.raw_html if source else None
        finding.og_title = source.og_title if source else None
        finding.og_image_url = source.og_image_url if source else None
        finding.og_description = source.og_description if source else None
        finding.og_site_name = source.og_site_name if source else None
        # Deterministic, never inferred from LLM prose — true iff we
        # actually got the source's own text, not just a resolved URL.
        finding.verified = source is not None and source.clean_text is not None
        # A page's own structured publish-date metadata beats the LLM's
        # text-based guess whenever it's available.
        if source and source.published_date:
            try:
                finding.published_at = date.fromisoformat(source.published_date)
            except ValueError:
                pass  # malformed — keep whatever the LLM guessed
    print(f"  [{keyword}] structured {len(batch.findings)} finding(s): "
          + ", ".join(f"{f.category}" for f in batch.findings), flush=True)
    return batch
