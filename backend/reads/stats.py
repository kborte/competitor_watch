"""Aggregate rollups: the dashboard KPI block (/stats) and the per-company counts
behind the filter chips (/companies).

Both group by canonical entity rather than raw company string, and both apply the
same freshness rule as the feed, so a KPI can never count something the feed
would not show.
"""

from psycopg2.extras import RealDictCursor

from .. import companies
from . import windows
from .findings import EFFECTIVE_CATEGORY_SQL

_TONES = ("positive", "negative", "neutral", "mixed")


def list_companies(conn) -> list[dict]:
    """Per-company finding counts for today, this week, this month and all time,
    grouped by canonical name."""
    # Three windows in one pass, so the query binds by name rather than position.
    # Grouping happens in Python afterwards: there are at most a handful of
    # distinct raw company strings, not worth mirroring the alias map into SQL.
    retrieved_today, published_today = windows.bounds("today")
    retrieved_week, published_week = windows.bounds("week")
    retrieved_month, published_month = windows.bounds("month")

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT company,
                   COUNT(*) FILTER (
                       WHERE {windows.freshness_sql_named("today", "findings")} AND NOT is_duplicate
                   ) AS new_today,
                   COUNT(*) FILTER (
                       WHERE {windows.freshness_sql_named("week", "findings")} AND NOT is_duplicate
                   ) AS new_this_week,
                   COUNT(*) FILTER (
                       WHERE {windows.freshness_sql_named("month", "findings")} AND NOT is_duplicate
                   ) AS new_this_month,
                   COUNT(*) AS total_findings
            FROM findings
            WHERE NOT is_reference AND company != ALL(%(retired)s)
            GROUP BY company
            """,
            {
                "today_date": published_today, "today_instant": retrieved_today,
                "week_date": published_week, "week_instant": retrieved_week,
                "month_date": published_month, "month_instant": retrieved_month,
                "crawl_recency_cats": windows.CRAWL_RECENCY_CATEGORIES,
                "retired": companies.retired_aliases(),
            },
        )
        raw_rows = cur.fetchall()

    # Several raw spellings can collapse into one canonical company, so counts
    # are summed rather than assigned.
    grouped: dict[str, dict] = {}
    for row in raw_rows:
        name = companies.canonical_name(row["company"])
        bucket = grouped.setdefault(name, {
            "company": name, "new_today": 0, "new_this_week": 0,
            "new_this_month": 0, "total_findings": 0,
        })
        for field in ("new_today", "new_this_week", "new_this_month", "total_findings"):
            bucket[field] += row[field]

    return sorted(grouped.values(), key=lambda r: r["company"])


def _period_clause(window: str, prior: bool) -> tuple[str | None, list]:
    """Freshness clause for the current or the immediately preceding window,
    as (sql_or_None, bind_params)."""
    if prior:
        params = windows.prior_params(window)
        # "all" has no preceding period. Match nothing rather than silently
        # comparing the current window against the whole history.
        return ("FALSE", []) if params is None else (windows.prior_sql(), params)
    params = windows.freshness_params(window)
    return (None, []) if params is None else (windows.freshness_sql(), params)


def _rows(
    conn, *, company: str | None, category: str | None, line: str | None,
    window: str, prior: bool, reference: bool,
) -> list[dict]:
    """One per-company aggregate slice, scoped to competitors or to the QIC
    reference set, for either the current or the preceding window."""
    clauses = ["NOT f.is_duplicate", "f.is_reference = %s", "f.company != ALL(%s)"]
    params: list = [reference, companies.retired_aliases()]

    period_sql, period_params = _period_clause(window, prior)
    if period_sql:
        clauses.append(period_sql)
        params.extend(period_params)

    if not reference:
        if company == companies.MARKET_BUCKET:
            clauses.append("f.company != ALL(%s)")
            params.append(companies.known_aliases())
        elif company:
            clauses.append("f.company = ANY(%s)")
            params.append(companies.aliases_for(company))
    if category:
        # Same precedence as the feed, so a category-filtered KPI counts exactly
        # the findings a category-filtered feed would list.
        clauses.append(f"{EFFECTIVE_CATEGORY_SQL} = %s")
        params.append(category)
    if line:
        clauses.append("f.line = %s")
        params.append(line)

    # Tone is only ever recorded on social_sentiment findings, so each tone
    # count is guarded on the category as well as the value.
    tone_counts = ",\n                   ".join(
        f"COUNT(*) FILTER (WHERE f.category = 'social_sentiment' AND f.tone = '{tone}') AS {tone}"
        for tone in _TONES
    )
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            f"""
            SELECT f.company, COUNT(*) AS finding_count,
                   COUNT(*) FILTER (WHERE c.materiality = 'high') AS high_count,
                   {tone_counts}
            FROM findings f
            LEFT JOIN llm_calls lc ON lc.finding_id = f.id
            LEFT JOIN classifications c ON c.llm_call_id = lc.id
            WHERE {' AND '.join(clauses)}
            GROUP BY f.company
            """,
            params,
        )
        return cur.fetchall()


def _totals(rows: list[dict]) -> dict:
    """Collapses per-company aggregate rows into one set of totals."""
    return {
        "findings": sum(row["finding_count"] for row in rows),
        "high_materiality": sum(row["high_count"] for row in rows),
        "tone": {tone: sum(row[tone] for row in rows) for tone in _TONES},
    }


def _most_active(rows: list[dict]) -> dict | None:
    """The canonical company with the most findings in the slice, or None when
    there are none. Ties break alphabetically so the result is stable."""
    counts: dict[str, int] = {}
    for row in rows:
        canonical = companies.canonical_name(row["company"])
        counts[canonical] = counts.get(canonical, 0) + row["finding_count"]
    if not counts:
        return None
    name, count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
    return {"company": name, "count": count}


def get_stats(
    conn, *, company: str | None = None, category: str | None = None,
    line: str | None = None, window: str = "week",
) -> dict:
    """The dashboard KPI block: competitor and QIC-reference totals for the
    window, each against the preceding period for a delta."""
    has_prior = window != "all"  # "all" has nothing to compare against

    def slice_(*, prior: bool, reference: bool) -> list[dict]:
        """One of the four slices, with the reference set exempt from filters."""
        # The QIC reference set is a fixed benchmark, so a company filter chosen
        # for the competitor feed must not narrow it.
        return _rows(
            conn, company=None if reference else company, category=category, line=line,
            window=window, prior=prior, reference=reference,
        )

    current_rows = slice_(prior=False, reference=False)
    current = _totals(current_rows)
    previous = _totals(slice_(prior=True, reference=False)) if has_prior else None
    qic_current = _totals(slice_(prior=False, reference=True))
    qic_previous = _totals(slice_(prior=True, reference=True)) if has_prior else None

    return {
        "window": window,
        "current": current,
        "previous": previous,
        "delta": None if previous is None else current["findings"] - previous["findings"],
        "most_active": _most_active(current_rows),
        "qic_reference": {
            "mentions": qic_current["findings"],
            "previous_mentions": None if qic_previous is None else qic_previous["findings"],
            "tone": qic_current["tone"],
            "previous_tone": None if qic_previous is None else qic_previous["tone"],
        },
    }
