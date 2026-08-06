# Competitor Watch — middle-management dashboard

Next.js (App Router, TypeScript) frontend for the middle-management audience
described in [`../docs/read-api.md`](../docs/read-api.md). Client-fetched via
TanStack Query straight against the deployed backend — no server-rendering,
no auth (the backend's read endpoints are open; CORS is the only guard).

The upper-management dashboard is a separate team's build against the same
API — nothing in this app is shared with it beyond the API contract.

## Local development

```bash
npm install
cp .env.local.example .env.local   # point NEXT_PUBLIC_API_BASE_URL at your backend
npm run dev
```

Requires the backend (`../backend`) running and reachable at
`NEXT_PUBLIC_API_BASE_URL`, with `FRONTEND_ORIGINS` on the backend including
`http://localhost:3000`.

## Structure

- `app/` — routes, root layout, the TanStack Query provider.
- `components/` — `Header` (crawl-freshness indicator), `FilterBar` (window/category/company),
  `SortToggle`, `FeedList`/`FeedCard`, `RecordPanel` (detail view + audit-trail disclosure).
- `lib/api.ts` — typed fetch wrappers for every backend endpoint.
- `lib/types.ts` — TypeScript interfaces mirroring the API's response shapes.
- `lib/time.ts` — fixed UTC+3 (Qatar, no DST) formatting, matching the backend's own window math.

## Deploying

Vercel, zero-config. Set `NEXT_PUBLIC_API_BASE_URL` to the deployed backend's
URL in the Vercel project's environment variables — that's the only
production config needed.
