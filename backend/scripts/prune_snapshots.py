"""Recurring maintenance: drop archived page HTML past its retention window.

Each snapshot is up to 2 MB and nothing ever removed them, so the findings table
grew without bound. Only `source_html` is cleared — the finding, its verdict and
the whole audit chain stay, so history remains readable; what is lost is the
ability to re-render that page as it looked. Run daily as a CronJob.

    python3 -m backend.scripts.prune_snapshots [--days N] [--apply]
"""

import argparse
import logging

from .. import config, db

log = logging.getLogger("prune_snapshots")

DEFAULT_RETENTION_DAYS = config.SNAPSHOT_RETENTION_DAYS


def run(apply: bool, days: int) -> None:
    """Reports, then optionally clears, snapshots older than the window."""
    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*), COALESCE(sum(length(source_html)), 0)
                FROM findings
                WHERE source_html IS NOT NULL
                  AND retrieved_at < now() - make_interval(days => %s)
                """,
                (days,),
            )
            count, total_bytes = cur.fetchone()
            log.info("retention %dd: %d snapshot(s) eligible, %.1f MB",
                     days, count, total_bytes / 1_048_576)

            if not apply:
                log.info("dry run — pass --apply to clear them")
                return
            if not count:
                return

            cur.execute(
                """
                UPDATE findings SET source_html = NULL
                WHERE source_html IS NOT NULL
                  AND retrieved_at < now() - make_interval(days => %s)
                """,
                (days,),
            )
            log.info("cleared %d snapshot(s)", cur.rowcount)


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=DEFAULT_RETENTION_DAYS,
                        help=f"retention window in days (default {DEFAULT_RETENTION_DAYS})")
    parser.add_argument("--apply", action="store_true",
                        help="actually clear snapshots (default: dry-run)")
    args = parser.parse_args()
    run(apply=args.apply, days=args.days)


if __name__ == "__main__":
    main()
