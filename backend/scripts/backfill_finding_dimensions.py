"""Backfill line, tone, and source-location fields on pre-v4 findings.

Runs dry by default:

    python3 -m backend.scripts.backfill_finding_dimensions
    python3 -m backend.scripts.backfill_finding_dimensions --limit 10
    python3 -m backend.scripts.backfill_finding_dimensions --apply

The prompt uses the same fixed taxonomy as the live crawler. Existing fields
are only filled when missing, so rerunning the script is safe.
"""

import argparse

from google import genai
from google.genai import types
from pydantic import BaseModel

from .. import db
from ..htmlutil import extract_clean_text
from ..schemas import Line, Tone

client = genai.Client()
MODEL = "gemini-3.6-flash"


class Dimensions(BaseModel):
    line: Line
    tone: Tone | None = None
    source_location: str | None = None


PROMPT = """Classify this stored competitor-watch finding.

line must be exactly one of: motor, health, travel, marine, energy, aviation, pab, home, yacht,
market_wide, outside_our_lines. Website/app are channels: use the underlying insurance line when
specific, market_wide for cross-line platform or general corporate changes, and outside_our_lines
for genuinely non-insurance products or insurance covers outside QIC's nine listed lines.

tone is positive, negative, neutral, or mixed for social_sentiment; otherwise omit it.
source_location is a short location such as "Opening paragraph" or "Under Renewals" only when
the supplied page text makes it identifiable; otherwise omit it.

Category: {category}
Title: {title}
Summary: {summary}
Excerpt: {excerpt}
Page text: {page_text}
"""


def classify_dimensions(row: dict) -> Dimensions:
    clean_text = extract_clean_text(row["source_html"])[:6000] if row["source_html"] else "(unavailable)"
    prompt = PROMPT.format(
        category=row["category"], title=row["title"], summary=row["summary"],
        excerpt=row["source_excerpt"], page_text=clean_text,
    )
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=Dimensions,
        ),
    )
    return response.parsed


def run(apply: bool, limit: int | None = None) -> None:
    with db.connect() as conn:
        with conn.cursor() as cur:
            query = """
                SELECT id, category, title, summary, source_excerpt, source_html,
                       line, tone, source_location
                FROM findings
                WHERE line IS NULL OR (category = 'social_sentiment' AND tone IS NULL)
                ORDER BY id
            """
            if limit:
                query += " LIMIT %s"
                cur.execute(query, (limit,))
            else:
                cur.execute(query)
            columns = [desc[0] for desc in cur.description]
            rows = [dict(zip(columns, values)) for values in cur.fetchall()]

        print(f"{len(rows)} finding(s) need dimensions. {'APPLYING' if apply else 'DRY RUN'}.")
        for row in rows:
            result = classify_dimensions(row)
            line = row["line"] or result.line
            tone = row["tone"] or result.tone
            source_location = row["source_location"] or result.source_location
            print(f"  #{row['id']}: {line}, tone={tone or '—'}, location={source_location or '—'}")
            if apply:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE findings SET line = %s, tone = %s, source_location = %s WHERE id = %s",
                        (line, tone, source_location, row["id"]),
                    )

        print("applied." if apply else "dry run — pass --apply to write.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    run(apply=args.apply, limit=args.limit)


if __name__ == "__main__":
    main()
