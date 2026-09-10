"""Shared fixtures.

Both packages read configuration at import time and construct a Gemini client,
so the environment must be populated before anything under test is imported.
No test here makes a network call or touches a database.
"""

import os

os.environ.setdefault("WEBHOOK_SECRET", "test-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://unused/unused")
os.environ.setdefault("GEMINI_API_KEY", "test-key")
os.environ.setdefault("BACKEND_INGEST_URL", "http://unused.invalid/ingest")
