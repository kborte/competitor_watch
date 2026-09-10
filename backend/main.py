"""FastAPI app — the HTTP surface, and nothing else.

POST /ingest is the write path (secret, validate, hand to ingest.py); the GET
routes are the read API behind the dashboard. Both keep their logic elsewhere,
so this file stays a translation from request params to a call and back to a
response.

Run locally:
    WEBHOOK_SECRET=... uvicorn backend.main:app --reload --port 8000
"""

import hmac
import logging
import os
from datetime import UTC, datetime
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError

from . import config, db, htmlutil, reads
from . import ingest as ingest_logic
from .schemas import Category, IngestPayload, Line

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger(__name__)

# Query-param vocabularies. Declared as types rather than checked by hand:
# FastAPI rejects anything outside them with a 422 before the route body
# runs, so there is no validation code to keep in step with the values.
# Category and Line come straight from schemas.py — the same literals the
# ingest contract uses, so the read API can't drift from what's stored.
Window = Literal["today", "week", "month", "year", "all"]
View = Literal["full", "summary"]
SortBy = Literal["materiality", "published_at", "retrieved_at"]
SortDir = Literal["asc", "desc"]
Materiality = Literal["low", "medium", "high"]

app = FastAPI()

# No CORS middleware: the dashboard and the API share one origin behind the
# Ingress (dashboard at /, API at /api), so browser requests are same-origin and
# never preflight. Access control is the Ingress's job — /ingest is not exposed
# there, and the crawler reaches it over internal cluster DNS.

# Applied under an advisory lock, so several pods starting at once during a
# RollingUpdate cannot race each other (see db.init_db).
db.init_db()


@app.get("/healthz")
def healthz():
    """Liveness: proves the process is up and serving. Deliberately touches no
    dependency, so a database blip cannot cause a restart loop."""
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    """Readiness: proves the database is reachable, so a pod that cannot serve
    real traffic is taken out of rotation rather than restarted."""
    try:
        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception as exc:
        log.exception("readiness check failed")
        raise HTTPException(status_code=503, detail="database unreachable") from exc
    return {"status": "ready"}


@app.post("/ingest")
async def ingest(request: Request, authorization: str = Header(...)):
    """Accepts one crawler delivery. 401 on a bad secret, 422 on a malformed
    body (which is stored in rejected_payloads before being rejected)."""
    # Constant-time comparison: `!=` on secrets short-circuits at the first
    # differing byte, so response timing leaks how much of a guess was correct.
    if not hmac.compare_digest(authorization, f"Bearer {config.WEBHOOK_SECRET}"):
        raise HTTPException(status_code=401, detail="bad secret")

    raw_body = await request.body()
    try:
        payload = IngestPayload.model_validate_json(raw_body)
    except ValidationError as exc:
        # Read as raw bytes and validated here rather than via a typed body
        # parameter, so a malformed delivery can be stored before it is
        # rejected. FastAPI would 422 it before the handler ran.
        # `detail` is bound now because Python unbinds `exc` when this block
        # ends, and the closure below outlives the name.
        detail = str(exc)
        body_text = raw_body.decode("utf-8", errors="replace")

        def store_rejected() -> None:
            with db.connect() as conn:
                db.insert_rejected_payload(
                    conn, datetime.now(UTC), body_text, detail,
                )
        await run_in_threadpool(store_rejected)
        raise HTTPException(status_code=422, detail=detail) from exc

    # process() is fully synchronous — blocking database calls and a multi-second
    # LLM call. Awaiting it directly on the event loop would stall every other
    # request in this worker for its whole duration, including the health probes.
    return await run_in_threadpool(ingest_logic.process, payload)


@app.get("/findings")
def list_findings(
    company: str | None = None, category: Category | None = None, line: Line | None = None,
    materiality: Materiality | None = None, window: Window = "all",
    sort_by: SortBy = "materiality", sort_dir: SortDir = "desc", include_duplicates: bool = False,
    limit: int = reads.DEFAULT_LIMIT, offset: int = 0,
):
    """The competitor feed. Every enum param is validated by its type before
    this runs; `company` is not, so an unknown value simply matches nothing."""
    with db.connect() as conn:
        return reads.list_findings(
            conn, company=company, category=category, line=line, materiality=materiality,
            window=window, sort_by=sort_by, sort_dir=sort_dir, include_duplicates=include_duplicates,
            limit=limit, offset=offset,
        )


@app.get("/stats")
def get_stats(
    company: str | None = None, category: Category | None = None,
    line: Line | None = None, window: Window = "week",
):
    """Dashboard KPIs for a window, with a delta against the preceding one."""
    with db.connect() as conn:
        return reads.get_stats(conn, company=company, category=category, line=line, window=window)


@app.get("/findings/{finding_id}")
def get_finding(finding_id: int, view: View = "full"):
    """One finding with its audit trail. 404 if the id does not exist."""
    with db.connect() as conn:
        result = reads.get_finding(conn, finding_id, view=view)
    if result is None:
        raise HTTPException(status_code=404, detail="finding not found")
    return result


@app.get("/findings/{finding_id}/snapshot")
def get_snapshot(finding_id: int):
    """The archived source page as it looked when observed."""
    with db.connect() as conn:
        snapshot = reads.get_snapshot(conn, finding_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="finding not found")
    if snapshot["html"] is None:
        raise HTTPException(status_code=404, detail="no snapshot captured for this finding")

    html = htmlutil.inject_base_href(snapshot["html"], snapshot["source_url"])
    # CSP sandbox (no tokens) blocks any script in the captured page from
    # executing, enforced by the browser regardless of how the frontend
    # embeds this response — not reliant on the consumer remembering a
    # sandbox attribute on its <iframe>.
    return Response(content=html, media_type="text/html", headers={"Content-Security-Policy": "sandbox"})


@app.get("/companies")
def list_companies():
    """Tracked competitors with per-window finding counts, for the filter chips."""
    with db.connect() as conn:
        return reads.list_companies(conn)


@app.get("/crawl-status")
def get_crawl_status():
    """When the crawler last delivered anything, for the staleness indicator."""
    with db.connect() as conn:
        return {"latest_crawl_at": reads.get_latest_crawl_at(conn)}
