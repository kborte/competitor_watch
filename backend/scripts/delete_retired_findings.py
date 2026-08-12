"""One-off maintenance script: permanently delete every finding belonging to a
retired competitor (companies.RETIRED_ALIASES), along with its audit chain.

    python3 -m backend.scripts.delete_retired_findings            # dry run
    python3 -m backend.scripts.delete_retired_findings --apply    # writes

Deletion walks the foreign keys inward-out — changes -> llm_calls -> findings
— then cleans up two things that would otherwise be left dangling:

- seen_urls rows for URLs no surviving finding references. Left behind, a URL
  stays in the dedup ledger, so if the market-wide keyword ever surfaces that
  page again it would be judged a duplicate on first sighting and never
  classified.
- routine_runs that held only deleted findings. These are per-finding delivery
  receipts, so a run whose one finding is gone is pure orphan. Runs that
  legitimately carry zero findings (the keywords_with_no_findings markers) are
  NOT touched: only runs identified from the deleted findings' own run_ids are
  considered, never "any run with no findings".

The raw payload in routine_runs.raw_payload is the only verbatim copy of what
the crawler delivered, so removing those rows is what makes this deletion
actually complete rather than leaving the data readable in JSON.
"""

import argparse

from .. import companies, db


def run(apply: bool) -> None:
    aliases = companies.retired_aliases()
    if not aliases:
        print("RETIRED_ALIASES is empty — nothing to delete.")
        return

    print(f"retired aliases: {aliases}")
    print(f"{'APPLYING' if apply else 'DRY RUN'}\n")

    with db.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, run_id, source_url FROM findings WHERE company = ANY(%s)",
                (aliases,),
            )
            rows = cur.fetchall()

        if not rows:
            print("no matching findings.")
            return

        finding_ids = [r[0] for r in rows]
        run_ids = sorted({r[1] for r in rows})
        urls = sorted({r[2] for r in rows})
        print(f"  findings to delete:        {len(finding_ids)}")
        print(f"  distinct source URLs:      {len(urls)}")
        print(f"  routine_runs referenced:   {len(run_ids)}")

        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM llm_calls WHERE finding_id = ANY(%s)", (finding_ids,))
            n_calls = cur.fetchone()[0]
            cur.execute(
                """
                SELECT count(*) FROM changes
                WHERE llm_call_id IN (SELECT id FROM llm_calls WHERE finding_id = ANY(%s))
                """,
                (finding_ids,),
            )
            n_changes = cur.fetchone()[0]
            # URLs that only these findings reference — anything shared with a
            # surviving finding must keep its ledger entry.
            cur.execute(
                """
                SELECT count(*) FROM seen_urls s
                WHERE s.source_url = ANY(%s)
                  AND NOT EXISTS (
                      SELECT 1 FROM findings f
                      WHERE f.source_url = s.source_url AND f.id <> ALL(%s)
                  )
                """,
                (urls, finding_ids),
            )
            n_seen = cur.fetchone()[0]
            cur.execute(
                """
                SELECT count(*) FROM routine_runs r
                WHERE r.id = ANY(%s)
                  AND NOT EXISTS (
                      SELECT 1 FROM findings f
                      WHERE f.run_id = r.id AND f.id <> ALL(%s)
                  )
                """,
                (run_ids, finding_ids),
            )
            n_runs = cur.fetchone()[0]

        print(f"  llm_calls to delete:       {n_calls}")
        print(f"  changes to delete:         {n_changes}")
        print(f"  seen_urls to delete:       {n_seen}")
        print(f"  routine_runs to delete:    {n_runs}  (of {len(run_ids)} referenced)")

        if not apply:
            print("\ndry run — pass --apply to write.")
            return

        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM changes
                WHERE llm_call_id IN (SELECT id FROM llm_calls WHERE finding_id = ANY(%s))
                """,
                (finding_ids,),
            )
            deleted_changes = cur.rowcount
            cur.execute("DELETE FROM llm_calls WHERE finding_id = ANY(%s)", (finding_ids,))
            deleted_calls = cur.rowcount
            # seen_urls and routine_runs are resolved BEFORE the findings go,
            # while the "is anything else still using this?" check can still
            # see the rows it needs to compare against.
            cur.execute(
                """
                DELETE FROM seen_urls s
                WHERE s.source_url = ANY(%s)
                  AND NOT EXISTS (
                      SELECT 1 FROM findings f
                      WHERE f.source_url = s.source_url AND f.id <> ALL(%s)
                  )
                """,
                (urls, finding_ids),
            )
            deleted_seen = cur.rowcount
            cur.execute("DELETE FROM findings WHERE id = ANY(%s)", (finding_ids,))
            deleted_findings = cur.rowcount
            cur.execute(
                """
                DELETE FROM routine_runs r
                WHERE r.id = ANY(%s)
                  AND NOT EXISTS (SELECT 1 FROM findings f WHERE f.run_id = r.id)
                """,
                (run_ids,),
            )
            deleted_runs = cur.rowcount

        print(f"\n  deleted changes:      {deleted_changes}")
        print(f"  deleted llm_calls:    {deleted_calls}")
        print(f"  deleted seen_urls:    {deleted_seen}")
        print(f"  deleted findings:     {deleted_findings}")
        print(f"  deleted routine_runs: {deleted_runs}")
        print("\napplied.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run)")
    args = parser.parse_args()
    run(apply=args.apply)


if __name__ == "__main__":
    main()
