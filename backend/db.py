"""Storage — plain psycopg2, no ORM, hand-written SQL.

Five tables form the audit chain, each row pointing back at what produced it:
routine_runs (verbatim payload receipts) -> findings -> llm_calls -> classifications,
with seen_urls alongside as the dedup ledger. A sixth, rejected_payloads, sits
outside the chain and catches deliveries that failed validation. SCHEMA below runs
on every boot and every statement in it is idempotent.
"""

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

-- Renamed from "changes": the table holds the parsed verdict of one
-- classification call (category, materiality, confidence, evidence,
-- rationale), 1:1 with llm_calls. "changes" was inherited from this
-- system's ancestor, a page-change detector, and stopped describing the
-- contents long ago. Guarded so it is a no-op on a fresh database (where
-- the CREATE below does the work) and runs exactly once on an existing
-- one; the CREATE that used to name "changes" is deliberately gone, or it
-- would recreate an empty table beside the renamed one on the next boot.
DO $$
BEGIN
    IF to_regclass('public.changes') IS NOT NULL
       AND to_regclass('public.classifications') IS NULL THEN
        ALTER TABLE changes RENAME TO classifications;
    END IF;
END $$;

-- Token counts per call, so spend is measurable per finding and per run from
-- the database rather than only visible on the Google bill. Nullable: rows
-- written before this existed have no counts, and 0 would be a lie.
ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS input_tokens INTEGER;
ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS output_tokens INTEGER;
ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS total_tokens INTEGER;

CREATE TABLE IF NOT EXISTS classifications (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    llm_call_id BIGINT NOT NULL REFERENCES llm_calls(id),
    category TEXT NOT NULL,
    materiality TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_quote TEXT NOT NULL
);

ALTER TABLE classifications ADD COLUMN IF NOT EXISTS rationale TEXT;
-- Nullable with no default: rows written before this column existed
-- genuinely have no grounding verdict, and NULL says that honestly where
-- a false would assert the model had judged the excerpt unsupported.
ALTER TABLE classifications ADD COLUMN IF NOT EXISTS grounded BOOLEAN;

CREATE TABLE IF NOT EXISTS rejected_payloads (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL,
    raw_body TEXT NOT NULL,
    validation_error TEXT NOT NULL
);

-- Indexes. Postgres indexes primary keys automatically but not foreign keys, so
-- every join in reads/ was a sequential scan. The two audit-chain joins run on
-- every feed and stats query; the rest back the filters and sorts the dashboard
-- actually issues.
CREATE INDEX IF NOT EXISTS idx_llm_calls_finding_id ON llm_calls (finding_id);
CREATE INDEX IF NOT EXISTS idx_classifications_llm_call_id ON classifications (llm_call_id);
CREATE INDEX IF NOT EXISTS idx_findings_run_id ON findings (run_id);
CREATE INDEX IF NOT EXISTS idx_findings_retrieved_at ON findings (retrieved_at DESC);
CREATE INDEX IF NOT EXISTS idx_findings_published_at ON findings (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_findings_company ON findings (company);
-- The feed's default shape: non-duplicate competitor rows, newest first.
CREATE INDEX IF NOT EXISTS idx_findings_feed ON findings (retrieved_at DESC)
    WHERE NOT is_duplicate AND NOT is_reference;
-- Retention sweep: find rows that still carry a snapshot.
CREATE INDEX IF NOT EXISTS idx_findings_snapshot_retention ON findings (retrieved_at)
    WHERE source_html IS NOT NULL;
"""


@contextmanager
def connect():
    """Yields a connection that commits on clean exit and always closes."""
    conn = psycopg2.connect(config.DATABASE_URL)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


@contextmanager
def savepoint(conn, name: str = "finding"):
    """Nested transaction for one finding. If the block raises, only this
    finding's rows are undone — the rest of the payload survives."""
    # A Python-level failure (a bad LLM response) leaves the transaction
    # healthy, so the rollback discards exactly the rows written inside the
    # block. The name is a fixed literal, never caller-supplied.
    with conn.cursor() as cur:
        cur.execute(f"SAVEPOINT {name}")
    try:
        yield
    except Exception:
        with conn.cursor() as cur:
            cur.execute(f"ROLLBACK TO SAVEPOINT {name}")
        raise
    else:
        with conn.cursor() as cur:
            cur.execute(f"RELEASE SAVEPOINT {name}")


# Arbitrary but fixed: any process applying this schema must pick the same
# number for the lock to mean anything.
_SCHEMA_LOCK_KEY = 0x0C0FFEE5


def init_db() -> None:
    """Applies SCHEMA under an advisory lock. Safe to call repeatedly, and safe
    when several pods start at once."""
    # `CREATE TABLE IF NOT EXISTS` is not atomic: two pods checking and creating
    # concurrently — exactly what a RollingUpdate does — can both pass the check
    # and one then fails with a duplicate-object error, crash-looping the new
    # pod. The transaction-scoped lock serialises them: the first applies the
    # schema, the others wait and then find everything already present.
    with connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (_SCHEMA_LOCK_KEY,))
            cur.execute(SCHEMA)


def content_hash(text: str) -> str:
    """Stable hash of a page's text, used by dedup to detect content changes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_exists(conn, run_id: str) -> bool:
    """Whether this delivery was already processed — the idempotency check."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM routine_runs WHERE id = %s", (run_id,))
        return cur.fetchone() is not None


def insert_run(conn, run_id: str, received_at, raw_payload: dict) -> None:
    """Records a delivery and its verbatim payload, before anything interprets it."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO routine_runs (id, received_at, raw_payload) VALUES (%s, %s, %s)",
            (run_id, received_at, Json(raw_payload)),
        )


def get_seen_url(conn, source_url: str, scope: str = "competitor"):
    """Returns (category, last_content_hash) for a URL in the ledger, or None."""
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
    """Records this sighting of a URL, refreshing its last-seen run and hash.
    first_seen_run_id is set once on insert and never overwritten."""
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
    """Drops bulky fields on duplicate rows."""
    return value if not is_duplicate else None


def insert_finding(conn, run_id: str, finding, is_duplicate: bool) -> int:
    """Stores one finding, duplicate or not. Returns the new finding id."""
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
                # The HTML snapshot and link-preview metadata are only worth storing
                # on the sighting that represents a new or changed content state;
                # re-storing identical values on every crawl tick is pure waste.
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


def insert_llm_call(
    conn, finding_id: int, model: str, prompt: str, raw_output: str, called_at,
    usage: dict | None = None,
) -> int:
    """Records the exact prompt, raw output and token usage for one call.
    Returns the new call id."""
    usage = usage or {}
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO llm_calls "
            "(finding_id, model, prompt, raw_output, called_at, "
            " input_tokens, output_tokens, total_tokens) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (finding_id, model, prompt, raw_output, called_at,
             usage.get("input_tokens"), usage.get("output_tokens"), usage.get("total_tokens")),
        )
        return cur.fetchone()[0]


def insert_rejected_payload(conn, received_at, raw_body: str, validation_error: str) -> None:
    """Keeps a delivery that failed schema validation, for debugging."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO rejected_payloads (received_at, raw_body, validation_error) VALUES (%s, %s, %s)",
            (received_at, raw_body, validation_error),
        )


def insert_classification(conn, llm_call_id: int, classification) -> None:
    """Records the parsed verdict — category, materiality, grounding — for one call."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO classifications "
            "(llm_call_id, category, materiality, confidence, evidence_quote, rationale, grounded) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (llm_call_id, classification.category, classification.materiality,
             classification.confidence, classification.evidence_quote,
             classification.rationale, classification.grounded),
        )
