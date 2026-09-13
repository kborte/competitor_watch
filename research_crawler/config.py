"""Crawler configuration — env vars and the keyword list.

Reads the repo-root .env (see .env.example), the same file the backend reads;
the two are deployed separately but configured from one place. In a container
that file is absent and the platform supplies the environment directly.
KEYWORDS is the list the crawl iterates: one grounded search per entry.
GEMINI_API_KEY is not read here — the SDK picks it up from the environment.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BACKEND_INGEST_URL = os.environ["BACKEND_INGEST_URL"]  # e.g. http://localhost:8123/ingest
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

# MARKET_WIDE_KEYWORD gathers broad market news; QIC_REFERENCE_KEYWORD is stored
# as a benchmark and excluded from the competitor feed. Every other entry is a
# named competitor: structure.py forces finding.company to the search subject
# rather than trusting the LLM's independent guess, which has mistagged findings
# to an unrelated company merely mentioned in the article.
#
# Each competitor string must be a recognized alias in backend/companies.py —
# normally the canonical name itself, though a keyword chosen for search quality
# can differ from the dashboard name (see the Qatar General entry there). A
# keyword matching no alias silently lands in the market bucket.
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
    # Deliberately the full form, not "Qatar General Insurance": that would sit
    # a hair away from MARKET_WIDE_KEYWORD above, and a named-competitor keyword
    # force-tags every finding it produces (structure.py), so the overlap would
    # relabel generic market news as this company.
    "Qatar General Insurance & Reinsurance",
    MARKET_WIDE_KEYWORD,
    QIC_REFERENCE_KEYWORD,
]

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

# Scopes the grounded search to the last N days — a daily cron with an
# unbounded search kept resurfacing old articles it had simply never
# crawled before, which read as "new" despite being months/years old.
# Small default = daily cadence + a one-day overlap buffer. Widened via
# workflow_dispatch for a periodic month-wide backfill, or a one-time
# year-wide initial backfill — see .github/workflows/.
SEARCH_WINDOW_DAYS = int(os.environ.get("SEARCH_WINDOW_DAYS", "3"))


# ---------------------------------------------------------------------------
# Limits. Before these existed, a run's only input cap was 3000 characters per
# source in structure.py, and the number of sources was unbounded — so one
# keyword returning 40 grounded sources produced a 30k-token prompt with nothing
# to stop it.
# ---------------------------------------------------------------------------

# Sources fetched and fed to the structuring call per keyword. Grounding
# occasionally returns dozens; the first handful carry almost all the signal,
# and each one costs a page fetch plus ~750 prompt tokens.
MAX_SOURCES_PER_KEYWORD = int(os.environ.get("MAX_SOURCES_PER_KEYWORD", "15"))

# The research summary is pasted into the structuring prompt whole. Truncating
# it bounds the one input that had no limit at all.
MAX_SUMMARY_CHARS = int(os.environ.get("MAX_SUMMARY_CHARS", "12000"))

# Findings accepted from one keyword, and from one whole run. A ceiling turns a
# runaway keyword into a logged, bounded event instead of an unbounded bill.
MAX_FINDINGS_PER_KEYWORD = int(os.environ.get("MAX_FINDINGS_PER_KEYWORD", "20"))
MAX_FINDINGS_PER_CRAWL = int(os.environ.get("MAX_FINDINGS_PER_CRAWL", "200"))

# Uppercased because logging rejects a lowercase level name outright
# (ValueError: Unknown level: 'debug'), which would be a crash on boot.
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

# Kill switch, checked before any paid call is made. Stated positively so the
# variable reads the way it behaves — an inverted boolean is the kind of thing
# that gets set to "false" in an emergency and quietly keeps running.
CRAWL_ENABLED = os.environ.get("CRAWL_ENABLED", "true").strip().lower() not in {
    "0", "false", "no", "off",
}

# Pages are fetched concurrently. Serial fetching at 15s each meant 20 sources
# alone could exhaust the 300s per-company budget before structuring began.
FETCH_CONCURRENCY = int(os.environ.get("FETCH_CONCURRENCY", "6"))

# ---------------------------------------------------------------------------
# Timeouts, innermost strictest, so a slow call always surfaces as a real error
# to whoever is waiting instead of one side guessing:
#   Gemini call < backend HTTP call < the backend's own request timeout.
# ---------------------------------------------------------------------------
DISCOVER_TIMEOUT_MS = int(os.environ.get("DISCOVER_TIMEOUT_MS", "120000"))
STRUCTURE_TIMEOUT_MS = int(os.environ.get("STRUCTURE_TIMEOUT_MS", "90000"))
DISCOVER_MAX_OUTPUT_TOKENS = int(os.environ.get("DISCOVER_MAX_OUTPUT_TOKENS", "4096"))
STRUCTURE_MAX_OUTPUT_TOKENS = int(os.environ.get("STRUCTURE_MAX_OUTPUT_TOKENS", "8192"))
# Search grounding benefits from some reasoning; shaping already-found material
# into a fixed schema does not.
DISCOVER_THINKING_BUDGET = int(os.environ.get("DISCOVER_THINKING_BUDGET", "2048"))
STRUCTURE_THINKING_BUDGET = int(os.environ.get("STRUCTURE_THINKING_BUDGET", "0"))

# Retry only transient statuses, only a few times. Exhausting them is not data
# loss: the next daily crawl re-reports everything it can still see.
GEMINI_MAX_ATTEMPTS = int(os.environ.get("GEMINI_MAX_ATTEMPTS", "3"))
GEMINI_BACKOFF_SECONDS = float(os.environ.get("GEMINI_BACKOFF_SECONDS", "2"))

# Delivery timeout. Comfortably above the backend's own classification budget
# (45s) so the client stops waiting only when something is genuinely wrong,
# never merely because classification was slow.
BACKEND_TIMEOUT_SECONDS = int(os.environ.get("BACKEND_TIMEOUT_SECONDS", "90"))

# Delivery retries. Free in model tokens: /ingest is idempotent on
# routine_run_id and commits that row before classifying, so a repeat never
# reaches the model. Exhausting them is not data loss either — the next daily
# crawl re-reports the finding.
DELIVERY_MAX_ATTEMPTS = int(os.environ.get("DELIVERY_MAX_ATTEMPTS", "3"))
DELIVERY_BACKOFF_SECONDS = float(os.environ.get("DELIVERY_BACKOFF_SECONDS", "2"))
