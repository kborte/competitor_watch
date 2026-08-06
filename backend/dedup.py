"""Two-tier deterministic dedup — the only novelty decision in the system.

A never-seen source_url always proceeds to classification. A seen news/
social_sentiment URL is a duplicate by default (those are one-shot; an
article essentially never gets rewritten into something materially
different after publish). A seen product/marketing URL is re-hashed on
every sighting — those are a competitor's own stable pages, and a hash
change there is exactly the signal the original page-crawler was built to
catch.

The hash is computed over the page's clean text (derived from the
captured source_html), not the LLM's chosen excerpt — hashing the excerpt
made "did this page change" depend on which sentence the model happened to
quote, rather than the page itself. When source_html is unavailable (the
LLM's source_url didn't match any independently-fetched source), there's
nothing to hash: treat it as needing classification rather than guessing,
and carry a None hash forward so the next sighting stays in that same
state until a capture actually succeeds."""

from urllib.parse import urlsplit, urlunsplit

from . import db
from .htmlutil import extract_clean_text

STABLE_URL_CATEGORIES = {"product", "marketing"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def _content_hash(finding) -> str | None:
    if not finding.source_html:
        return None
    return db.content_hash(extract_clean_text(finding.source_html))


def check(conn, finding) -> tuple[bool, str | None]:
    """Returns (needs_classification, content_hash)."""
    normalized = normalize_url(finding.source_url)
    hash_value = _content_hash(finding)
    seen = db.get_seen_url(conn, normalized)

    if seen is None:
        return True, hash_value

    _, last_hash = seen
    if finding.category not in STABLE_URL_CATEGORIES:
        return False, hash_value

    if hash_value is None or last_hash is None:
        return True, hash_value

    return last_hash != hash_value, hash_value
