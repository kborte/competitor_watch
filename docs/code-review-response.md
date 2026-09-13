# Code review response

Every item raised across the six review batches, with what was done and why.
Where something was **not** changed, the reasoning is recorded rather than the
item being dropped.

Verification for the whole batch: `ruff` clean, **164 Python tests**, **10
frontend tests**, `tsc --noEmit` clean, and end-to-end runs against a real
Postgres — one seeded with the *old* schema to confirm the migration path, one
booted purely from the composed `DATABASE_URL`.

**Legend** — ✅ fixed · 🟡 fixed differently than suggested · 📌 deliberate, not
changed · ⚠️ partially incorrect as reported

---

## 1. Shared-Ingress migration

One origin serves both the dashboard (`/`) and the API (`/api`).

| Item | | What changed |
|---|---|---|
| `frontend/lib/api.ts` — `new URL(path, base)` discards the base path | ✅ | Replaced with string concatenation. `new URL("/findings", "https://host/api")` returned `https://host/findings` — the `/api` prefix silently vanished — and a relative base threw `TypeError`. Verified against `/api`, `/api/`, `https://host/api` and `http://backend:8080`. |
| CORS no longer needed | ✅ | Middleware **removed entirely**, along with `FRONTEND_ORIGINS` from `config.py`, the env templates, `DEPLOY.md`, `frontend/README.md` and `docs/backend-api.md`. |
| Backend not exposed separately; `/ingest` closed at the Ingress | 📌 | No code change needed — `/ingest` already requires the bearer secret, and reachability is the Ingress's business. Recorded in `docs/backend-api.md` as the deliberate access-control boundary. |
| `NEXT_PUBLIC_API_BASE_URL` becomes `/api` | ✅ | Now works. CI builds with `NEXT_PUBLIC_API_BASE_URL=/api` to prove one image is environment-independent. |

`frontend/lib/api.test.ts` pins this, including two tests that assert the *old*
`new URL()` behaviour explicitly, so nobody reintroduces it.

---

## 2. Correctness

| File | | What changed |
|---|---|---|
| `ingest.py:39` — ledger written before classification | ✅ | Each finding now writes inside a **savepoint**, with the ledger `upsert` last. Row, verdict and ledger entry land together or not at all. A failed classification stores *nothing*, so the next crawl sees the URL as new and retries. |
| `crawler.py:62` — response body never read | ✅ | `deliver()` returns a `Delivery(stored, classify_errors)` instead of a bool. HTTP 200 with `{"errors": 1}` is now reported as *stored but unclassified*, and the run summary reads `N delivered, N failed, N classified with errors`. |
| `ingest.py:19-20` — comment promises a retry that doesn't exist | ✅ | Comment rewritten (the false claim was mine, introduced in `535b11e`; `git log -S` confirms). Later the retry was *implemented* as well, once measurement showed it costs no model tokens — so the comment and the code now agree in the other direction. |
| `classify.py:66` — `response.parsed` may be `None` | ✅ | Explicit check raising `ValueError` with the model's actual output. `.parsed` is `None` on a safety block or token-limit truncation, which is not an exception. |
| `ingest.py:66-70` — result used outside `try` → 500 | ✅ | Fixed by the same savepoint work. A `None` verdict is now caught, counted as an error and isolated to one finding. Verified: **no exception escapes, no 500.** |
| `crawler.py:60` — timeout mismatch | ✅ | Ordered innermost-strictest: **Gemini 45s < crawler 90s < server 300s.** A test asserts the first inequality so the ordering can't silently invert. |

### ⚠️ One correction

> **`ingest.py:66-70`** — "rollback of the whole transaction"

True, but the blast radius is one finding: the crawler posts one finding per
request. And because the `routine_runs` row rolled back too, idempotency never
blocked a retry — so this was self-healing on the next crawl, unlike the ledger
bug, which was permanent. Worth separating: only one of these two lost data for
good.

---

## 3. Architecture and performance

