"""JSON contract shared with the backend's /ingest endpoint. Duplicated
here rather than imported, since this crawler is deployed independently
from the backend — the two agree on a wire format, not on code."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel

Category = Literal["product", "marketing", "news", "social_sentiment", "regulatory", "other"]


class Finding(BaseModel):
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


class FindingsBatch(BaseModel):
    """Wrapper for structured output — Gemini's response_schema needs a
    top-level object, not a bare list."""
    findings: list[Finding]


class IngestPayload(BaseModel):
    routine_run_id: str
    run_started_at: datetime
    run_completed_at: datetime
    keywords: list[str]
    findings: list[Finding]
    keywords_with_no_findings: list[str] = []
    notes: str = ""
