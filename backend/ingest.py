"""Core ingest logic — dedup, classify, store — sitting behind the HTTP
route in main.py. Kept separate from the transport so the processing
doesn't care how a validated IngestPayload arrived."""

from datetime import datetime, timezone

from . import classify, db, dedup
from .schemas import IngestPayload


def process(payload: IngestPayload) -> dict:
    with db.connect() as conn:
        if db.run_exists(conn, payload.routine_run_id):
            return {"status": "already processed", "routine_run_id": payload.routine_run_id}

        db.insert_run(
            conn, payload.routine_run_id,
            datetime.now(timezone.utc),
            payload.model_dump(mode="json"),
        )

        new_count = duplicate_count = error_count = 0
        for finding in payload.findings:
            needs_classification, hash_value = dedup.check(conn, finding)
            finding_id = db.insert_finding(
                conn, payload.routine_run_id, finding, is_duplicate=not needs_classification,
            )
            db.upsert_seen_url(
                conn, dedup.normalize_url(finding.source_url), finding.category,
                payload.routine_run_id, hash_value,
                scope="reference" if finding.is_reference else "competitor",
            )

            if not needs_classification:
                duplicate_count += 1
                continue

            # QIC is a benchmark, not a competitor. Its line/tone/source
            # context is already structured by the crawler; assigning
            # competitor materiality would be misleading and wasteful.
            if finding.is_reference:
                new_count += 1
                continue

            try:
                classification, prompt, raw_output = classify.classify(finding)
            except Exception:
                error_count += 1
                continue

            llm_call_id = db.insert_llm_call(
                conn, finding_id, classify.MODEL, prompt, raw_output,
                datetime.now(timezone.utc),
            )
            db.insert_change(conn, llm_call_id, classification)
            new_count += 1

    return {
        "status": "processed",
        "routine_run_id": payload.routine_run_id,
        "new_or_changed": new_count,
        "duplicates": duplicate_count,
        "errors": error_count,
    }
