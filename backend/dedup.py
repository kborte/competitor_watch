"""Two-tier novelty check — the only place "is this new?" is decided.

The crawler reports every relevant finding on every run, repeats included, so
this is what stops the backend paying for an LLM call on the same page twice. A
never-seen URL is always new; a seen one depends on whether its category is the
kind of page that gets rewritten in place.
"""

from urllib.parse import urlsplit, urlunsplit

from . import db
from .htmlutil import extract_clean_text

# Categories whose URLs are a competitor's own stable pages rather than one-shot
# publications. These get re-hashed on every sighting, because a content change
# there is precisely the signal this system exists to catch. Everything else —
# news, social posts — is written once and never meaningfully rewritten, so a
# repeat sighting is just a repeat.
STABLE_URL_CATEGORIES = {"product", "marketing"}


def normalize_url(url: str) -> str:
    """Strips query, fragment and trailing slash so trivially different URLs for
    the same page share one ledger entry."""
    parts = urlsplit(url)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def _content_hash(finding) -> str | None:
    """Hashes the captured page's clean text, or None when no HTML was captured."""
    # Hashing the page rather than the LLM's chosen excerpt: hashing the excerpt
    # made "did this page change" depend on which sentence the model happened to
    # quote, rather than on the page itself.
    if not finding.source_html:
        return None
    return db.content_hash(extract_clean_text(finding.source_html))


def check(conn, finding) -> tuple[bool, str | None]:
    """Decides whether a finding earns a classification call.
    Returns (needs_classification, content_hash_to_record)."""
    normalized = normalize_url(finding.source_url)
    hash_value = _content_hash(finding)
    scope = "reference" if finding.is_reference else "competitor"
    seen = db.get_seen_url(conn, normalized, scope)

    if seen is None:
        return True, hash_value

    _, last_hash = seen
    if finding.category not in STABLE_URL_CATEGORIES:
        return False, hash_value

    # No capture to compare, on either side. Treat it as needing classification
    # rather than guessing, and carry the None forward so the next sighting stays
    # in this state until a capture actually succeeds.
    if hash_value is None or last_hash is None:
        return True, hash_value

    return last_hash != hash_value, hash_value