| File | | What changed |
|---|---|---|
| `ingest.py:18` — LLM call inside an open transaction | ✅ | `process()` now runs in three phases: claim + dedup (short transaction), classify (**no connection held**), write (short transaction). Verified by counting `db.connect()` calls: two per payload, neither spanning the model call. |
| `main.py:47` — `async def` with a synchronous body | 🟡 | Kept `async def` and offloaded via `run_in_threadpool`. Converting to `def` would have meant taking a typed body parameter, and FastAPI would then reject a malformed payload *before* the handler could store it in `rejected_payloads`. Verified: `/healthz` answers in **6 ms** during a 1.5 s ingest. |
| `main.py:34` — `init_db()` at import races during RollingUpdate | ✅ | Wrapped in `pg_advisory_xact_lock`. First pod applies the schema, others wait then no-op. A migration Job is the cleaner long-term pattern and is noted in `DEPLOY.md`, but this is safe now with zero deploy ceremony. |
| `db.py:18` — no indexes at all | ✅ | Eight added, including the two audit-chain foreign keys and a partial index matching the feed's default shape. Postgres indexes primary keys but never foreign keys, so every join in `reads/` was a sequential scan. `EXPLAIN` confirms `idx_findings_feed` and `idx_llm_calls_finding_id` are used. |
| `discover.py:78` — serial, unbounded source fetching | ✅ | Capped at `MAX_SOURCES_PER_KEYWORD` (15) **before** fetching, and fetched concurrently (6 workers). 20 sources × 15 s serially could exhaust the 300 s per-company budget before structuring even began. |

---

## 4. LLM cost and reliability

| Item | | What changed |
|---|---|---|
| `classify.py:59` — no `max_output_tokens` / `thinking_budget` / `timeout` | ✅ | Bounded. `thinking_budget=0`: a short structured verdict over an excerpt already in the prompt. Strictest timeout of the three, since it runs inside a request the crawler is waiting on. |
| `discover.py:64` — same | ✅ | Bounded. Keeps `thinking_budget=2048` and the longest timeout — it is the only call that reaches out to the web. |
| `structure.py:85` — same | ✅ | Bounded. `thinking_budget=0`, but the largest `max_output_tokens`: its output is a list of findings. |
| No retries on 429/503 | ✅ | Linear backoff, 3 attempts, **only** on 429/500/502/503/504. Permanent statuses (400/401/403/404/422) fail on the first attempt — retrying those only delays the error and spends quota. |
| `crawler.py:64` — 401, 422 and 503 handled identically | ✅ | 401/403 now raise `FatalDeliveryError` and abort the run. A secret mismatch previously produced a full run of quiet failures. |
| `structure.py:72` — the only input cap in the project | ✅ | Still capped per source, but the *number* of sources is now bounded too, so the whole block is bounded. The research summary — previously pasted in whole with no cap at all — is capped at 12 000 chars. |
| `crawler.py:134` — no per-run ceiling, no kill switch | ✅ | `MAX_FINDINGS_PER_CRAWL` (200) and `MAX_FINDINGS_PER_KEYWORD` (20). `CRAWL_ENABLED=false` stops the crawl before any paid call. `run()` returns a non-zero exit code when anything needed attention. |
| `ingest.py:66` — `usage_metadata` not recorded | ✅ | Three nullable columns on `llm_calls`. Spend is now measurable per finding and per run from SQL rather than only on the Google bill. |

All defaults are env-overridable; nothing requires a code change to retune.

---

## 5. Security

| File | | What changed |
|---|---|---|
| `main.py:50` — secret compared with `!=` | ✅ | `hmac.compare_digest`. `!=` short-circuits at the first differing byte, so response timing leaked how much of a guess was right. |
| `fetch.py:250` — body fully downloaded before the size check | ✅ | `stream=True` with an 8 MB read ceiling enforced *while* reading. The 2 MB snapshot cap decides what to **store**; this decides when to stop **reading**. |
| `fetch.py:239` — no scheme check, redirect limit, or private-IP blocking | ✅ | Scheme restricted to http/https, redirects capped at 5, and every resolved address checked with `ip_address(...).is_global`. The final redirect hop is re-checked, since it is a different URL than the one vetted. Verified blocked: `file://`, `gopher://`, `127.0.0.1`, `localhost`, `169.254.169.254`, RFC1918, `[::1]`, and `*.svc.cluster.local`. |
| `main.py:67-133` — all GETs unauthenticated | 📌 | **Deliberate, per your decision.** Access control lives at the Ingress. Now documented as a decision in `config.py`, `main.py`, `docs/backend-api.md` and the architecture page, with the caveat stated plainly: anything that can route to the service can read the findings, so the API must not get a public hostname without a gateway. |

