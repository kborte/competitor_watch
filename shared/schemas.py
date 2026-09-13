"""The JSON contract for POST /ingest.

The crawler builds these; the backend validates against them. Defined once so a
field cannot be added on one side and forgotten on the other — a drift that
shows up only at runtime, as a rejected delivery.
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
    # Optional, though the crawler always sets it: rows predating the field
    # exist, and rejecting a delivery over it would lose a finding that is
    # otherwise perfectly storable. A missing line only narrows the dashboard's
    # line filter.
    line: Line | None = None
    tone: Tone | None = None
    source_location: str | None = None
    is_reference: bool = False


class IngestPayload(BaseModel):
    """One delivery. The crawler sends a single finding per request, so a
    partial crawl still lands everything it found before failing."""

    routine_run_id: str
    run_started_at: datetime
    run_completed_at: datetime
    keywords: list[str]
    findings: list[Finding]
    keywords_with_no_findings: list[str] = []
    notes: str = ""
