"""Time windows and the freshness rule — one definition, used by every read query.

"Fresh" is not simply "recently crawled": a finding is dated by its source's own
publish date where one exists, and only falls back to crawl time for the kinds of
source where having no publish date is normal. That fallback is what `category`
decides. Everything below exists to express that single rule in whichever SQL
parameter style the calling query needs.
"""

from datetime import date, datetime, timedelta, timezone

# Findings are timestamped in UTC, but the audience is Qatar-based, so "today"
# means a Qatar-local calendar day. Qatar doesn't observe DST, so a fixed offset
# is safe without pulling in a timezone library.
QATAR_OFFSET = timedelta(hours=3)

# Rolling windows (last N days), not calendar-aligned — a PM checking in gets a
# consistently full picture regardless of what day of the week or month it is.
WINDOW_DAYS = {"week": 7, "month": 30, "year": 365}

# Which categories may use crawl time as a stand-in when published_at is missing.
#
# For these four, an undated source is normal rather than a failure: a
# competitor's own product or offer page and an app-store listing are evergreen
# and carry no publish date at all, so "we first saw this change today" genuinely
# IS the news — which is exactly what the content-hash dedup detects.
#
# For every other category — news, regulatory, financial_results,
# investment_or_acquisition — a real publication date always exists, so a missing
# one means extraction failed. Crawl time must NOT stand in there: doing so is
# what once put 2019 and 2025 articles in the "this week" view.
#
# This keys off findings.category (the crawler's tag), never the classifier's
# overlay. The crawler's tag is on every row; a classification exists only for
# the subset that was classified. Letting a retag move a finding between these
# two rules would silently drop undated findings out of every window.
CRAWL_RECENCY_CATEGORIES = ["product", "marketing", "social_sentiment", "other"]

# The rule itself, in two forms. The current-period form is open-ended
# (>= cutoff); the prior-period form is bounded on both sides so consecutive
# periods can never overlap and double-count.
_CURRENT = (
    "(({a}.published_at IS NOT NULL AND {a}.published_at >= {date_from}) "
    "OR ({a}.published_at IS NULL AND {a}.category = ANY({cats}) "
    "AND {a}.retrieved_at >= {instant_from}))"
)
_PRIOR = (
    "(({a}.published_at IS NOT NULL "
    "AND {a}.published_at >= {date_from} AND {a}.published_at < {date_to}) "
    "OR ({a}.published_at IS NULL AND {a}.category = ANY({cats}) "
    "AND {a}.retrieved_at >= {instant_from} AND {a}.retrieved_at < {instant_to}))"
)


def bounds(window: str) -> tuple[datetime, date] | tuple[None, None]:
    """Cutoffs for a window as (retrieved_at instant, published_at date).
    Returns (None, None) for "all", which has no cutoff."""
    now = datetime.now(timezone.utc)
    qatar_now = now + QATAR_OFFSET
    if window == "today":
        qatar_midnight = qatar_now.replace(hour=0, minute=0, second=0, microsecond=0)
        return qatar_midnight - QATAR_OFFSET, qatar_now.date()
    if window in WINDOW_DAYS:
        days = WINDOW_DAYS[window]
        return now - timedelta(days=days), (qatar_now - timedelta(days=days)).date()
    return None, None  # "all"


def freshness_sql(alias: str = "f") -> str:
    """Current-period rule with three positional placeholders, in the order
    freshness_params() returns them."""
    return _CURRENT.format(a=alias, date_from="%s", cats="%s", instant_from="%s")


def freshness_params(window: str) -> list | None:
    """Bind values for freshness_sql(), or None when the window has no cutoff
    and the clause should be omitted entirely."""
    retrieved_cutoff, published_cutoff = bounds(window)
    if retrieved_cutoff is None:
        return None
    return [published_cutoff, CRAWL_RECENCY_CATEGORIES, retrieved_cutoff]


def freshness_sql_named(period: str, alias: str = "f") -> str:
    """The same current-period rule bound by name instead of position, for the
    rollup query that evaluates three windows in one statement."""
    # Positional placeholders would be unreadable there: nine of them, in an
    # order dictated by where each FILTER clause happens to sit in the SQL.
    return _CURRENT.format(
        a=alias,
        date_from=f"%({period}_date)s",
        cats="%(crawl_recency_cats)s",
        instant_from=f"%({period}_instant)s",
    )


def prior_sql(alias: str = "f") -> str:
    """Previous-period rule with five positional placeholders, in the order
    prior_params() returns them."""
    return _PRIOR.format(
        a=alias, date_from="%s", date_to="%s", cats="%s",
        instant_from="%s", instant_to="%s",
    )


def prior_params(window: str) -> list | None:
    """Bind values for prior_sql(), or None when the window has no meaningful
    preceding period (only "all")."""
    current_retrieved, current_published = bounds(window)
    if current_retrieved is None:
        return None
    days = 1 if window == "today" else WINDOW_DAYS[window]
    return [
        current_published - timedelta(days=days), current_published,
        CRAWL_RECENCY_CATEGORIES,
        current_retrieved - timedelta(days=days), current_retrieved,
    ]
