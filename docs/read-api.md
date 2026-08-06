# Competitor Watch — Read API

Base URL: the deployed backend's origin (e.g. `https://competitor-watch-backend.onrender.com`).
No authentication on any endpoint below — access is scoped only by CORS to the known
frontend origins. All timestamps in responses are UTC; `today`/`week`/`month` windows are
computed server-side using Qatar local time (UTC+3).

## Endpoints

### `GET /findings`
List/search findings. Query params (all optional):

| param | values | default |
|---|---|---|
| `company` | exact match | — |
| `category` | `product`\|`marketing`\|`news`\|`social_sentiment`\|`regulatory`\|`other` | — |
| `window` | `today`\|`week`\|`month`\|`all` | `all` |
| `prioritized` | bool | `true` if window is `week`/`month`, else `false` |
| `include_duplicates` | bool | `false` |
| `limit` | 1–200 | 50 |
| `offset` | int | 0 |

When `prioritized` is in effect, results sort by materiality (high → medium → low), then
recency. Otherwise, plain recency. Response items **exclude** `source_html` and any LLM
audit data — this is a light listing payload.

### `GET /findings/{id}`
Full detail for one finding. Query param: `view` = `full` (default) or `summary`.

- `full` — finding fields + `change` (materiality, confidence, evidence_quote, rationale) +
  `llm_call` (model, prompt, raw_output, called_at — the raw LLM audit trail) + `has_snapshot`.
- `summary` — same, minus `llm_call`. Same judgment/materiality info, without the
  internal model-debugging detail.

404 if the id doesn't exist.

### `GET /findings/{id}/snapshot`
Raw captured HTML of the source page at observation time, served as `text/html`
(not JSON) — meant to be dropped into an `<iframe>`. 404 if the finding doesn't exist,
or if no snapshot was captured for it (duplicates never get one; see caveat below).

### `GET /companies`
Per-company aggregate counts: `new_today`, `new_this_week`, `new_this_month`,
`total_findings`. Good for sidebar badges.

### `GET /crawl-status`
`{"latest_crawl_at": <ISO timestamp with UTC offset, or null if no findings exist yet>}` —
the most recent `retrieved_at` across all findings. Backs a "last crawled at"
freshness indicator in the UI. Parse it as a timezone-aware timestamp rather
than assuming the offset is always `+00:00` — it reflects the DB session's
timezone setting.

## Recommended usage for the upper-management dashboard

This is a UI convention, not enforced access control — both frontends can call any
endpoint above. But for a high-signal, low-noise executive view:

- **`GET /findings?window=week`** (or `month`) — already sorts by materiality by
  default, so the highest-signal items surface first.
- **`GET /findings/{id}?view=summary`** when drilling into one item — gives the
  materiality judgment and rationale without raw LLM prompt/output.
- **Skip `/findings/{id}/snapshot` and `view=full`** — those are the audit/investigation
  layer (verifying a claim against the literal page HTML, or checking the model's raw
  reasoning), which belongs in the middle-management/ops-facing tool, not an executive
  summary. Nothing technically blocks calling them later if a feature needs it.
- **`GET /companies`** for sidebar badges — `new_this_week`/`new_this_month` fit a
  weekly/monthly executive review cadence better than `new_today`.

## Caveats worth knowing

- `materiality` is `null` on duplicate/unclassified findings — filtered out by default
  since `include_duplicates` defaults to `false`.
- A snapshot only exists for the finding that represents a genuinely new/changed
  content state (one snapshot per distinct state, not one per crawl run) — so most
  `product`/`marketing` findings *will* have one, but `news`/`social_sentiment`/etc.
  only get one on first sighting, and it's normal for `has_snapshot` to be `false`.
