"""Entry point — run on a cron schedule: python3 -m research_crawler.crawler

For each keyword: grounded search (discover.py), independent page-fetch
verification, then structuring into clean findings (structure.py). Findings are
delivered to the backend one at a time as they are produced, so a crash partway
through only loses work not yet done. No novelty judgment happens here — every
relevant finding is reported every run, and the backend's ledger decides what's new.
"""

import queue
import threading
import traceback
import uuid
from datetime import datetime, timezone

import requests

from . import config
from .discover import discover
from .schemas import IngestPayload
from .structure import structure

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


def deliver(payload: IngestPayload) -> bool:
    """POSTs one payload to the backend. Returns True on success and never
    raises — a failed delivery must not crash the rest of the crawl."""
    try:
        resp = requests.post(
            config.BACKEND_INGEST_URL,
            headers={"Authorization": f"Bearer {config.WEBHOOK_SECRET}"},
            data=payload.model_dump_json(),
            timeout=30,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        print(f"  DELIVERY FAILED ({payload.routine_run_id}): {exc}", flush=True)
        return False


def _envelope(crawl_id: str, seq: int, keyword: str, findings: list, no_findings: bool, note_suffix: str = "") -> IngestPayload:
    """Wraps findings in one delivery. Each gets a unique routine_run_id for the
    backend's idempotency check; crawl_id ties the run back together."""
    now = datetime.now(timezone.utc)
    return IngestPayload(
        routine_run_id=f"{crawl_id}-{seq}",
        run_started_at=now,
        run_completed_at=now,
        keywords=[keyword],
        findings=findings,
        keywords_with_no_findings=[keyword] if no_findings else [],
        notes=f"crawl_id={crawl_id}{note_suffix}",
    )


def run() -> None:
    """Crawls every configured keyword in turn, delivering as it goes."""
    crawl_id = str(uuid.uuid4())
    total = len(config.KEYWORDS)
    seq = 0
    delivered = failed = 0

    print(f"crawl {crawl_id} starting — {total} keywords, "
          f"{PER_COMPANY_TIMEOUT_SECONDS}s budget per company, "
          f"search window: last {config.SEARCH_WINDOW_DAYS}d", flush=True)

    for i, keyword in enumerate(config.KEYWORDS, 1):
        print(f"\n[{i}/{total}] {keyword}", flush=True)
        status, payload = _run_company(keyword, config.SEARCH_WINDOW_DAYS)

        if status == "timeout":
            print(f"  [{keyword}] TIMEOUT — exceeded {PER_COMPANY_TIMEOUT_SECONDS}s budget, abandoning", flush=True)
            seq += 1
            ok = deliver(_envelope(crawl_id, seq, keyword, [], no_findings=True, note_suffix=";timeout"))
            delivered += ok
            failed += not ok
            continue

        if status == "error":
            exc = payload
            print(f"  [{keyword}] ERROR — {exc!r}", flush=True)
            traceback.print_exc()
            seq += 1
            ok = deliver(_envelope(crawl_id, seq, keyword, [], no_findings=True))
            delivered += ok
            failed += not ok
            continue

        summary, sources, batch = payload

        if not batch.findings:
            seq += 1
            ok = deliver(_envelope(crawl_id, seq, keyword, [], no_findings=True))
            delivered += ok
            failed += not ok
            print(f"  [{keyword}] no findings — recorded", flush=True)
            continue

        for finding in batch.findings:
            seq += 1
            ok = deliver(_envelope(crawl_id, seq, keyword, [finding], no_findings=False))
            delivered += ok
            failed += not ok
            print(f"  [{keyword}] -> {'delivered' if ok else 'FAILED'}: "
                  f"[{finding.category}] {finding.title}", flush=True)

        print(f"  [{keyword}] done — {len(batch.findings)} finding(s) "
              f"({i}/{total} keywords complete)", flush=True)

    print(f"\ncrawl {crawl_id} complete — {delivered} delivered, {failed} failed", flush=True)


if __name__ == "__main__":
    run()
