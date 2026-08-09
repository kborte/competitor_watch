"""Storage — plain psycopg2, no ORM. Five tables mirror the architecture
doc's audit chain: routine_runs (raw payload receipts, immutable), findings,
seen_urls (the dedup ledger — the only novelty decision in the system),
llm_calls, and changes."""

import hashlib
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import Json

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS routine_runs (
    id TEXT PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL,
    raw_payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES routine_runs(id),
    keyword TEXT NOT NULL,
    company TEXT NOT NULL,
    category TEXT NOT NULL,
    platform TEXT,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    source_excerpt TEXT NOT NULL,
    published_at DATE,
    retrieved_at TIMESTAMPTZ NOT NULL,
    is_duplicate BOOLEAN NOT NULL
);

ALTER TABLE findings ADD COLUMN IF NOT EXISTS source_html TEXT;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS og_title TEXT;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS og_image_url TEXT;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS og_description TEXT;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS og_site_name TEXT;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS verified BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS line TEXT;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS tone TEXT;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS source_location TEXT;
ALTER TABLE findings ADD COLUMN IF NOT EXISTS is_reference BOOLEAN NOT NULL DEFAULT false;

CREATE TABLE IF NOT EXISTS seen_urls (
    source_url TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT 'competitor',
    category TEXT NOT NULL,
    first_seen_run_id TEXT NOT NULL,
    last_seen_run_id TEXT NOT NULL,
    last_content_hash TEXT,
    PRIMARY KEY (source_url, scope)
);

ALTER TABLE seen_urls ADD COLUMN IF NOT EXISTS scope TEXT NOT NULL DEFAULT 'competitor';
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'seen_urls'::regclass AND contype = 'p'
          AND array_length(conkey, 1) = 1
    ) THEN
        ALTER TABLE seen_urls DROP CONSTRAINT seen_urls_pkey;
        ALTER TABLE seen_urls ADD PRIMARY KEY (source_url, scope);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS llm_calls (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    finding_id BIGINT NOT NULL REFERENCES findings(id),
    model TEXT NOT NULL,
    prompt TEXT NOT NULL,
    raw_output TEXT NOT NULL,
    called_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS changes (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    llm_call_id BIGINT NOT NULL REFERENCES llm_calls(id),
    category TEXT NOT NULL,
    materiality TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_quote TEXT NOT NULL
);

ALTER TABLE changes ADD COLUMN IF NOT EXISTS rationale TEXT;

CREATE TABLE IF NOT EXISTS rejected_payloads (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL,
    raw_body TEXT NOT NULL,
    validation_error TEXT NOT NULL
);
"""


@contextmanager
def connect():
    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_exists(conn, run_id: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM routine_runs WHERE id = %s", (run_id,))
        return cur.fetchone() is not None


def insert_run(conn, run_id: str, received_at, raw_payload: dict) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO routine_runs (id, received_at, raw_payload) VALUES (%s, %s, %s)",
            (run_id, received_at, Json(raw_payload)),
        )


def get_seen_url(conn, source_url: str, scope: str = "competitor"):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT category, last_content_hash FROM seen_urls WHERE source_url = %s AND scope = %s",
            (source_url, scope),
        )
        return cur.fetchone()


def upsert_seen_url(
    conn, source_url: str, category: str, run_id: str, content_hash_value: str,
    scope: str = "competitor",
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO seen_urls (source_url, scope, category, first_seen_run_id, last_seen_run_id, last_content_hash)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_url, scope) DO UPDATE SET
                last_seen_run_id = excluded.last_seen_run_id,
                last_content_hash = excluded.last_content_hash
            """,
            (source_url, scope, category, run_id, run_id, content_hash_value),
        )


def _only_if_new(value, is_duplicate: bool):
    """Several fields (the HTML snapshot, link-preview metadata) only earn
    storage on the finding that actually represents a new/changed content
    state — re-storing identical values on every unchanged crawl tick would
    be pure waste."""
    return value if not is_duplicate else None


def insert_finding(conn, run_id: str, finding, is_duplicate: bool) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO findings (run_id, keyword, company, category, platform, source_url, title,
                                   summary, source_excerpt, published_at, retrieved_at, is_duplicate,
                                   source_html, og_title, og_image_url, og_description, og_site_name,
                                   verified, line, tone, source_location, is_reference)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s)
            RETURNING id
            """,
            (
                run_id, finding.keyword, finding.company, finding.category, finding.platform,
                finding.source_url, finding.title, finding.summary, finding.source_excerpt,
                finding.published_at, finding.retrieved_at, is_duplicate,
                _only_if_new(finding.source_html, is_duplicate),
                _only_if_new(finding.og_title, is_duplicate),
                _only_if_new(finding.og_image_url, is_duplicate),
                _only_if_new(finding.og_description, is_duplicate),
                _only_if_new(finding.og_site_name, is_duplicate),
                finding.verified,
                finding.line, finding.tone, finding.source_location, finding.is_reference,
            ),
        )
        return cur.fetchone()[0]


def insert_llm_call(conn, finding_id: int, model: str, prompt: str, raw_output: str, called_at) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO llm_calls (finding_id, model, prompt, raw_output, called_at) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (finding_id, model, prompt, raw_output, called_at),
        )
        return cur.fetchone()[0]


def insert_rejected_payload(conn, received_at, raw_body: str, validation_error: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO rejected_payloads (received_at, raw_body, validation_error) VALUES (%s, %s, %s)",
            (received_at, raw_body, validation_error),
        )


def insert_change(conn, llm_call_id: int, classification) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO changes (llm_call_id, category, materiality, confidence, evidence_quote, rationale) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (llm_call_id, classification.category, classification.materiality,
             classification.confidence, classification.evidence_quote, classification.rationale),
        )
