"""The JSON contract shared with the backend's /ingest endpoint.

Duplicated in backend/schemas.py rather than imported: this crawler is deployed
independently, so the two agree on a wire format, not on code. Any change here
has to be made there too.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

Category = Literal[
    "product", "marketing", "news", "social_sentiment", "regulatory",
    "investment_or_acquisition", "financial_results", "other",
]

Line = Literal[
    "motor", "health", "travel", "marine", "energy", "aviation", "pab", "home", "yacht",
    "market_wide", "outside_our_lines",
]

Tone = Literal["positive", "negative", "neutral", "mixed"]


class Finding(BaseModel):
    """One competitor development, as delivered to the backend."""

    keyword: str
    company: str
    category: Category
    platform: str | None = None
    source_url: str
    title: str
    summary: str
    source_excerpt: str
    published_at: date | None = None
    retrieved_at: datetime
    source_html: str | None = None
    og_title: str | None = None
    og_image_url: str | None = None
    og_description: str | None = None
    og_site_name: str | None = None
    verified: bool = True
    # Required here, Optional in backend/schemas.py: the crawler always knows
    # the line and should never emit a finding without one, but the backend
    # must still accept legacy deliveries that lack it.
    line: Line
    tone: Tone | None = None
    source_location: str | None = None
    is_reference: bool = False


class FindingsBatch(BaseModel):
    """Wrapper for structured output — response_schema needs a top-level object,
    not a bare list."""
    findings: list[Finding]


class IngestPayload(BaseModel):
    """One delivery to /ingest."""

    routine_run_id: str
    run_started_at: datetime
    run_completed_at: datetime
    keywords: list[str]
    findings: list[Finding]
    keywords_with_no_findings: list[str] = []
    notes: str = ""
