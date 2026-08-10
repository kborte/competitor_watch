# Competitor Watch — Backend API

Base URL:

```
https://competitor-watch-backend-407920901425.me-central1.run.app
```

The read endpoints (`GET`) have **no authentication**. Access is scoped only by CORS to the
origins in `FRONTEND_ORIGINS`, which is hygiene against arbitrary sites reading the data
client-side, not a security boundary. `curl` and server-side code can call them freely.

The write endpoint (`POST /ingest`) requires a bearer secret.

All timestamps in responses are ISO 8601 with a UTC offset. The `today`/`week`/`month`/`year`
windows are computed server-side in Qatar local time (fixed UTC+3, no DST).

## Concepts you need before reading the endpoints

**Window recency prefers `published_at` over `retrieved_at`.** A source published a year ago
that the crawler only just discovered is not "new." `published_at` is often null (undated
social/review pages), and those fall back to `retrieved_at` recency rather than disappearing
from every window except `all` — but only for `product`, `marketing`, `social_sentiment`, and
`other`. For dated-event categories (`news`, `regulatory`, `financial_results`,
`investment_or_acquisition`) a missing publish date means extraction failed, so crawl time is
*not* substituted; those findings only appear under `window=all`.

`week`/`month`/`year` are rolling windows (last 7/30/365 days), not calendar-aligned.

**Companies are canonical entities, not raw strings.** The model's `company` field drifts in
spelling across crawls, so `backend/companies.py` maps every variant to one canonical name.
Pass either the canonical name or any known alias — both `GET /companies` and the `company`
filter resolve to the same grouped entity.

Canonical names:

```
Bupa Arabia · Tawuniya · ADNIC · Sukoon Insurance · Alkhaleej Takaful
Beema · Doha Insurance · QIIC · QLM · Qatar Insurance Market
```

`Qatar Insurance Market` is a special bucket meaning "not any tracked competitor" — banks,
ministries, regulators, and anything the market-wide keyword turns up. Filtering on it is an
inverse match, not an alias lookup.

**QIC is a benchmark, not a competitor.** QIC findings are stored with `is_reference = true`
and excluded from `GET /findings` and `GET /companies` entirely. They surface only in the
`qic_reference` block of `GET /stats`.

**`materiality` is null on duplicates.** Only findings that represent a genuinely new or
changed content state get an LLM call, so re-sightings carry no materiality judgment. They
are filtered out by default (`include_duplicates=false`).

## Enumerations

| Field | Values |
|---|---|
| `category` | `product`, `marketing`, `news`, `social_sentiment`, `regulatory`, `investment_or_acquisition`, `financial_results`, `other` |
| `line` | `motor`, `health`, `travel`, `marine`, `energy`, `aviation`, `pab`, `home`, `yacht`, `market_wide`, `outside_our_lines` |
| `materiality` | `low`, `medium`, `high` |
| `tone` | `positive`, `negative`, `neutral`, `mixed` (social findings only) |
| `window` | `today`, `week`, `month`, `year`, `all` |

`pab` is personal accident and business. `line` describes the insurance line, not the
channel — a website or app finding is tagged with the underlying line, or `market_wide` for
something cross-line.

---

# Read endpoints

## `GET /findings`

List and filter findings. This is the main feed endpoint.

| Param | Values | Default |
|---|---|---|
| `company` | canonical name or any alias | — |
| `category` | see enumerations | — |
| `line` | see enumerations | — |
| `materiality` | `low` \| `medium` \| `high` | — |
| `window` | `today` \| `week` \| `month` \| `year` \| `all` | `all` |
| `sort_by` | `materiality` \| `published_at` \| `retrieved_at` | `materiality` |
| `sort_dir` | `asc` \| `desc` | `desc` |
| `include_duplicates` | `true` \| `false` | `false` |
| `limit` | 1–200 (clamped) | 50 |
| `offset` | integer | 0 |

`sort_by=materiality` ranks high → medium → low with recency as the tiebreak. The other two
sort directly, with nulls last regardless of direction.

Invalid values for `window`, `sort_by`, `sort_dir`, `line`, or `materiality` return **422**
with the allowed set in the detail message. `company` and `category` are not validated — an
unknown value simply matches nothing.

