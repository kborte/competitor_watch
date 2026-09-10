"""One-off: re-classify `regulatory` findings against the expanded taxonomy.

Added investment_or_acquisition and financial_results, and tightened regulatory to
mean compliance/licensing specifically. Uses its own prompt rather than
classify.py, which judges materiality and takes the crawler's category as given.

    python3 -m backend.scripts.reclassify_regulatory [--limit N] [--apply]
"""

import argparse
import logging
from datetime import UTC, datetime

from google import genai
from google.genai import types
from pydantic import BaseModel

from .. import config, db
from ..reads.windows import CRAWL_RECENCY_CATEGORIES
from ..schemas import Category

log = logging.getLogger("reclassify_regulatory")

client = genai.Client()
MODEL = config.GEMINI_MODEL

PROMPT_TEMPLATE = """A competitor-watch finding was tagged "regulatory" under an old, looser \
category scheme. Re-classify it under the current taxonomy:

- product: a change to what's actually offered — new coverage, features, pricing structure.
- marketing: campaigns, promotions, sponsorships, brand pushes.
- news: general press coverage not covered by a more specific bucket below.
- social_sentiment: reviews, social media, forum mentions.
- regulatory: compliance, licensing, conduct frameworks, disclosure requirements — a regulator \
being involved is not sufficient on its own; the finding must be about compliance/licensing \
itself, not merely announced through a regulatory process.
- investment_or_acquisition: M&A, stake changes, funding rounds, new subsidiary formation.
- financial_results: earnings, profit/loss, dividends, capital raises — even when a regulator \
had to approve the raise itself, the story is financial, not regulatory.
- other: doesn't fit any of the above.

Title: {title}
Summary: {summary}
Excerpt: "{source_excerpt}"

Return exactly one category from the list above — the one that best fits, even if it's still \
"regulatory"."""


class _CategoryOnly(BaseModel):
    """Category alone — this script re-judges nothing else."""

    category: Category


def reclassify_one(title: str, summary: str, source_excerpt: str) -> tuple[str, str, str]:
    """Asks the model to re-bucket one finding under the current taxonomy.
    Returns (category, prompt, raw_output) so the change stays attributable."""
    prompt = PROMPT_TEMPLATE.format(title=title, summary=summary, source_excerpt=source_excerpt)
    response = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=_CategoryOnly),
    )
    if response.parsed is None:
        raise ValueError(f"model returned no parseable category: {(response.text or '')[:200]!r}")
    return response.parsed.category, prompt, response.text


def run(apply: bool, limit: int | None = None) -> None:
    """Re-judges every regulatory finding, as one all-or-nothing transaction."""
    with db.connect() as conn:
        with conn.cursor() as cur:
            query = ("SELECT id, title, summary, source_excerpt, published_at "
                     "FROM findings WHERE category = 'regulatory' ORDER BY id")
            if limit:
                query += f" LIMIT {limit}"
            cur.execute(query)
            rows = cur.fetchall()

        log.info("found %d finding(s) tagged 'regulatory'. %s.",
                 len(rows), "APPLYING" if apply else "DRY RUN")
        changed = recency_shifts = 0
        for finding_id, title, summary, source_excerpt, published_at in rows:
            new_category, prompt, raw_output = reclassify_one(title, summary, source_excerpt)
            if new_category == "regulatory":
                continue
            changed += 1

            # Category decides whether an undated finding may use crawl time as
            # its date (see reads/windows.CRAWL_RECENCY_CATEGORIES), so moving a
            # finding between the two groups changes which time windows it
            # appears in. 'regulatory' is a dated category, so every move here
            # can only *add* window visibility — but the hazard is real in the
            # other direction, and a silent change either way is worth naming.
            was_crawl_recency = "regulatory" in CRAWL_RECENCY_CATEGORIES
            now_crawl_recency = new_category in CRAWL_RECENCY_CATEGORIES
            shifted = published_at is None and was_crawl_recency != now_crawl_recency
            if shifted:
                recency_shifts += 1

            log.info("#%s: regulatory -> %s%s — %r", finding_id, new_category,
                     "  [freshness class changes: undated row]" if shifted else "", title)

            if apply:
                # Recorded in the audit chain, not mutated silently: the same
                # llm_calls row that every other verdict gets, so "why is this
                # finding tagged this way" stays answerable.
                db.insert_llm_call(
                    conn, finding_id, MODEL, prompt, raw_output,
                    datetime.now(UTC),
                )
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE findings SET category = %s WHERE id = %s",
                        (new_category, finding_id),
                    )

        log.info("%d/%d reclassified%s", changed, len(rows),
                 " (applied)" if apply else " (dry run — pass --apply to write)")
        if recency_shifts:
            log.warning("%d undated finding(s) changed freshness class — verify they still "
                        "appear in the expected time windows", recency_shifts)


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run only)")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N rows")
    args = parser.parse_args()
    run(apply=args.apply, limit=args.limit)


if __name__ == "__main__":
    main()
