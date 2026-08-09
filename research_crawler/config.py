"""Crawler configuration — env vars only. Deployed independently from the
backend, so this reads its own .env, not the backend's."""

import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# GEMINI_API_KEY is not read here; the Gemini SDK picks it up from the
# environment on its own.
BACKEND_INGEST_URL = os.environ["BACKEND_INGEST_URL"]  # e.g. http://localhost:8123/ingest
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

# MARKET_WIDE_KEYWORD gathers broad market news; QIC_REFERENCE_KEYWORD is
# stored as a benchmark and excluded from the competitor feed. Every other
# entry is a named competitor: structure.py forces finding.company to the
# search subject rather than trusting the LLM's independent guess (which has
# mistagged findings to an unrelated company mentioned in the article
# instead of the competitor actually being searched for). These strings
# Competitor strings must exactly match backend/companies.py's canonical names.
MARKET_WIDE_KEYWORD = "Qatar general insurance market"
QIC_REFERENCE_KEYWORD = "Qatar Insurance Company (QIC)"

KEYWORDS = [
    "Bupa Arabia",
    "Tawuniya",
    "ADNIC",
    "Sukoon Insurance",
    "Alkhaleej Takaful",
    "Beema",
    "Doha Insurance",
    "QIIC",
    "QLM",
    MARKET_WIDE_KEYWORD,
    QIC_REFERENCE_KEYWORD,
]

MODEL = "gemini-3.6-flash"

# Scopes the grounded search to the last N days — a daily cron with an
# unbounded search kept resurfacing old articles it had simply never
# crawled before, which read as "new" despite being months/years old.
# Small default = daily cadence + a one-day overlap buffer. Widened via
# workflow_dispatch for a periodic month-wide backfill, or a one-time
# year-wide initial backfill — see .github/workflows/.
SEARCH_WINDOW_DAYS = int(os.environ.get("SEARCH_WINDOW_DAYS", "3"))
