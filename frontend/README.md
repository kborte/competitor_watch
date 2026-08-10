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
cp .env.local.example .env.local   # point NEXT_PUBLIC_API_BASE_URL at your backend
npm run dev
```

Requires the backend (`../backend`) running and reachable at
`NEXT_PUBLIC_API_BASE_URL`, with `FRONTEND_ORIGINS` on the backend including
`http://localhost:3000`.

## Structure

- `app/` — routes, root layout, the TanStack Query provider.
- `components/` — sticky header and filters, KPI/attention panels, grouped feed, and the
  evidence/detail panel with the existing snapshot and audit disclosures.
- `lib/api.ts` — typed fetch wrappers for every backend endpoint.
- `lib/types.ts` — TypeScript interfaces mirroring the API's response shapes.
- `lib/time.ts` — fixed UTC+3 (Qatar, no DST) formatting, matching the backend's own window math.

## Deploying

Vercel, zero-config. Live at https://competitor-watch-qic.vercel.app.

Two settings, on both sides:

1. `NEXT_PUBLIC_API_BASE_URL` in the Vercel project's environment variables, pointed at
   https://competitor-watch-backend-407920901425.me-central1.run.app. It's inlined at build
   time, so **redeploy after changing it** — setting the variable alone does nothing.
2. `FRONTEND_ORIGINS` on the backend must include this app's origin, or every request fails
   CORS while `curl` keeps working. See [`../DEPLOY.md`](../DEPLOY.md) step 4b.

Preview deployments get their own `*.vercel.app` hostnames, which aren't in
`FRONTEND_ORIGINS` — so previews fail CORS unless you add them (it splits on commas).
