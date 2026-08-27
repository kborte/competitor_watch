"""Pydantic models — the shapes this service validates against.

Finding and IngestPayload are the JSON contract the crawler delivers; they are
duplicated in research_crawler/schemas.py rather than shared, since the crawler is
deployed separately and the two agree on a wire format, not on code.
Classification is the structured output the classifier is forced to return.
"""

from datetime import date, datetime
from typing import Literal, Optional

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
    """One competitor development, as delivered by the crawler."""

    keyword: str
    company: str
    category: Category
    platform: Optional[str] = None
    source_url: str
    title: str
    summary: str
    source_excerpt: str
    published_at: Optional[date] = None
    retrieved_at: datetime
    source_html: Optional[str] = None
    og_title: Optional[str] = None
    og_image_url: Optional[str] = None
    og_description: Optional[str] = None
    og_site_name: Optional[str] = None
    verified: bool = True
    line: Optional[Line] = None
    tone: Optional[Tone] = None
    source_location: Optional[str] = None
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


class Classification(BaseModel):
    """One classifier verdict. Persisted to the classifications table."""

    category: Category
    materiality: Literal["low", "medium", "high"]
    confidence: float
    grounded: bool
    evidence_quote: str
    rationale: str