The SSRF hardening matters more than it did: these URLs come from Gemini's
grounding metadata — not attacker-chosen, but not ours either — and in a cluster
a request to a link-local address reaches things a public runner never could.

---

## 6. Consistency and data lifecycle

| Item | | What changed |
|---|---|---|
| `reclassify_regulatory.py` — mutates `category` without an audit entry | ✅ | Now writes an `llm_calls` row for every change, so "why is this finding tagged this way" stays answerable. Also added a `None`-response guard. |
| `reclassify_regulatory.py` — breaks the `CRAWL_RECENCY_CATEGORIES` invariant | ⚠️ | **Not reproducible as described.** The script selects only `WHERE category = 'regulatory'`, and `regulatory` is *not* a crawl-recency category. Every move it can make either keeps the row in the dated group or moves it *into* the crawl-recency group, which only **adds** window visibility. Nothing falls out. The hazard is real in the opposite direction, so the script now detects and warns on any freshness-class change, and the invariant is documented at the mutation site. |
| `schemas.py` — `line: Line` vs `line: Optional[Line]` | 📌 | **Intentional, now documented on both sides.** rows predating the field exist, and rejecting a delivery over it would lose a finding that is otherwise storable. A missing line only narrows the dashboard's line filter. The crawler still always sets it. |
| `Dockerfile` — "single worker, no pool needed" | ✅ | Reworded. It is a property of *this configuration*, not of the app: one worker is a choice, the app is safe at any worker count, and scaling is done with replicas. |
| `fetch.py:19` — `source_html` up to 2 MB with no retention | ✅ | `backend/scripts/prune_snapshots.py` clears `source_html` past a 90-day window (`SNAPSHOT_RETENTION_DAYS`), dry-run by default. Findings and audit chain are preserved; what is lost is re-rendering that page. Run as a daily CronJob. |

---

## 7. Infrastructure

| Gap | | What changed |
|---|---|---|
| No tests | ✅ | **164 Python tests** (`tests/`) covering the freshness rule, dedup, the company registry, fetch guards, date extraction, retry policy, delivery outcomes, configuration assembly, and the shared-package boundary. **10 frontend tests** for URL building. No test makes a network call or needs a database. |
| `print` everywhere, no `logging` | ✅ | `logging` throughout backend and crawler, with `LOG_LEVEL` configurable. Classification failures are now `log.exception` rather than a silently incremented counter. |
| No `/healthz` without the DB | ✅ | `/healthz` (touches nothing) and `/readyz` (`SELECT 1`, 503 on failure). Liveness deliberately depends on nothing, so a database blip cannot restart every pod at once. |
| No "0 delivered in 24 h" alert | ✅ | `.github/workflows/crawl-alert.yml`, daily at 08:00 UTC, fails if the newest finding is older than 30 h. All three paths tested against a stub server: fresh, stale, and never-delivered. |
| No CI | ✅ | `.github/workflows/ci.yml` — ruff + pytest, and typecheck + tests + build for the frontend. No secrets, no database, no Gemini access, so CI can't be broken by an outage. |
| Image tagged `:latest` | ✅ | `DEPLOY.md` now tags by commit SHA. With a moving tag you cannot tell which code is running, so "is the fix deployed?" is unanswerable and a rollback target is a guess. |

---

## 8. Configuration consolidation

Raised separately, after the batches above: one `.env` for every component, with
a committed template.

