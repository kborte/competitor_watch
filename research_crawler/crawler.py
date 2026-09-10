"""Entry point — run on a cron schedule: python3 -m research_crawler.crawler

For each keyword: grounded search (discover.py), independent page-fetch
verification, then structuring into clean findings (structure.py). Findings are
delivered to the backend one at a time as they are produced, so a crash partway
through only loses work not yet done. No novelty judgment happens here — every
relevant finding is reported every run, and the backend's ledger decides what's new.
"""

import logging
import queue
import sys
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import requests

from . import config
from .discover import discover
from .schemas import IngestPayload
from .structure import structure

logging.basicConfig(
    level=config.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

# Each company gets its own budget for discover + structure combined. One
# stuck company must never eat the whole run.
PER_COMPANY_TIMEOUT_SECONDS = 5 * 60


def _run_company(keyword: str, time_range_days: int | None):
    """Runs discover+structure for one keyword under a time budget. Returns
    ("ok", (summary, sources, batch)), ("error", exc) or ("timeout", None)."""
    # Daemon thread so a hung network call can never keep the process alive: on
    # timeout we stop waiting and move on, abandoning the thread rather than
    # joining it. Note this bounds wall-clock, not the work already in flight.
    result: queue.Queue = queue.Queue(maxsize=1)

    def worker():
        """Does the work and hands back a result or the exception that stopped it."""
        try:
            summary, sources = discover(keyword, time_range_days=time_range_days)
            batch = structure(keyword, summary, sources)
            result.put(("ok", (summary, sources, batch)))
        except Exception as exc:
            result.put(("error", exc))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(PER_COMPANY_TIMEOUT_SECONDS)
    if thread.is_alive():
        return "timeout", None
    return result.get()


class FatalDeliveryError(Exception):
    """A delivery failure that every later delivery will hit too."""


@dataclass
class Delivery:
    """Outcome of one delivery. `stored` and `classified` are separate facts:
    the backend can accept a payload and still fail to judge it."""
    stored: bool
    classify_errors: int = 0

    def __bool__(self) -> bool:
        return self.stored


def deliver(payload: IngestPayload) -> Delivery:
    """POSTs one payload to the backend and reads what it says happened.
    Raises FatalDeliveryError only for failures that will not fix themselves."""
    try:
        resp = requests.post(
            config.BACKEND_INGEST_URL,
            headers={"Authorization": f"Bearer {config.WEBHOOK_SECRET}"},
            data=payload.model_dump_json(),
            timeout=config.BACKEND_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        log.error("delivery failed (%s): %r", payload.routine_run_id, exc)
        return Delivery(stored=False)

    # 401 means the shared secret does not match; 403 that we are not allowed
    # in. Neither improves by trying the next 200 findings, and the old code
    # treated them exactly like a transient 503 — so a secret mismatch produced
    # a full run of quiet failures. Fail fast and loudly instead.
    if resp.status_code in (401, 403):
        raise FatalDeliveryError(
            f"backend rejected our credentials ({resp.status_code}) — "
            f"WEBHOOK_SECRET does not match the backend's. Aborting the crawl."
        )

    if not resp.ok:
        log.error("delivery failed (%s): HTTP %s %s",
                  payload.routine_run_id, resp.status_code, resp.text[:300])
        return Delivery(stored=False)

    # HTTP 200 means "received and processed", not "everything succeeded". The
    # body carries a per-payload error count, and discarding it is what made a
    # stranded finding invisible in the run summary.
    try:
        body = resp.json()
    except ValueError:
        log.warning("delivery %s returned unreadable body: %s",
                    payload.routine_run_id, resp.text[:200])
        return Delivery(stored=True)

    errors = int(body.get("errors") or 0)
    if errors:
        log.warning("delivery %s stored but %d finding(s) could not be classified: %s",
                    payload.routine_run_id, errors, body)
    return Delivery(stored=True, classify_errors=errors)


def _envelope(crawl_id: str, seq: int, keyword: str, findings: list, no_findings: bool, note_suffix: str = "") -> IngestPayload:
    """Wraps findings in one delivery. Each gets a unique routine_run_id for the
    backend's idempotency check; crawl_id ties the run back together."""
    now = datetime.now(UTC)
    return IngestPayload(
        routine_run_id=f"{crawl_id}-{seq}",
        run_started_at=now,
        run_completed_at=now,
        keywords=[keyword],
        findings=findings,
        keywords_with_no_findings=[keyword] if no_findings else [],
        notes=f"crawl_id={crawl_id}{note_suffix}",
    )


def run() -> int:
    """Crawls every configured keyword in turn, delivering as it goes.
    Returns a process exit code: non-zero when the run needs attention."""
    if not config.CRAWL_ENABLED:
        # Kill switch, checked before any paid call: lets someone stop the crawl
        # without editing the workflow or revoking a key.
        log.warning("CRAWL_ENABLED is false — exiting without making any calls")
        return 0

    crawl_id = str(uuid.uuid4())
    total = len(config.KEYWORDS)
    seq = 0
    delivered = failed = classify_errors = 0
    findings_delivered = 0
    capped = False

    log.info("crawl %s starting — %d keywords, %ds budget per company, "
             "search window: last %dd, run cap %d findings",
             crawl_id, total, PER_COMPANY_TIMEOUT_SECONDS, config.SEARCH_WINDOW_DAYS,
             config.MAX_FINDINGS_PER_CRAWL)

    def record(result: Delivery) -> None:
        nonlocal delivered, failed, classify_errors
        delivered += result.stored
        failed += not result.stored
        classify_errors += result.classify_errors

    try:
        for i, keyword in enumerate(config.KEYWORDS, 1):
            log.info("[%d/%d] %s", i, total, keyword)
            status, payload = _run_company(keyword, config.SEARCH_WINDOW_DAYS)

            if status == "timeout":
                log.error("[%s] TIMEOUT — exceeded %ds budget, abandoning",
                          keyword, PER_COMPANY_TIMEOUT_SECONDS)
                seq += 1
                record(deliver(_envelope(crawl_id, seq, keyword, [], no_findings=True,
                                         note_suffix=";timeout")))
                continue

            if status == "error":
                log.error("[%s] ERROR", keyword, exc_info=payload)
                seq += 1
                record(deliver(_envelope(crawl_id, seq, keyword, [], no_findings=True)))
                continue

            _summary, _sources, batch = payload

            if not batch.findings:
                seq += 1
                record(deliver(_envelope(crawl_id, seq, keyword, [], no_findings=True)))
                log.info("[%s] no findings — recorded", keyword)
                continue

            for finding in batch.findings:
                # Run-wide ceiling. Without it, a bad search day multiplies into
                # an unbounded number of paid classification calls downstream.
                if findings_delivered >= config.MAX_FINDINGS_PER_CRAWL:
                    capped = True
                    log.error("run cap of %d findings reached — abandoning the rest of "
                              "the crawl (%d keywords unprocessed)",
                              config.MAX_FINDINGS_PER_CRAWL, total - i + 1)
                    break
                seq += 1
                result = deliver(_envelope(crawl_id, seq, keyword, [finding], no_findings=False))
                record(result)
                findings_delivered += result.stored
                log.info("[%s] -> %s: [%s] %s", keyword,
                         "delivered" if result.stored else "FAILED",
                         finding.category, finding.title)

            if capped:
                break
            log.info("[%s] done — %d finding(s) (%d/%d keywords complete)",
                     keyword, len(batch.findings), i, total)
    except FatalDeliveryError as exc:
        log.error("%s", exc)
        log.error("crawl %s aborted — %d delivered, %d failed", crawl_id, delivered, failed)
        return 2

    log.info("crawl %s complete — %d delivered, %d failed, %d classified with errors%s",
             crawl_id, delivered, failed, classify_errors,
             " (RUN CAP HIT)" if capped else "")

    # A non-zero exit makes a bad run visible in the Actions UI instead of
    # leaving a green tick over a run where nothing landed.
    if failed or classify_errors or capped:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run())