**Example**

```bash
curl "$BASE/findings?window=week&materiality=high&limit=2"
```

```json
[
  {
    "id": 412,
    "keyword": "Sukoon Insurance",
    "company": "Sukoon Insurance",
    "category": "product",
    "platform": null,
    "source_url": "https://www.sukoon.com/en/personal/motor",
    "title": "Sukoon adds agency-repair option to comprehensive motor cover",
    "summary": "Sukoon's motor page now lists an agency-repair tier alongside its existing garage-repair comprehensive product, priced as an add-on.",
    "source_excerpt": "Choose agency repair for repairs at the manufacturer's authorised workshop...",
    "published_at": null,
    "retrieved_at": "2026-08-10T05:12:44.318000+00:00",
    "is_duplicate": false,
    "og_title": "Motor Insurance | Sukoon",
    "og_image_url": "https://www.sukoon.com/assets/og-motor.png",
    "og_description": "Comprehensive and third-party motor cover.",
    "og_site_name": "Sukoon Insurance",
    "verified": true,
    "line": "motor",
    "tone": null,
    "source_location": null,
    "materiality": "high"
  },
  {
    "id": 409,
    "keyword": "Qatar general insurance market",
    "company": "Qatar Insurance Market",
    "category": "regulatory",
    "platform": null,
    "source_url": "https://www.qcb.gov.qa/en/news/circular-2026-14",
    "title": "QCB circular sets new minimum motor third-party limits",
    "summary": "The central bank raised minimum third-party liability limits for motor policies, effective Q4.",
    "source_excerpt": "Insurers shall ensure that all motor policies issued on or after...",
    "published_at": "2026-08-06",
    "retrieved_at": "2026-08-10T05:09:02.771000+00:00",
    "is_duplicate": false,
    "og_title": null,
    "og_image_url": null,
    "og_description": null,
    "og_site_name": null,
    "verified": true,
    "line": "motor",
    "tone": null,
    "source_location": null,
    "materiality": "high"
  }
]
```

Returns `[]` when nothing matches — never 404.

Notes on the payload:

- This is a **light listing shape**. It excludes `source_html` and all LLM audit data. Use
  `GET /findings/{id}` for those.
- The four `og_*` fields are Open Graph metadata captured from the source page, for rendering
  a link-preview card. All four are commonly null — plain-text and PDF sources rarely have OG
  tags, and like `source_html` they are only ever populated on the finding representing a new
  or changed content state, never on a duplicate re-sighting.
- `verified` is false when the crawler could not independently fetch the page the model cited.
- `source_location` is a free-text hint for social findings (which app store, which forum).

## `GET /stats`

Dashboard aggregates: current period, the immediately preceding period of equal length, and
the delta between them.

| Param | Values | Default |
|---|---|---|
| `company` | canonical name or alias | — |
| `category` | see enumerations | — |
| `line` | see enumerations | — |
| `window` | `today` \| `week` \| `month` \| `year` \| `all` | `week` |

**Example**

```bash
curl "$BASE/stats?window=week"
```

```json
{
  "window": "week",
  "current": {
    "findings": 34,
    "high_materiality": 6,
    "tone": { "positive": 3, "negative": 9, "neutral": 4, "mixed": 2 }
  },
  "previous": {
    "findings": 28,
    "high_materiality": 4,
    "tone": { "positive": 5, "negative": 6, "neutral": 3, "mixed": 1 }
  },
  "delta": 6,
  "most_active": { "company": "Tawuniya", "count": 9 },
  "qic_reference": {
    "mentions": 5,
    "previous_mentions": 3,
    "tone": { "positive": 1, "negative": 2, "neutral": 2, "mixed": 0 },
    "previous_tone": { "positive": 2, "negative": 1, "neutral": 0, "mixed": 0 }
  }
}
```

- The two periods never overlap — the previous window is bounded on both sides.
- For `window=all`, `previous`, `delta`, `previous_mentions`, and `previous_tone` are all
  `null` (there is no preceding period).
