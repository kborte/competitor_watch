"""Query layer backing the read API (main.py's GET routes). Kept separate
from the HTTP layer so main.py stays a thin translation from request params
to these calls and back to a response — same split as ingest.py/db.py on
the write side.

Findings are timestamped in UTC (retrieved_at), but the audience is
Qatar-based, so "today" is a Qatar-local calendar day. Qatar doesn't
observe DST, so a fixed UTC+3 offset is safe without a timezone library.
week/month/year are rolling windows (last 7/30/365 days), not
calendar-aligned — a PM checking in gets a consistently full picture
regardless of what day of the week/month it is.

Window recency prefers published_at (when the source itself was actually
published) over retrieved_at (when the crawler happened to see it) — a
page from a year ago that the crawler only just discovered isn't "new."
published_at is frequently null (undated social/review sources), so those
fall back to retrieved_at rather than disappearing from every window."""

from datetime import date, datetime, timedelta, timezone
from html import escape

from psycopg2.extras import RealDictCursor

from . import companies

QATAR_OFFSET = timedelta(hours=3)
MAX_LIMIT = 200
DEFAULT_LIMIT = 50

# high > medium > low; a bare `ORDER BY materiality DESC` would sort the
# TEXT column alphabetically (medium, low, high) instead.
MATERIALITY_RANK_SQL = "CASE materiality WHEN 'high' THEN 3 WHEN 'medium' THEN 2 WHEN 'low' THEN 1 ELSE 0 END"

_WINDOW_DAYS = {"week": 7, "month": 30, "year": 365}


def _window_bounds(window: str) -> tuple[datetime, date] | tuple[None, None]:
    """Returns (retrieved_at_cutoff, published_at_cutoff_date) for a window,
    or (None, None) for "all"."""
    now = datetime.now(timezone.utc)
    qatar_now = now + QATAR_OFFSET
    if window == "today":
        qatar_midnight = qatar_now.replace(hour=0, minute=0, second=0, microsecond=0)
        return qatar_midnight - QATAR_OFFSET, qatar_now.date()
    if window in _WINDOW_DAYS:
        days = _WINDOW_DAYS[window]
        return now - timedelta(days=days), (qatar_now - timedelta(days=days)).date()
    return None, None  # "all"


# Categories where an undated source is normal rather than an extraction
# failure: a competitor's own product/offer page or an app-store listing
# is evergreen and carries no publish date, so "we first saw this today"
# genuinely IS the news (that's exactly what the content-hash dedup
# tracks). A dated-event category — news, regulatory, financial results,
# M&A — always has a real publication date, so a missing one means
# extraction failed, and crawl-time must NOT stand in for it: that's what
# put 2019 and 2025 articles in the "this week" view.
CRAWL_RECENCY_CATEGORIES = ["product", "marketing", "social_sentiment", "other"]


def _freshness_sql(alias: str = "f") -> str:
    """Recency condition with three positional %s placeholders, in order:
    (published_at_cutoff_date, crawl_recency_categories, retrieved_at_cutoff)."""
    return (
        f"(({alias}.published_at IS NOT NULL AND {alias}.published_at >= %s) "
        f"OR ({alias}.published_at IS NULL AND {alias}.category = ANY(%s) "
        f"AND {alias}.retrieved_at >= %s))"
    )


def _order_sql(sort_by: str, sort_dir: str) -> str:
    # Defensive fallback (not just main.py's whitelist check) since these
    # become raw ORDER BY text, not bind parameters — an unrecognized value
    # degrades to a safe default rather than ever reaching string interpolation
    # unchecked.
    direction = "ASC" if sort_dir == "asc" else "DESC"
    if sort_by == "materiality":
        return f"ORDER BY {MATERIALITY_RANK_SQL} {direction}, f.retrieved_at DESC"
    if sort_by == "published_at":
        return f"ORDER BY f.published_at {direction} NULLS LAST, f.retrieved_at DESC"
    return f"ORDER BY f.retrieved_at {direction}"


