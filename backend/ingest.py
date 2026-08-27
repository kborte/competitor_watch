"""The write path: what happens to one delivered payload.

Store the payload verbatim, then for each finding decide novelty (dedup), spend an
LLM call only if it earned one (classify), and record the result with its audit
chain (db). Kept separate from the HTTP route in main.py so the processing does
not care how a validated payload arrived. Idempotent on routine_run_id.
"""

from datetime import datetime, timezone

from . import classify, db, dedup
from .schemas import IngestPayload


def process(payload: IngestPayload) -> dict:
    """Stores one delivery and classifies whatever in it is genuinely new.
    Returns per-payload counts for the crawler's log."""
    with db.connect() as conn:
        # A retried delivery is a no-op, not a duplicate: the crawler retries on
        # timeout and cannot know whether the first attempt landed.
        if db.run_exists(conn, payload.routine_run_id):
            return {"status": "already processed", "routine_run_id": payload.routine_run_id}

        db.insert_run(
            conn, payload.routine_run_id,
            datetime.now(timezone.utc),
            payload.model_dump(mode="json"),
        )

        new_count = duplicate_count = error_count = 0
        for finding in payload.findings:
            # Every finding is stored regardless of what follows. Only the
            # classification below is conditional, which is why classifications
            # rows are sparse relative to findings.
            needs_classification, hash_value = dedup.check(conn, finding)
            finding_id = db.insert_finding(
                conn, payload.routine_run_id, finding, is_duplicate=not needs_classification,
            )
            db.upsert_seen_url(
                conn, dedup.normalize_url(finding.source_url), finding.category,
                payload.routine_run_id, hash_value,
                scope="reference" if finding.is_reference else "competitor",
            )

            # Skip 1 of 3 — already seen, and unchanged if it was the kind of
            # page whose content we re-hash.
            if not needs_classification:
                duplicate_count += 1
                continue

            # Skip 2 of 3 — QIC is a benchmark, not a competitor. Its line/tone/
            # source context is already structured by the crawler; assigning it
            # competitor materiality would be misleading and wasteful.
            if finding.is_reference:
                new_count += 1
                continue

            # Skip 3 of 3 — one bad classification must not abort the rest of
            # the payload; the finding is already stored either way.
            try:
                classification, prompt, raw_output = classify.classify(finding)
            except Exception:
                error_count += 1
                continue

            llm_call_id = db.insert_llm_call(
                conn, finding_id, classify.MODEL, prompt, raw_output,
                datetime.now(timezone.utc),
            )
            db.insert_classification(conn, llm_call_id, classification)
            new_count += 1

    return {
        "status": "processed",
        "routine_run_id": payload.routine_run_id,
        "new_or_changed": new_count,
        "duplicates": duplicate_count,
        "errors": error_count,
    }
