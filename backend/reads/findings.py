"""The findings feed (/findings) and single-finding detail (/findings/{id}).

Every finding carries the crawler's category; the subset that was classified also
carries the backend classifier's second opinion. These queries show the
classifier's verdict where one exists and fall back to the crawler's otherwise,
consistently across both the visible label and the category filter.
"""

from psycopg2.extras import RealDictCursor

from .. import companies
from . import windows

MAX_LIMIT = 200
DEFAULT_LIMIT = 50

# high > medium > low. A bare `ORDER BY materiality DESC` would sort the TEXT
# column alphabetically — medium, low, high — which is not an ordering at all.
MATERIALITY_RANK_SQL = (
    "CASE materiality WHEN 'high' THEN 3 WHEN 'medium' THEN 2 WHEN 'low' THEN 1 ELSE 0 END"
)

# The resolved category: the classifier's where it exists, the crawler's
# otherwise. Used for both the SELECT and the category filter so a card's visible
# label always matches what filtering on that label returns. Deliberately NOT
# used for freshness — see windows.CRAWL_RECENCY_CATEGORIES.
EFFECTIVE_CATEGORY_SQL = "COALESCE(c.category, f.category)"


def _order_sql(sort_by: str, sort_dir: str) -> str:
    """Builds the ORDER BY clause, falling back to a safe default for any
    unrecognized value."""
    # The fallback is not redundant with main.py's Literal types: these values
    # become raw SQL text rather than bind parameters, so an unrecognized one
    # must degrade to a default rather than reach interpolation unchecked.
    direction = "ASC" if sort_dir == "asc" else "DESC"
    if sort_by == "materiality":
        return f"ORDER BY {MATERIALITY_RANK_SQL} {direction}, f.retrieved_at DESC"
    if sort_by == "published_at":
        return f"ORDER BY f.published_at {direction} NULLS LAST, f.retrieved_at DESC"
    return f"ORDER BY f.retrieved_at {direction}"


def list_findings(
    conn, *, company: str | None = None, category: str | None = None, line: str | None = None,
    materiality: str | None = None, window: str = "all",
    sort_by: str = "materiality", sort_dir: str = "desc", include_duplicates: bool = False,
    limit: int = DEFAULT_LIMIT, offset: int = 0,
) -> list[dict]:
    """The main competitor feed: filtered, freshness-scoped and sorted findings.
    QIC reference rows and retired competitors are always excluded."""
    limit = max(1, min(limit, MAX_LIMIT))

    clauses = ["f.is_reference = false", "f.company != ALL(%s)"]
    params: list = [companies.retired_aliases()]
    if not include_duplicates:
        clauses.append("f.is_duplicate = false")

    freshness_params = windows.freshness_params(window)
    if freshness_params is not None:  # None means "all" — no time filter at all
        clauses.append(windows.freshness_sql())
        params.extend(freshness_params)

    if company == companies.MARKET_BUCKET:
        # The market bucket is an inverse set — "not any recognized competitor" —
        # rather than a finite alias list like every other entity.
        clauses.append("f.company != ALL(%s)")
        params.append(companies.known_aliases())
    elif company:
        clauses.append("f.company = ANY(%s)")
        params.append(companies.aliases_for(company))
    if category:
        clauses.append(f"{EFFECTIVE_CATEGORY_SQL} = %s")
        params.append(category)
    if line:
        clauses.append("f.line = %s")
        params.append(line)
    if materiality:
        clauses.append("c.materiality = %s")
        params.append(materiality)

    # LEFT JOINs throughout: a finding only has an llm_calls/classifications row
    # if it was actually classified, which duplicates and reference rows are not.
    query = f"""
        SELECT f.id, f.keyword, f.company, {EFFECTIVE_CATEGORY_SQL} AS category,
               f.category AS crawler_category, c.category AS classified_category,
               f.platform, f.source_url, f.title,
               f.summary, f.source_excerpt, f.published_at, f.retrieved_at, f.is_duplicate,
               f.og_title, f.og_image_url, f.og_description, f.og_site_name, f.verified,
               f.line, f.tone, f.source_location,
               c.materiality
        FROM findings f
        LEFT JOIN llm_calls lc ON lc.finding_id = f.id
        LEFT JOIN classifications c ON c.llm_call_id = lc.id
        WHERE {' AND '.join(clauses)}
        {_order_sql(sort_by, sort_dir)}
        LIMIT %s OFFSET %s
    """
    params.extend([limit, offset])
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(query, params)
        return cur.fetchall()


def get_finding(conn, finding_id: int, view: str = "full") -> dict | None:
    """One finding plus its audit trail, or None if the id doesn't exist.
    view="summary" keeps the verdict but omits the raw prompt and model output."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("SELECT * FROM findings WHERE id = %s", (finding_id,))
        finding = cur.fetchone()
        if finding is None:
            return None

        cur.execute(
            """
            SELECT lc.model, lc.prompt, lc.raw_output, lc.called_at,
                   c.category, c.materiality, c.confidence, c.evidence_quote,
                   c.rationale, c.grounded
            FROM llm_calls lc
            LEFT JOIN classifications c ON c.llm_call_id = lc.id
            WHERE lc.finding_id = %s
            """,
            (finding_id,),
        )
        audit = cur.fetchone()

    result = dict(finding)
    # source_html can be megabytes; callers get a flag and fetch it from
    # /snapshot only if they actually want to render it.
    result["has_snapshot"] = result.pop("source_html") is not None

    # Same category precedence as the feed, so the detail view can never
    # disagree with the card the reader clicked through from.
    result["crawler_category"] = result["category"]
    result["classified_category"] = audit["category"] if audit else None
    if audit and audit["category"]:
        result["category"] = audit["category"]

    result["change"] = {
        "materiality": audit["materiality"],
        "confidence": audit["confidence"],
        "evidence_quote": audit["evidence_quote"],
        "rationale": audit["rationale"],
        # NULL on rows classified before this was recorded: "not judged",
        # which is not the same claim as "judged unsupported".
        "grounded": audit["grounded"],
    } if audit else None
    result["llm_call"] = {
        "model": audit["model"],
        "prompt": audit["prompt"],
        "raw_output": audit["raw_output"],
        "called_at": audit["called_at"],
    } if (audit and view == "full") else None
    return result


def get_snapshot(conn, finding_id: int) -> dict | None:
    """The captured page HTML for a finding as {"source_url", "html"}, or None if
    the finding doesn't exist. "html" is itself None when nothing was captured."""
    with conn.cursor() as cur:
        cur.execute("SELECT source_url, source_html FROM findings WHERE id = %s", (finding_id,))
        row = cur.fetchone()
    if row is None:
        return None
    source_url, html = row
    return {"source_url": source_url, "html": html}


def get_latest_crawl_at(conn):
    """When the crawler last delivered anything, for the dashboard's staleness
    indicator."""
    # Retired competitors are excluded: their newest rows are frozen at whenever
    # tracking stopped, so counting them would report a time that never moves.
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(retrieved_at) FROM findings WHERE company != ALL(%s)",
            (companies.retired_aliases(),),
        )
        return cur.fetchone()[0]
