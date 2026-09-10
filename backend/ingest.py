"""The write path: what happens to one delivered payload.

Runs in three phases — claim the delivery and decide novelty, classify, then
write — so that no database transaction is held open across an LLM call. Kept
separate from the HTTP route in main.py so the processing does not care how a
validated payload arrived. Idempotent on routine_run_id.
"""

import logging
from datetime import UTC, datetime

from . import classify, db, dedup
from .schemas import IngestPayload

log = logging.getLogger(__name__)


def process(payload: IngestPayload) -> dict:
    """Stores one delivery and classifies whatever in it is genuinely new.
    Returns per-payload counts for the crawler's log."""
    # ---- Phase 1: claim the delivery, decide novelty. Short transaction. ----
    with db.connect() as conn:
        # Idempotent on routine_run_id: the same delivery can legitimately
        # arrive twice — a re-run of the workflow, or a manual dispatch — and
        # must not be counted twice. The crawler itself does not retry; a
        # delivery lost in transit is recovered by the next daily crawl, which
        # re-reports every finding it can still see.
        if db.run_exists(conn, payload.routine_run_id):
            return {"status": "already processed", "routine_run_id": payload.routine_run_id}

        # The verbatim delivery is retained even if no individual finding
        # survives classification below.
        db.insert_run(
            conn, payload.routine_run_id,
            datetime.now(UTC),
            payload.model_dump(mode="json"),
        )
        decisions = [(finding, *dedup.check(conn, finding)) for finding in payload.findings]

    # ---- Phase 2: classify. No transaction, no connection held. ----
    # An LLM call takes seconds and can be retried internally. Holding a
    # Postgres transaction across it would keep a connection and its locks idle
    # for that whole time, which at a few concurrent requests is enough to
    # exhaust the connection allowance of a managed database.
    verdicts: dict[int, tuple] = {}
    failed: set[int] = set()
    for index, (finding, needs_classification, _hash) in enumerate(decisions):
        # A verdict is spent only on a finding that is both new and a
        # competitor's. Duplicates are already judged; QIC is a benchmark, whose
        # line/tone context the crawler has already structured, so competitor
        # materiality would mislead.
        if not needs_classification or finding.is_reference:
            continue
        try:
            verdicts[index] = classify.classify(finding)
        except Exception:
            # Logged rather than silently counted: this is the failure that used
            # to strand a finding permanently, so it should be findable.
            log.exception("classification failed for %s", finding.source_url)
            failed.add(index)

    # ---- Phase 3: write. Short transaction, one savepoint per finding. ----
    new_count = duplicate_count = error_count = 0
    with db.connect() as conn:
        for index, (finding, needs_classification, hash_value) in enumerate(decisions):
            if index in failed:
                # Nothing is stored for this finding — not the row, not the
                # ledger entry. The next crawl re-reports it and tries again.
                error_count += 1
                continue

            try:
                # Everything this finding writes lands together or not at all,
                # so one bad row cannot abort the rest of the payload.
                with db.savepoint(conn):
                    finding_id = db.insert_finding(
                        conn, payload.routine_run_id, finding,
                        is_duplicate=not needs_classification,
                    )

                    if index in verdicts:
                        classification, prompt, raw_output, usage = verdicts[index]
                        llm_call_id = db.insert_llm_call(
                            conn, finding_id, classify.MODEL, prompt, raw_output,
                            datetime.now(UTC), usage=usage,
                        )
                        db.insert_classification(conn, llm_call_id, classification)

                    # The ledger entry goes last, in the same savepoint as the
                    # verdict. "I have seen this URL" and "here is my judgment
                    # of it" therefore become true at the same moment — so a
                    # failure above cannot leave the ledger suppressing a retry
                    # of a finding that never got judged.
                    db.upsert_seen_url(
                        conn, dedup.normalize_url(finding.source_url), finding.category,
                        payload.routine_run_id, hash_value,
                        scope="reference" if finding.is_reference else "competitor",
                    )
            except Exception:
                log.exception("storing finding failed for %s", finding.source_url)
                error_count += 1
                continue

            if needs_classification:
                new_count += 1
            else:
                duplicate_count += 1

    return {
        "status": "processed",
        "routine_run_id": payload.routine_run_id,
        "new_or_changed": new_count,
        "duplicates": duplicate_count,
        "errors": error_count,
    }
