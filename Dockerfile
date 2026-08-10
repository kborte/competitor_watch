FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/

# Cloud Run injects $PORT (8080 by default). Single worker: the app opens a
# fresh psycopg2 connection per request, so there's no pool to size.
CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}
