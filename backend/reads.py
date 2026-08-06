"""Query layer backing the read API (main.py's GET routes). Kept separate
from the HTTP layer so main.py stays a thin translation from request params
to these calls and back to a response — same split as ingest.py/db.py on
the write side.

Findings are timestamped in UTC (retrieved_at), but the audience is
Qatar-based, so "today" is a Qatar-local calendar day. Qatar doesn't
observe DST, so a fixed UTC+3 offset is safe without a timezone library.
week/month are rolling windows (last 7/30 days), not calendar-aligned —
a PM checking in gets a consistently full picture regardless of what day
of the week it is."""

from datetime import datetime, timedelta, timezone
from html import escape

from psycopg2.extras import RealDictCursor

QATAR_OFFSET = timedelta(hours=3)
MAX_LIMIT = 200
DEFAULT_LIMIT = 50

# high > medium > low; a bare `ORDER BY materiality DESC` would sort the
# TEXT column alphabetically (medium, low, high) instead.
MATERIALITY_RANK_SQL = "CASE materiality WHEN 'high' THEN 3 WHEN 'medium' THEN 2 WHEN 'low' THEN 1 ELSE 0 END"


def _window_start(window: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    if window == "today":
        qatar_midnight = (now + QATAR_OFFSET).replace(hour=0, minute=0, second=0, microsecond=0)
        return qatar_midnight - QATAR_OFFSET
    if window == "week":
        return now - timedelta(days=7)
    if window == "month":
        return now - timedelta(days=30)
    return None  # "all"


def list_findings(
    conn, *, company: str | None = None, category: str | None = None, window: str = "all",
    prioritized: bool | None = None, include_duplicates: bool = False,
    limit: int = DEFAULT_LIMIT, offset: int = 0,
) -> list[dict]:
    if prioritized is None:
        prioritized = window in ("week", "month")
    limit = max(1, min(limit, MAX_LIMIT))

    clauses = []
    params: list = []
    if not include_duplicates:
        clauses.append("f.is_duplicate = false")
    start = _window_start(window)
    if start is not None:
        clauses.append("f.retrieved_at >= %s")
        params.append(start)
    if company:
        clauses.append("f.company = %s")
        params.append(company)
    if category:
        clauses.append("f.category = %s")
        params.append(category)

    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    order_sql = (
        f"ORDER BY {MATERIALITY_RANK_SQL} DESC, f.retrieved_at DESC" if prioritized
        else "ORDER BY f.retrieved_at DESC"
    )

    query = f"""
        SELECT f.id, f.keyword, f.company, f.category, f.platform, f.source_url, f.title,
               f.summary, f.source_excerpt, f.published_at, f.retrieved_at, f.is_duplicate,
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


def list_companies(conn) -> list[dict]:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT company,
                   COUNT(*) FILTER (WHERE retrieved_at >= %(today)s AND NOT is_duplicate) AS new_today,
                   COUNT(*) FILTER (WHERE retrieved_at >= %(week)s AND NOT is_duplicate) AS new_this_week,
                   COUNT(*) FILTER (WHERE retrieved_at >= %(month)s AND NOT is_duplicate) AS new_this_month,
                   COUNT(*) AS total_findings
            FROM findings
            GROUP BY company
            ORDER BY company
            """,
            {
                "today": _window_start("today"),
                "week": _window_start("week"),
                "month": _window_start("month"),
            },
        )
        return cur.fetchall()
