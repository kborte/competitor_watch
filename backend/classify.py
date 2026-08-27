"""The one LLM call in the backend: judging a single finding.

No agent, no tools, no loop — structured output forces the verdict fields
directly. Primarily a materiality judge, it also re-reads the crawler's category
as a second opinion and reports whether the excerpt really supports the summary.
Only findings that survive dedup and are not QIC reference rows get here
(ingest.py), so classifications are sparse relative to findings.
"""

from google import genai
from google.genai import types

from . import config  # noqa: F401 — import order matters: this triggers load_dotenv() before Client() reads the env
from .schemas import Classification

client = genai.Client()  # reads GEMINI_API_KEY from the environment

MODEL = "gemini-3.6-flash"

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


def classify(finding) -> tuple[Classification, str, str]:
    """Returns (classification, prompt_sent, raw_output) — the last two are for the audit log."""
    prompt = PROMPT_TEMPLATE.format(
        company=finding.company, category=finding.category, title=finding.title,
        summary=finding.summary, source_excerpt=finding.source_excerpt,
    )
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Classification,
        ),
    )
    return response.parsed, prompt, response.text
