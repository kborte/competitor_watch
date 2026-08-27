"""One-off: re-classify `regulatory` findings against the expanded taxonomy.

Added investment_or_acquisition and financial_results, and tightened regulatory to
mean compliance/licensing specifically. Uses its own prompt rather than
classify.py, which judges materiality and takes the crawler's category as given.

    python3 -m backend.scripts.reclassify_regulatory [--limit N] [--apply]
"""

import argparse

from google import genai
from google.genai import types
from pydantic import BaseModel

from .. import db
from ..schemas import Category

client = genai.Client()
MODEL = "gemini-3.6-flash"

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


def reclassify_one(title: str, summary: str, source_excerpt: str) -> str:
    """Asks the model to re-bucket one finding under the current taxonomy."""
    prompt = PROMPT_TEMPLATE.format(title=title, summary=summary, source_excerpt=source_excerpt)
    response = client.models.generate_content(
        model=MODEL, contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=_CategoryOnly),
    )
    return response.parsed.category


def run(apply: bool, limit: int | None = None) -> None:
    """Re-judges every regulatory finding, as one all-or-nothing transaction."""
    with db.connect() as conn:
        with conn.cursor() as cur:
            query = "SELECT id, title, summary, source_excerpt FROM findings WHERE category = 'regulatory' ORDER BY id"
            if limit:
                query += f" LIMIT {limit}"
            cur.execute(query)
            rows = cur.fetchall()

        print(f"Found {len(rows)} finding(s) tagged 'regulatory'. {'APPLYING' if apply else 'DRY RUN'}.")
        changed = 0
        for finding_id, title, summary, source_excerpt in rows:
            new_category = reclassify_one(title, summary, source_excerpt)
            if new_category != "regulatory":
                changed += 1
                print(f"  #{finding_id}: regulatory -> {new_category} — {title!r}")
                if apply:
                    with conn.cursor() as cur:
                        cur.execute("UPDATE findings SET category = %s WHERE id = %s", (new_category, finding_id))

        print(f"\n{changed}/{len(rows)} would be reclassified"
              + (" (applied)" if apply else " (dry run — pass --apply to write)"))


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Actually write changes (default: dry-run only)")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N rows")
    args = parser.parse_args()
    run(apply=args.apply, limit=args.limit)


if __name__ == "__main__":
    main()
