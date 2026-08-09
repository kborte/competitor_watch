"""Crawler configuration — env vars only. Deployed independently from the
backend, so this reads its own .env, not the backend's."""

import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# GEMINI_API_KEY is not read here; the Gemini SDK picks it up from the
# environment on its own.
BACKEND_INGEST_URL = os.environ["BACKEND_INGEST_URL"]  # e.g. http://localhost:8123/ingest
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

# One special entry, MARKET_WIDE_KEYWORD, for broad market news not tied
# to a specific tracked competitor. Every other entry is treated as a named
# competitor: structure.py forces finding.company to exactly this string
# for those, rather than trusting the LLM's independent guess (which has
# mistagged findings to an unrelated company mentioned in the article
# instead of the competitor actually being searched for). These strings
# must exactly match the canonical names in backend/companies.py.
MARKET_WIDE_KEYWORD = "Qatar general insurance market"

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
]

MODEL = "gemini-3.6-flash"

# Scopes the grounded search to the last N days — a daily cron with an
# unbounded search kept resurfacing old articles it had simply never
# crawled before, which read as "new" despite being months/years old.
# Small default = daily cadence + a one-day overlap buffer. Widened via
# workflow_dispatch for a periodic month-wide backfill, or a one-time
# year-wide initial backfill — see .github/workflows/.
SEARCH_WINDOW_DAYS = int(os.environ.get("SEARCH_WINDOW_DAYS", "3"))