def list_findings(
    conn, *, company: str | None = None, category: str | None = None, window: str = "all",
    sort_by: str = "materiality", sort_dir: str = "desc", include_duplicates: bool = False,
    limit: int = DEFAULT_LIMIT, offset: int = 0,
) -> list[dict]:
    limit = max(1, min(limit, MAX_LIMIT))

    clauses = []
    params: list = []
    if not include_duplicates:
        clauses.append("f.is_duplicate = false")
    retrieved_cutoff, published_cutoff = _window_bounds(window)
    if retrieved_cutoff is not None:
        clauses.append(_freshness_sql())
        params.extend([published_cutoff, CRAWL_RECENCY_CATEGORIES, retrieved_cutoff])
    if company == companies.MARKET_BUCKET:
        # The bucket is an inverse set — "not any recognized competitor" —
        # not a finite alias list like every other entity.
        clauses.append("f.company != ALL(%s)")
        params.append(companies.known_aliases())
    elif company:
        clauses.append("f.company = ANY(%s)")
        params.append(companies.aliases_for(company))
    if category:
        clauses.append("f.category = %s")
        params.append(category)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order_sql = _order_sql(sort_by, sort_dir)

    query = f"""
        SELECT f.id, f.keyword, f.company, f.category, f.platform, f.source_url, f.title,
               f.summary, f.source_excerpt, f.published_at, f.retrieved_at, f.is_duplicate,
               f.og_title, f.og_image_url, f.og_description, f.og_site_name, f.verified,
               c.materiality
        FROM findings f
        LEFT JOIN llm_calls lc ON lc.finding_id = f.id
        LEFT JOIN changes c ON c.llm_call_id = lc.id
        {where_sql}
        {order_sql}
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def get_finding(conn, finding_id: int, view: str = "full") -> dict | None:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM findings WHERE id = %s", (finding_id,))
        finding = cur.fetchone()
        if finding is None:
            return None

        cur.execute(
            """
            SELECT lc.model, lc.prompt, lc.raw_output, lc.called_at,
                   c.materiality, c.confidence, c.evidence_quote, c.rationale
            FROM llm_calls lc
            LEFT JOIN changes c ON c.llm_call_id = lc.id
            WHERE lc.finding_id = %s
            """,
            (finding_id,),
        )
        audit = cur.fetchone()

    result = dict(finding)
    result["has_snapshot"] = result.pop("source_html") is not None
    result["change"] = {
        "materiality": audit["materiality"],
        "confidence": audit["confidence"],
        "evidence_quote": audit["evidence_quote"],
        "rationale": audit["rationale"],
    } if audit else None
    result["llm_call"] = {
        "model": audit["model"],
        "prompt": audit["prompt"],
        "raw_output": audit["raw_output"],
        "called_at": audit["called_at"],
    } if (audit and view == "full") else None
    return result


def get_snapshot(conn, finding_id: int) -> dict | None:
    """Returns {"source_url", "html"} (html may itself be None), or None if
    the finding doesn't exist at all."""
    with conn.cursor() as cur:
        cur.execute("SELECT source_url, source_html FROM findings WHERE id = %s", (finding_id,))
        row = cur.fetchone()
    if row is None:
        return None
    source_url, html = row
    return {"source_url": source_url, "html": html}


def inject_base_href(html: str, base_url: str) -> str:
    """So relative asset paths in the captured page resolve against the
    original site instead of 404ing against our own backend."""
    base_tag = f'<base href="{escape(base_url)}">'
    lower = html.lower()
    head_idx = lower.find("<head")
    if head_idx == -1:
        return base_tag + html
    insert_at = lower.find(">", head_idx) + 1
    return html[:insert_at] + base_tag + html[insert_at:]


def get_latest_crawl_at(conn) -> datetime | None:
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(retrieved_at) FROM findings")
        return cur.fetchone()[0]


def list_companies(conn) -> list[dict]:
    """Grouped by canonical entity, not raw string — the registry lookup
    happens in Python (a handful of distinct raw company strings at most,
    not worth mirroring the alias map into SQL)."""
    def freshness(period: str) -> str:
        # Same rule as list_findings (see CRAWL_RECENCY_CATEGORIES), spelled
        # out with named params since this query already uses them.
        return (
            f"((published_at IS NOT NULL AND published_at >= %({period}_date)s) "
            f"OR (published_at IS NULL AND category = ANY(%(crawl_recency_cats)s) "
            f"AND retrieved_at >= %({period}_instant)s))"
        )

    retrieved_today, published_today = _window_bounds("today")
    retrieved_week, published_week = _window_bounds("week")
    retrieved_month, published_month = _window_bounds("month")

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT company,
                   COUNT(*) FILTER (WHERE {freshness("today")} AND NOT is_duplicate) AS new_today,
                   COUNT(*) FILTER (WHERE {freshness("week")} AND NOT is_duplicate) AS new_this_week,
                   COUNT(*) FILTER (WHERE {freshness("month")} AND NOT is_duplicate) AS new_this_month,
                   COUNT(*) AS total_findings
            FROM findings
            GROUP BY company
            """,
            {
                "today_date": published_today, "today_instant": retrieved_today,
                "week_date": published_week, "week_instant": retrieved_week,
                "month_date": published_month, "month_instant": retrieved_month,
                "crawl_recency_cats": CRAWL_RECENCY_CATEGORIES,
            },
        )
        raw_rows = cur.fetchall()

    grouped: dict[str, dict] = {}
    for row in raw_rows:
        name = companies.canonical_name(row["company"])
        bucket = grouped.setdefault(name, {
            "company": name, "new_today": 0, "new_this_week": 0, "new_this_month": 0, "total_findings": 0,
        })
        bucket["new_today"] += row["new_today"]
        bucket["new_this_week"] += row["new_this_week"]
        bucket["new_this_month"] += row["new_this_month"]
        bucket["total_findings"] += row["total_findings"]

    return sorted(grouped.values(), key=lambda r: r["company"])
