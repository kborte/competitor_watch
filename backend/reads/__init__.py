"""Query layer behind the read API — the GET half of the backend.

main.py stays a thin translation from request params to these calls, the same
split ingest.py/db.py use on the write path. Three modules: windows.py holds the
time-window and freshness rule, findings.py the feed and detail queries, stats.py
the aggregate rollups. Everything public is re-exported here, so callers import
`reads` and never need to know which module a function lives in.
"""

from .findings import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    get_finding,
    get_latest_crawl_at,
    get_snapshot,
    list_findings,
)
from .stats import get_stats, list_companies

__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "get_finding",
    "get_latest_crawl_at",
    "get_snapshot",
    "get_stats",
    "list_companies",
    "list_findings",
]
