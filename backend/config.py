"""Backend configuration — env vars only, no framework config system needed at this scale.

GEMINI_API_KEY is not read here; the Gemini SDK picks it up from the
environment on its own. Both vars are expected in backend/.env (see
backend/.env.example) — never commit the real file.
"""

import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
DATABASE_URL = os.environ["DATABASE_URL"]
MCP_PUBLIC_HOST = os.environ.get("MCP_PUBLIC_HOST")  # e.g. "some-name.trycloudflare.com" — no scheme, no port

# Comma-separated origins allowed to call the read API, e.g.
# "https://middle-mgmt.qic.qa,https://upper-mgmt.qic.qa" — the read endpoints
# have no auth, so this is just hygiene against arbitrary sites reading the
# data client-side, not a security boundary.
FRONTEND_ORIGINS = [o.strip() for o in os.environ.get("FRONTEND_ORIGINS", "").split(",") if o.strip()]
