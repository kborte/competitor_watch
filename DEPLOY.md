# Deploying the backend

One Cloud Run service, `competitor-watch-backend`, in project `qic-ai-interns`, region `me-central1`.

https://competitor-watch-backend-407920901425.me-central1.run.app

Database is Supabase Postgres, not Cloud SQL. The crawler is not deployed here — it runs in GitHub Actions.

## Before you start

Check you are the right user.

```bash
gcloud config get-value account   # ai-intern@qic-ai-interns.iam.gserviceaccount.com
gcloud config get-value project   # qic-ai-interns
```

Your own `borte.kurbanbay@` login cannot deploy. If it prints the wrong account:

```bash
gcloud auth activate-service-account --key-file=~/.gcp/ai-intern-key.json
gcloud config set project qic-ai-interns
```

- the key is `chmod 600`, lives outside the repo, and is gitignored
- switch back afterwards with `gcloud config set account borte.kurbanbay@bd.qatarinsurance.com`

You do not need Docker. Cloud Build builds the image on Google's machines.

## Step 1. Clean working tree

```bash
git status --porcelain     # must print nothing that belongs in the image
```

`gcloud builds submit` uploads **the folder, not the commit**. It does not know what you have committed. Uncommitted edits under `backend/` will ship; uncommitted edits anywhere else will not, because the Dockerfile only copies `backend/`.

## Step 2. Do you need a build?

| What you changed | What to run |
| --- | --- |
| Anything under `backend/` | Steps 3 to 5 |
| `Dockerfile` or `backend/requirements.txt` | Steps 3 to 5 |
| Only an env var or secret | Step 4b only. No build. |
| `research_crawler/` | Nothing here. It runs in GitHub Actions, redeploys itself on push. |
| `frontend/` | Nothing here. Deployed separately. |

## Step 3. Build

```bash
gcloud builds submit --tag me-central1-docker.pkg.dev/qic-ai-interns/eip/competitor-watch-backend:latest . --region=global --async
```

About two minutes. `--async` because this account cannot stream build logs — without it gcloud errors out even though the build succeeds.

Check it finished:

```bash
gcloud builds list --region=global --limit=1 --format='value(status)'   # want SUCCESS
```

- the image lives in the `eip` repo because this account cannot create Artifact Registry repos
- `eip-api` and `eip-web` are your teammate's images in the same repo. Never build to those two names.
- only ever tagged `:latest`, so you cannot tell from Artifact Registry which commit is live. Rollback still works (step 6).

## Step 4. Deploy

```bash
gcloud run deploy competitor-watch-backend --region=me-central1 \
  --image=me-central1-docker.pkg.dev/qic-ai-interns/eip/competitor-watch-backend:latest
```

Pass `--image` and nothing else. Secrets, scaling, port and auth all carry over from the last revision.

**Never use `--set-secrets` or `--set-env-vars` here.** Both delete everything not listed, so a one-line tweak silently wipes the rest and the service comes back broken. Use step 4b instead.

## Step 4b. Changing only a setting

```bash
gcloud run services update competitor-watch-backend --region=me-central1 \
  --update-env-vars=FRONTEND_ORIGINS=https://your-frontend-url
```

About 30 seconds, no build.

To change a secret's value, add a new version in Secret Manager and redeploy — the service pins `:latest`, but a running revision keeps the version it started with.

## Step 5. Smoke test

```bash
URL=$(gcloud run services describe competitor-watch-backend --region=me-central1 --format='value(status.url)')

curl -s $URL/crawl-status                  # process started AND reached Supabase
curl -s "$URL/findings?window=all&limit=1" # read path works, data is there
curl -s "$URL/stats?window=week"           # aggregation works
```

Run all three.

- `/crawl-status` is the one that matters most. `db.init_db()` runs at import in `backend/main.py`, so any response at all proves the container booted *and* connected to Supabase. A bad `DATABASE_URL` is a startup crash, not a 500.
- `/findings` returning `[]` after a crawl means ingestion is broken, not that there is no news.

## Step 6. If it is broken, roll back

```bash
gcloud run revisions list --service=competitor-watch-backend --region=me-central1

gcloud run services update-traffic competitor-watch-backend --region=me-central1 \
  --to-revisions=competitor-watch-backend-00002-abc=100
```

Seconds, and you get the exact previous container with its exact settings. Do not rebuild while the service is down.

## Things that will trip you

**You cannot read logs from the terminal.** `gcloud builds log` and `gcloud logging read` both return PERMISSION_DENIED on this account. Use the Cloud Console → Cloud Run → the service → **Logs** tab.

**The crawler is a separate deployment.** `.github/workflows/crawl.yml` runs daily at 05:00 UTC on GitHub's runners and POSTs to `$URL/ingest`. If you change the Cloud Run URL, update the `BACKEND_INGEST_URL` repo secret or every delivery silently fails.

**A green GitHub Actions run does not mean data landed.** `deliver()` in `research_crawler/crawler.py` catches delivery failures and the process still exits 0. Check the last log line: `crawl <id> complete — N delivered, N failed`.

**`WEBHOOK_SECRET` must match in two places** — Secret Manager and the GitHub repo secret. A mismatch is a 401 on every ingest, which shows up as `N failed` and nothing else.

**The browser cannot read the API until `FRONTEND_ORIGINS` is set.** `backend/main.py` only adds the CORS middleware if that variable is non-empty, so with it unset every request from the dashboard fails while `curl` works fine. Set it with step 4b once the frontend has a URL. Origin only: scheme and host, no trailing slash.

**Supabase free projects pause after ~7 days of no activity.** The daily crawl keeps it awake. If the backend starts erroring after a quiet stretch, un-pause it in the Supabase dashboard.

**Schema changes are automatic.** `SCHEMA` in `backend/db.py` runs on every container start and every statement is idempotent. Add a column by appending `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` and redeploying. Destructive changes (drop, rename, retype) cannot be expressed this way — run those by hand in the Supabase SQL Editor.

## First-time setup, for reference

Already done, listed in case it needs redoing.

- Secrets `DATABASE_URL`, `WEBHOOK_SECRET`, `GEMINI_API_KEY` in Secret Manager, labelled `project: competitor-watch`
- The runtime account `407920901425-compute@developer.gserviceaccount.com` was granted **Secret Manager Secret Accessor** on each of the three secrets, from the Console as `borte.kurbanbay@`. `ai-intern@` cannot do this. Any new secret needs the same grant or the deploy is rejected.
- First deploy used the full flag set: `--set-secrets`, `--allow-unauthenticated`, `--max-instances=4`, `--memory=512Mi`, `--timeout=300`, `--port=8080`
- GitHub repo secrets: `BACKEND_INGEST_URL`, `WEBHOOK_SECRET`, `GEMINI_API_KEY`
- Initial data: Actions tab → Competitor research crawl → Run workflow → `search_window_days=365`
