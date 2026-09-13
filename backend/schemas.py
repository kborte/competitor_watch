"""Pydantic models the backend validates against.

The wire contract (Finding, IngestPayload and their enums) lives in shared/ and
is re-exported here, so existing imports keep working and there is one
definition rather than two. Classification is backend-only: it is the structured
output the classifier is forced to return, and never crosses the wire.
"""

from typing import Literal

from pydantic import BaseModel

from shared.schemas import Category, Finding, IngestPayload, Line, Tone

__all__ = ["Category", "Classification", "Finding", "IngestPayload", "Line", "Tone"]


class Classification(BaseModel):
    """One classifier verdict. Persisted to the classifications table."""

    category: Category
    materiality: Literal["low", "medium", "high"]
    confidence: float
    grounded: bool
    evidence_quote: str
    rationale: str
