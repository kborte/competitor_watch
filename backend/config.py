"""Backend configuration — env vars only, no framework config system at this scale.

Reads the repo-root .env (see .env.example) for local development. In a container
that file is absent and the platform supplies the environment directly, which
works unchanged: load_dotenv() no-ops on a missing file and never overrides a
variable that is already set.
"""

import os
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

# GEMINI_API_KEY is not read here; the Gemini SDK picks it up from the
# environment on its own.

# No CORS configuration: the dashboard and the API are served from one origin
# behind a shared Ingress (dashboard at /, API at /api), so browser requests are
# same-origin and never preflight. Access control lives at the Ingress — /ingest
# is not exposed there at all, and the crawler reaches it over internal cluster
# DNS.


def _database_url() -> str:
    """DATABASE_URL verbatim when set, otherwise assembled from POSTGRES_*."""
    # Assembled here rather than in the .env because `kubectl --from-env-file`
    # and `docker compose env_file:` copy values literally: a ${VAR} reference
    # in the file would arrive as those characters. Doing it in Python behaves
    # the same under every one of them.
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return explicit

    password = os.environ.get("POSTGRES_PASSWORD")
    if not password:
        raise RuntimeError(
            "Set DATABASE_URL, or POSTGRES_PASSWORD to have it built from the "
            "POSTGRES_* parts. See .env.example."
        )
    # Quoted: a password containing @ : / or ? would otherwise be parsed as
    # structure rather than as a value.
    user = quote(os.environ.get("POSTGRES_USER", "cw"), safe="")
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    name = os.environ.get("POSTGRES_DB", "competitor_watch")
    sslmode = os.environ.get("POSTGRES_SSLMODE", "disable")
    return (
        f"postgresql://{user}:{quote(password, safe='')}@{host}:{port}/{name}"
        f"?sslmode={sslmode}"
    )


DATABASE_URL = _database_url()

# Uppercased because logging rejects a lowercase level name outright
# (ValueError: Unknown level: 'debug'), which would be a crash on boot.
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

# Retry only the transient statuses, and only a few times — the crawler
# re-reports everything tomorrow, so exhausting retries is not data loss.
GEMINI_MAX_ATTEMPTS = int(os.environ.get("GEMINI_MAX_ATTEMPTS", "3"))
GEMINI_BACKOFF_SECONDS = float(os.environ.get("GEMINI_BACKOFF_SECONDS", "2"))

# Bound on the classification call. Must stay below the crawler's HTTP timeout,
# which must in turn stay below the server's own request timeout, so a slow call
# always surfaces as a real error to whoever is waiting rather than as a guess.
CLASSIFY_TIMEOUT_MS = int(os.environ.get("CLASSIFY_TIMEOUT_MS", "45000"))
CLASSIFY_MAX_OUTPUT_TOKENS = int(os.environ.get("CLASSIFY_MAX_OUTPUT_TOKENS", "1024"))
# 0 disables extended thinking. The verdict is a short structured judgment over
# an excerpt already in the prompt; it does not need a reasoning budget.
CLASSIFY_THINKING_BUDGET = int(os.environ.get("CLASSIFY_THINKING_BUDGET", "0"))

SNAPSHOT_RETENTION_DAYS = int(os.environ.get("SNAPSHOT_RETENTION_DAYS", "90"))
