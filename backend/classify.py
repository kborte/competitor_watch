"""One LLM call per new/changed finding — no agent, no tools, no loop.
Structured output forces category/materiality/confidence directly, and the
model is asked to ground its judgment in the routine's own source_excerpt
rather than paraphrasing further."""

from google import genai
from google.genai import types

from . import config  # noqa: F401 — import order matters: this triggers load_dotenv() before Client() reads the env
from .schemas import Classification

client = genai.Client()  # reads GEMINI_API_KEY from the environment

MODEL = "gemini-3.6-flash"

PROMPT_TEMPLATE = """A competitor-watch routine found this item. Classify it.

Company: {company}
Category (as tagged by the routine): {category}
Title: {title}
Summary (routine's paraphrase): {summary}
Verbatim excerpt from the source: "{source_excerpt}"

Judge:
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
