# Competitor Watch

Automated competitor intelligence for QIC. Once a day it searches for news about eight
tracked insurers plus the Qatar market at large, verifies every source it finds, judges how
much each item matters, and serves the result to a dashboard.

Nothing here is a chatbot or an agent. It is a cron job, one LLM call per finding, and a
Postgres table with an audit trail.

## How it works

```
GitHub Actions (daily 05:00 UTC)
  └─ research_crawler/          Gemini grounded search per keyword
       ├─ discover.py           search, then independently fetch each cited page
       └─ structure.py          turn summary + page text into clean findings
            │
            │  POST /ingest  (one request per finding, bearer secret)
            ▼
Cloud Run: backend/             FastAPI
       ├─ dedup.py              seen-URL ledger — the only novelty decision
       ├─ classify.py           one Gemini call: materiality, confidence, grounding
       └─ db.py                 six tables, full audit chain
            │
            ▼
       Supabase Postgres
            │
            │  GET /findings, /stats, /companies, ...
            ▼
Vercel: frontend/               Next.js dashboard
```

Three things worth knowing about the design:

- **The crawler makes no novelty judgment.** Every relevant finding is reported on every
  run, even repeats. Whether something is new is decided once, in `backend/dedup.py`,
  against a seen-URL ledger. One place to reason about, one place to fix.
- **Delivery is per-finding, not per-batch.** A crash or timeout partway through a crawl
  loses only work not yet done. Each delivery carries its own `routine_run_id` and the
  backend is idempotent on it, so retries are no-ops.
- **Every judgment is auditable.** The raw payload, the exact prompt, the raw model output,
  and the captured page HTML are all stored. You can always answer "why did it say that."

## Live

| Piece | Where | Notes |
|---|---|---|
| Backend | https://competitor-watch-backend-407920901425.me-central1.run.app | Cloud Run, project `qic-ai-interns`, region `me-central1` |
| Database | Supabase Postgres | connected via the transaction pooler |
| Frontend | https://competitor-watch-qic.vercel.app | Vercel |
| Crawler | GitHub Actions | `.github/workflows/crawl.yml`, daily 05:00 UTC |

## Repo layout

| Path | What |
|---|---|
| `backend/` | FastAPI app. Ingest (write) + read API. Deployed to Cloud Run. |
| `research_crawler/` | The daily crawler. Runs on GitHub Actions, not deployed. |
| `frontend/` | Next.js dashboard. Deployed to Vercel. |
| `docs/backend-api.md` | Full API reference — every route, parameter, and response shape. |
| `DEPLOY.md` | How to ship a backend change. |
| `frontend/README.md` | Frontend setup and structure. |

## Docs

- **[docs/backend-api.md](docs/backend-api.md)** — every endpoint with parameters and example
  responses. This is the one to share with anyone building against the API.
- **[DEPLOY.md](DEPLOY.md)** — build and deploy the backend, roll back, and the permission
  traps specific to the shared `qic-ai-interns` project.
- **[frontend/README.md](frontend/README.md)** — local dev and component layout.

## Running locally

Backend:

```bash
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env      # fill in DATABASE_URL, WEBHOOK_SECRET, GEMINI_API_KEY
uvicorn backend.main:app --reload --port 8000
```

The schema creates itself on startup — `db.init_db()` runs the idempotent DDL in
`backend/db.py` every time the app boots. Point `DATABASE_URL` at the production Supabase
database and you are reading live data; point it at a local Postgres for a clean slate.

Crawler:

```bash
pip install -r research_crawler/requirements.txt
cp research_crawler/.env.example research_crawler/.env   # BACKEND_INGEST_URL, WEBHOOK_SECRET, GEMINI_API_KEY
python -m research_crawler.crawler
```

It runs all 10 keywords sequentially with a 5-minute budget each, so expect 5–50 minutes.
`SEARCH_WINDOW_DAYS=3` by default; set it higher to backfill.

Frontend: see [frontend/README.md](frontend/README.md).

## What it tracks

Eight competitors — Bupa Arabia, Tawuniya, ADNIC, Sukoon Insurance, Alkhaleej Takaful, Beema,
Doha Insurance, QIIC — plus a market-wide keyword and QIC itself as a benchmark
reference. QIC findings are stored but excluded from the competitor feed.

Adding or removing a competitor means editing two files, and they must agree exactly:
`research_crawler/config.py` (`KEYWORDS`) and `backend/companies.py` (`REGISTRY`). Anything
the crawler finds that isn't a registered competitor falls into the "Qatar Insurance Market"
bucket rather than getting its own entity.

## Operational notes

- **A green GitHub Actions run does not mean data landed.** `deliver()` catches delivery
  failures and the process still exits 0. Check the final log line:
  `crawl <id> complete — N delivered, N failed`.
- **`WEBHOOK_SECRET` lives in two places** — Secret Manager and the GitHub repo secrets. A
  mismatch is a 401 on every ingest and looks like "no news today."
- **Supabase free projects pause after ~7 days idle.** The daily crawl keeps it awake.
- **Schema changes are additive and automatic.** Append an
  `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` to `SCHEMA` in `backend/db.py` and redeploy.
  Destructive changes have to be run by hand in the Supabase SQL editor.
