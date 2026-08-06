"""Crawler configuration — env vars only. Deployed independently from the
backend, so this reads its own .env, not the backend's."""

import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# GEMINI_API_KEY is not read here; the Gemini SDK picks it up from the
# environment on its own.
BACKEND_INGEST_URL = os.environ["BACKEND_INGEST_URL"]  # e.g. http://localhost:8123/ingest
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]

KEYWORDS = [
    "Bupa Arabia",
    "Tawuniya",
    "ADNIC",
    "Sukoon",
    "Alkhaleej Takaful",
    "Beema",
    "Doha Insurance",
    "Qatar Islamic Insurance",
    "QLM",
    "Qatar general insurance market",
]

MODEL = "gemini-3.6-flash"
