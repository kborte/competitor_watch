"""Backend configuration — env vars only, no framework config system at this scale.

Required vars are expected in backend/.env (see backend/.env.example); never
commit the real file. GEMINI_API_KEY is not read here — the Gemini SDK picks it
up from the environment on its own.
"""

import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
DATABASE_URL = os.environ["DATABASE_URL"]

# No CORS configuration: the dashboard and the API are served from one origin
# behind a shared Ingress (dashboard at /, API at /api), so browser requests are
# same-origin and never preflight. Access control lives at the Ingress — /ingest
# is not exposed there at all, and the crawler reaches it over internal cluster
# DNS. See docs/code-review-response.md for that decision.

# Bound on the classification call. Must stay below the crawler's HTTP timeout,
# which must in turn stay below the server's own request timeout, so a slow call
# always surfaces as a real error to whoever is waiting rather than as a guess.
CLASSIFY_TIMEOUT_MS = int(os.environ.get("CLASSIFY_TIMEOUT_MS", "45000"))
CLASSIFY_MAX_OUTPUT_TOKENS = int(os.environ.get("CLASSIFY_MAX_OUTPUT_TOKENS", "1024"))
# 0 disables extended thinking. The verdict is a short structured judgment over
# an excerpt already in the prompt; it does not need a reasoning budget.
CLASSIFY_THINKING_BUDGET = int(os.environ.get("CLASSIFY_THINKING_BUDGET", "0"))

# Retry only the transient statuses, and only a few times — the crawler
# re-reports everything tomorrow, so exhausting retries is not data loss.
LLM_MAX_ATTEMPTS = int(os.environ.get("LLM_MAX_ATTEMPTS", "3"))
LLM_BACKOFF_SECONDS = float(os.environ.get("LLM_BACKOFF_SECONDS", "2"))
