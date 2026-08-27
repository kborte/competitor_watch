"""FastAPI app — the HTTP surface, and nothing else.

POST /ingest is the write path (secret, validate, hand to ingest.py); the GET
routes are the read API behind the dashboard, guarded only by a CORS allowlist.
Both keep their logic elsewhere, so this file stays a translation from request
params to a call and back to a response.

Run locally:
    WEBHOOK_SECRET=... uvicorn backend.main:app --reload --port 8000
"""

from datetime import datetime, timezone
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from . import config, db, htmlutil, reads
from . import ingest as ingest_logic
from .schemas import Category, IngestPayload, Line

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
db.init_db()

if config.FRONTEND_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.FRONTEND_ORIGINS,
        allow_methods=["GET"],
        allow_headers=["*"],
    )


@app.post("/ingest")
async def ingest(request: Request, authorization: str = Header(...)):
    """Accepts one crawler delivery. 401 on a bad secret, 422 on a malformed
    body (which is stored in rejected_payloads before being rejected)."""
    if authorization != f"Bearer {config.WEBHOOK_SECRET}":
        raise HTTPException(status_code=401, detail="bad secret")

    raw_body = await request.body()
    try:
        payload = IngestPayload.model_validate_json(raw_body)
    except ValidationError as exc:
        with db.connect() as conn:
            db.insert_rejected_payload(
                conn, datetime.now(timezone.utc),
                raw_body.decode("utf-8", errors="replace"), str(exc),
            )
        raise HTTPException(status_code=422, detail=str(exc))

    return ingest_logic.process(payload)


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