| Item | | What changed |
|---|---|---|
| Per-package env files (`backend/.env.example`, `research_crawler/.env.example`, `frontend/.env.local.example`) | ✅ | Replaced by one root `.env` + committed `.env.example`. Both `config.py` files load the repo-root file. |
| `DATABASE_URL` composed with `${VAR}` | 🟡 | Composed in `backend/config.py` instead, from the `POSTGRES_*` parts, with an explicit `DATABASE_URL` taking priority. `${}` expands under python-dotenv but is copied **literally** by `kubectl --from-env-file` and `docker compose env_file:`, so one file would have meant two different things. The password is percent-encoded — a raw `@` or `/` would be parsed as URL structure. |
| `LOG_LEVEL=debug` | ✅ | Would have **crashed on boot**: `ValueError: Unknown level: 'debug'`. Now uppercased at read. |
| `KEY=   # hint` inline comments | ✅ | Would have **silently become values**: python-dotenv strips a trailing comment only when a value precedes it, so an empty `WEBHOOK_SECRET` with a hint beside it starts the app with the hint as its secret. Every comment is on its own line, and a test enforces it. |
| `CRAWL_ENABLED` vs `CRAWL_DISABLED` | ✅ | Adopted the positive form. An inverted boolean is the kind of thing set to `false` in an emergency that quietly keeps running. |
| `GEMINI_MODEL` hardcoded in four files | ✅ | Read from config; a model change is now a redeploy, not a code edit. |
| `FRONTEND_ORIGINS`, `UVICORN_WORKERS`, `TZ` | ✅ | Dropped — nothing reads them. |
| `NEXT_PUBLIC_API_BASE_URL` absent from the proposed file | ✅ | Added, with the trap named: Next inlines it at **build** time, so setting it in the pod environment has no effect whatsoever. |
| One `GEMINI_TIMEOUT_MS` for all three calls | 📌 | Kept three separate sets, per your decision. The three calls do different work — search grounding needs reasoning and the longest timeout, classification needs neither and must be strictest. |

Three tests guard the template against drift: no variable read without being
documented, no documented variable unread, and no `${}` or inline comments.

---

## Deliberate decisions, collected

Five things were left as they are. Each is a decision, not an oversight:

1. ~~**No retry in `deliver()`.**~~ **Superseded.** Originally kept as-is on the
   grounds that tomorrow's crawl recovers a lost delivery. Revisited once it was
   measured: a retry costs **zero model tokens**, because `/ingest` is idempotent
   on `routine_run_id` and commits that row *before* classifying, so a repeat
   short-circuits without reaching the model — even while the original request is
   still in flight. `deliver()` now retries 3× on timeouts and 5xx only; after
   that it gives up and the next daily crawl re-reports the finding.
2. **Read endpoints unauthenticated.** Access control is the Ingress's job. The
   consequence is written down rather than glossed.
3. **`line` required in the crawler, optional in the backend.** Strict sender,
   tolerant receiver — deliberate, now commented in both files.
4. ~~**Schemas, HTML utilities and the retry helper duplicated.**~~
   **Superseded.** Originally kept on the reasoning that separately-deployed
   services should agree on a wire format rather than on code. That holds for
   independently-versioned services, not for two packages in one repo that change
   in the same commit — there the duplication only costs. All three now live in
   `shared/`, which imports from neither package and reads no configuration.
   Tests enforce both properties.
5. **Advisory lock rather than a migration Job.** Safe with any replica count and
   keeps the deploy a single step. The Job pattern is noted as the eventual
   target.

## One behaviour change worth flagging

The old comment said *"every finding is stored regardless of what follows."*
That is **no longer true**: a finding whose classification fails is now stored
nowhere. This is the trade that makes the retry work — keeping the row while
dropping the ledger entry would produce a second row for the same URL on the
retry, i.e. duplicate cards in the dashboard. Nothing auditable is lost, because
`routine_runs.raw_payload` still holds the verbatim delivery.

## Not addressed

- **The category overlay is still imprecise.** On a 200-row production sample the
  classifier's category overrides the crawler's on 7% of findings, and at least
  three of those were regressions — including a product review retagged
  `financial_results`, which removed it from `category=social_sentiment`. This
  predates the review batch and needs a product decision: revert the overlay,
  gate it on confidence, or accept it.
- **Deployment manifests for the cluster.** `DEPLOY.md` still documents the Cloud
  Run path. The probes, retention job and commit-pinned images that k8s manifests
  would need now exist, but the manifests themselves do not.