- `most_active` is `null` when there are no findings in the window.
- `tone` counts only ever come from `social_sentiment` findings; other categories contribute 0.
- `qic_reference` respects `category`, `line`, and `window` but **deliberately ignores** the
  `company` filter — QIC is the benchmark, so its mention count shouldn't change when you
  narrow to one competitor.

## `GET /findings/{id}`

Full detail for one finding, including the LLM audit trail.

| Param | Values | Default |
|---|---|---|
| `view` | `full` \| `summary` | `full` |

`full` includes `llm_call` — the exact prompt sent and the raw model output. `summary` omits
it, keeping the judgment without the model-debugging detail. Anything else returns 422; an
unknown id returns 404.

**Example**

```bash
curl "$BASE/findings/412?view=summary"
```

```json
{
  "id": 412,
  "run_id": "8f3c1e0a-...-7",
  "keyword": "Sukoon Insurance",
  "company": "Sukoon Insurance",
  "category": "product",
  "platform": null,
  "source_url": "https://www.sukoon.com/en/personal/motor",
  "title": "Sukoon adds agency-repair option to comprehensive motor cover",
  "summary": "Sukoon's motor page now lists an agency-repair tier...",
  "source_excerpt": "Choose agency repair for repairs at the manufacturer's authorised workshop...",
  "published_at": null,
  "retrieved_at": "2026-08-10T05:12:44.318000+00:00",
  "is_duplicate": false,
  "og_title": "Motor Insurance | Sukoon",
  "og_image_url": "https://www.sukoon.com/assets/og-motor.png",
  "og_description": "Comprehensive and third-party motor cover.",
  "og_site_name": "Sukoon Insurance",
  "verified": true,
  "line": "motor",
  "tone": null,
  "source_location": null,
  "is_reference": false,
  "has_snapshot": true,
  "change": {
    "materiality": "high",
    "confidence": 0.82,
    "evidence_quote": "Choose agency repair for repairs at the manufacturer's authorised workshop",
    "rationale": "Agency repair is a premium differentiator in Qatari motor and directly competes on our comprehensive tier."
  },
  "llm_call": null
}
```

With `view=full`, `llm_call` is populated instead:

```json
"llm_call": {
  "model": "gemini-3.6-flash",
  "prompt": "A competitor-watch routine found this item. Classify it...",
  "raw_output": "{\"category\": \"product\", \"materiality\": \"high\", ...}",
  "called_at": "2026-08-10T05:12:46.902000+00:00"
}
```

`change` and `llm_call` are both `null` on duplicates and on QIC reference findings — neither
gets classified. `source_html` is never returned here; `has_snapshot` tells you whether it
exists, and `/snapshot` serves it.

## `GET /findings/{id}/snapshot`

The raw captured HTML of the source page as it looked at observation time. Served as
`text/html`, not JSON — meant to be dropped straight into an `<iframe>`.

A `<base href="...">` tag is injected into `<head>` so relative asset paths resolve against
the original site. The response carries `Content-Security-Policy: sandbox`, which blocks any
script in the captured page from executing — enforced by the browser regardless of how the
consumer embeds it, so it doesn't depend on remembering a `sandbox` attribute.

**404** if the finding doesn't exist, or if no snapshot was captured for it. That second case
is normal: one snapshot exists per distinct content state, not per crawl run. Most
`product`/`marketing` findings have one; `news` and `social_sentiment` only get one on first
sighting. Check `has_snapshot` first.

## `GET /companies`

Per-company counts for sidebar badges. No parameters.

```bash
curl "$BASE/companies"
```

```json
[
  { "company": "ADNIC", "new_today": 0, "new_this_week": 2, "new_this_month": 7, "total_findings": 31 },
  { "company": "Alkhaleej Takaful", "new_today": 1, "new_this_week": 3, "new_this_month": 9, "total_findings": 44 },
  { "company": "Qatar Insurance Market", "new_today": 2, "new_this_week": 8, "new_this_month": 26, "total_findings": 118 }
]
```

Sorted alphabetically by canonical name. Counts are summed across every raw-string alias of
that company. The `new_*` counts exclude duplicates and use the same recency rules as
`GET /findings`; `total_findings` includes duplicates and ignores windows. QIC reference
findings are excluded entirely.

