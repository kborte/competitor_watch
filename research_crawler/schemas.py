"""Pydantic models the crawler produces.

The wire contract (Finding, IngestPayload and their enums) lives in shared/ and
is re-exported here. FindingsBatch is crawler-only: it exists solely because
structured output needs a top-level object, and never crosses the wire.
"""

from pydantic import BaseModel

from shared.schemas import Category, Finding, IngestPayload, Line, Tone

__all__ = ["Category", "Finding", "FindingsBatch", "IngestPayload", "Line", "Tone"]


class FindingsBatch(BaseModel):
    """Wrapper for structured output — response_schema needs a top-level object,
    not a bare list."""

    findings: list[Finding]
