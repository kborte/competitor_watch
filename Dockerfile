FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/

# $PORT is injected by the platform (8080 by default).
#
# One uvicorn worker per container, by choice rather than by necessity: the app
# opens a fresh psycopg2 connection per request and holds no in-process state,
# so it is safe to run at any worker count — scale by adding replicas, which is
# what the cluster is for. Raising --workers here would multiply this pod's
# database connections with no coordination between them.
CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080}
