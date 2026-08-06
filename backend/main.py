"""FastAPI app.

POST /ingest validates the shared secret, validates the payload against
the JSON contract (via the IngestPayload model), stores it verbatim, then
runs two-tier dedup before spending an LLM call on anything. Idempotent on
routine_run_id, so a retried delivery is a no-op rather than a duplicate.

The GET routes below it are the read API backing the frontend — additive,
no auth (see FRONTEND_ORIGINS in config.py for the CORS-only guard), and
they don't touch the write path at all.

Run locally:
    WEBHOOK_SECRET=... uvicorn backend.main:app --reload --port 8000
"""

from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError

from . import config, db, reads
from . import ingest as ingest_logic
from .schemas import IngestPayload

VALID_WINDOWS = {"today", "week", "month", "all"}
VALID_VIEWS = {"full", "summary"}

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
    company: str | None = None, category: str | None = None, window: str = "all",
    prioritized: bool | None = None, include_duplicates: bool = False,
    limit: int = reads.DEFAULT_LIMIT, offset: int = 0,
):
    if window not in VALID_WINDOWS:
        raise HTTPException(status_code=422, detail=f"window must be one of {sorted(VALID_WINDOWS)}")
    with db.connect() as conn:
        return reads.list_findings(
            conn, company=company, category=category, window=window, prioritized=prioritized,
            include_duplicates=include_duplicates, limit=limit, offset=offset,
        )


@app.get("/findings/{finding_id}")
def get_finding(finding_id: int, view: str = "full"):
    if view not in VALID_VIEWS:
        raise HTTPException(status_code=422, detail=f"view must be one of {sorted(VALID_VIEWS)}")
    with db.connect() as conn:
        result = reads.get_finding(conn, finding_id, view=view)
    if result is None:
        raise HTTPException(status_code=404, detail="finding not found")
    return result


@app.get("/findings/{finding_id}/snapshot")
def get_snapshot(finding_id: int):
    with db.connect() as conn:
        snapshot = reads.get_snapshot(conn, finding_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="finding not found")
    if snapshot["html"] is None:
        raise HTTPException(status_code=404, detail="no snapshot captured for this finding")

    html = reads.inject_base_href(snapshot["html"], snapshot["source_url"])
    # CSP sandbox (no tokens) blocks any script in the captured page from
    # executing, enforced by the browser regardless of how the frontend
    # embeds this response — not reliant on the consumer remembering a
    # sandbox attribute on its <iframe>.
    return Response(content=html, media_type="text/html", headers={"Content-Security-Policy": "sandbox"})


@app.get("/companies")
def list_companies():
    with db.connect() as conn:
        return reads.list_companies(conn)