A company with zero findings does not appear in the list at all.

## `GET /crawl-status`

```bash
curl "$BASE/crawl-status"
```

```json
{ "latest_crawl_at": "2026-08-10T05:14:31.882000+00:00" }
```

The most recent `retrieved_at` across all findings, for a "last updated" indicator.
`null` when the database is empty. Parse it as a timezone-aware timestamp rather than
assuming `+00:00` — the offset reflects the database session's timezone.

---

# Write endpoint

## `POST /ingest`

Used by the crawler only. One finding per request in normal operation, though the schema
accepts a batch.

**Headers**

```
Authorization: Bearer <WEBHOOK_SECRET>
Content-Type: application/json
```

**Body**

| Field | Type | Required |
|---|---|---|
| `routine_run_id` | string — idempotency key | yes |
| `run_started_at` | ISO datetime | yes |
| `run_completed_at` | ISO datetime | yes |
| `keywords` | string[] | yes |
| `findings` | Finding[] | yes (may be empty) |
| `keywords_with_no_findings` | string[] | no, default `[]` |
| `notes` | string | no, default `""` |

Each `Finding`:

| Field | Type | Required |
|---|---|---|
| `keyword` | string | yes |
| `company` | string | yes |
| `category` | see enumerations | yes |
| `source_url` | string | yes |
| `title` | string | yes |
| `summary` | string | yes |
| `source_excerpt` | string — verbatim from the source | yes |
| `retrieved_at` | ISO datetime | yes |
| `platform` | string \| null | no |
| `published_at` | date (`YYYY-MM-DD`) \| null | no |
| `source_html` | string \| null | no — the captured page, enables snapshots and hash dedup |
| `og_title`, `og_image_url`, `og_description`, `og_site_name` | string \| null | no |
| `verified` | bool | no, default `true` |
| `line` | see enumerations \| null | no |
| `tone` | see enumerations \| null | no |
| `source_location` | string \| null | no |
| `is_reference` | bool | no, default `false` — QIC benchmark findings |

**Responses**

```json
{ "status": "processed", "routine_run_id": "8f3c...-7", "new_or_changed": 1, "duplicates": 0, "errors": 0 }
```

```json
{ "status": "already processed", "routine_run_id": "8f3c...-7" }
```

| Code | Meaning |
|---|---|
| 200 | Processed, or already processed (idempotent replay) |
| 401 | `Authorization` header missing or the secret doesn't match |
| 422 | Body failed schema validation — the raw body and the error are stored in `rejected_payloads` for debugging |

`errors` counts findings where the classification LLM call threw. Those are stored as
findings with no materiality rather than dropped.

---

# Recommended usage

Both dashboards can call any endpoint — this is convention, not enforcement.

**Executive / upper-management view.** Keep it high-signal:

- `GET /findings?window=week` — `sort_by` already defaults to `materiality desc`, so the
  most important items surface without extra parameters.
- `GET /findings/{id}?view=summary` when drilling in — the judgment and rationale, without
  raw prompts.
- `GET /companies` for badges — `new_this_week` / `new_this_month` fit a weekly review
  cadence better than `new_today`.
- Skip `view=full` and `/snapshot`. Those are the audit layer.

**Ops / investigation view.** `view=full` plus `/snapshot` lets you verify a claim against
the literal page HTML and inspect the model's raw reasoning. `include_duplicates=true`
shows re-sightings, useful for confirming the dedup ledger is behaving.

# Gotchas

- **`window` defaults differ per endpoint**: `all` on `/findings`, `week` on `/stats`. Easy to
  compare mismatched numbers by accident.
- **`limit` is silently clamped** to 1–200. Asking for 1000 gets you 200 with no warning.
- **Dated categories vanish outside `window=all` when undated.** A `news` finding whose
  `published_at` failed to extract appears only under `all`. If a finding you know exists is
  missing from `week`, check its `published_at`.
- **`materiality` filtering excludes duplicates implicitly**, since duplicates have no
  materiality at all.
- **CORS is off entirely when `FRONTEND_ORIGINS` is unset.** The middleware is only added if
  the variable is non-empty, so browser calls fail while `curl` works. See `DEPLOY.md`.
