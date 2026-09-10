# Competitor Watch — middle-management dashboard

Next.js (App Router, TypeScript) frontend for the middle-management audience
described in [`../docs/backend-api.md`](../docs/backend-api.md). Client-fetched via
TanStack Query straight against the deployed backend — no server-rendering,
no auth (the backend's read endpoints are open; CORS is the only guard).

The upper-management dashboard is a separate team's build against the same
API — nothing in this app is shared with it beyond the API contract.

## Local development

```bash
npm install
# NEXT_PUBLIC_API_BASE_URL comes from the repo-root .env (see ../.env.example)
npm run dev
```

Requires the backend (`../backend`) running and reachable at
`NEXT_PUBLIC_API_BASE_URL`. Locally that is an absolute URL
(`http://localhost:8000`), because the two run on different ports; in the
cluster it is the relative prefix `/api`, since both are served from one origin.

## Structure

- `app/` — routes, root layout, the TanStack Query provider.
- `components/` — sticky header and filters, KPI/attention panels, grouped feed, and the
  evidence/detail panel with the existing snapshot and audit disclosures.
- `lib/api.ts` — typed fetch wrappers for every backend endpoint.
- `lib/api.test.ts` — URL-building tests (`npm test`, Node's built-in runner).
- `lib/types.ts` — TypeScript interfaces mirroring the API's response shapes.
- `lib/time.ts` — fixed UTC+3 (Qatar, no DST) formatting, matching the backend's own window math.

## Deploying

Vercel, zero-config. Live at https://competitor-watch-qic.vercel.app.

One setting: `NEXT_PUBLIC_API_BASE_URL`. It is inlined at build time, so
**redeploy after changing it** — setting the variable alone does nothing.

In the cluster, set it to `/api`. The dashboard and the API share one origin
behind the Ingress (dashboard at `/`, API at `/api`), which means:

- No CORS configuration on either side. Requests are same-origin and never preflight.
- The same image runs in every environment, because the base URL is a path, not
  a domain. Changing the domain needs no rebuild.

`lib/api.ts` builds request URLs by string concatenation for exactly this
reason. `new URL(path, base)` resolves an absolute path against the base's
*origin* and discards the base's own path, so `/api` silently vanished — and a
relative base threw a `TypeError` outright. `lib/api.test.ts` pins that.
