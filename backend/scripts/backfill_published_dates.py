"""One-off maintenance script: recover `published_at` for findings stored
before deterministic date extraction existed (they only ever got the LLM's
text-based guess, which usually came back empty because the page's real
date lives in <meta>/JSON-LD markup that never survives into the text the
LLM sees).

    python3 -m backend.scripts.backfill_published_dates            # dry run
    python3 -m backend.scripts.backfill_published_dates --apply    # writes

Re-fetches each undated finding's source_url and runs the crawler's own
extract_published_date() over the fresh HTML, so the crawler and this
backfill can never disagree about what a date is. Fetches once per
distinct URL (many findings share one) with a small delay between hits.

Rows that stay null after this are genuinely dateless — evergreen listing
pages, app-store entries, offer pages — not extraction failures.
"""

import argparse
import sys
import time
from collections import defaultdict

# The crawler is a sibling package deployed separately from the backend;
# for a local maintenance script it's fine to import from it directly
# rather than duplicating the extraction logic and letting the two drift.
sys.path.insert(0, __file__.rsplit("/backend/", 1)[0])

from research_crawler.fetch import extract_date_from_url, extract_published_date  # noqa: E402
import requests  # noqa: E402

from .. import db  # noqa: E402

USER_AGENT = "QIC-CompetitorWatch/1.0 (internal competitive-intelligence monitor)"
DELAY_SECONDS = 0.5
SKIP_URL_MARKERS = ("vertexaisearch.cloud.google.com/grounding-api-redirect",)


def resolve_date(url: str, timeout: int = 15) -> str | None:
    """Fresh fetch → structured-markup extraction, falling back to the URL
    path. Returns None if the page can't be reached or carries no date."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException:
        return extract_date_from_url(url)  # page unreachable; path may still carry it

    if "html" not in resp.headers.get("Content-Type", "").lower():
        return extract_date_from_url(resp.url)
    return extract_published_date(resp.text, resp.url)


def run(apply: bool, limit: int | None = None) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT source_url, array_agg(id) FROM findings
                WHERE published_at IS NULL GROUP BY source_url ORDER BY min(id)
            """
            if limit:
                query += f" LIMIT {limit}"
            cur.execute(query)
            url_groups = cur.fetchall()

        total_rows = sum(len(ids) for _, ids in url_groups)
        print(f"{len(url_groups)} distinct URL(s) across {total_rows} undated finding(s). "
              f"{'APPLYING' if apply else 'DRY RUN'}.\n")

        stats: dict[str, int] = defaultdict(int)
        for url, finding_ids in url_groups:
            if any(marker in url for marker in SKIP_URL_MARKERS):
                stats["skipped_dead_redirect"] += len(finding_ids)
                continue

            date = resolve_date(url)
            time.sleep(DELAY_SECONDS)

            if date is None:
                stats["no_date_found"] += len(finding_ids)
                continue

            stats["dated"] += len(finding_ids)
            print(f"  {date}  ({len(finding_ids)} row(s))  {url[:90]}")
            if apply:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE findings SET published_at = %s WHERE id = ANY(%s)",
                        (date, finding_ids),
                    )

        print(f"\n  dated:                 {stats['dated']}")
        print(f"  no date on page:       {stats['no_date_found']}")
        print(f"  skipped (dead links):  {stats['skipped_dead_redirect']}")
        print("\n" + ("applied." if apply else "dry run — pass --apply to write."))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run)")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N distinct URLs")
    args = parser.parse_args()
    run(apply=args.apply, limit=args.limit)


if __name__ == "__main__":
    main()
