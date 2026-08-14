# Replate — Frontend

React (Vite + TypeScript) mobile-first frontend for Replate. A working UI wired against the
backend's real API contract, with Cognito sign-in mocked locally since no user pool exists
yet.

## Setup

```bash
cd frontend
npm install
cp .env.example .env
```

The backend must be running locally for any of this to talk to real data — see
[`../backend/README.md`](../backend/README.md) (`docker compose up -d`).

## Run

```bash
npm run dev
```

Opens on `http://localhost:5173`. The port is pinned with `strictPort` in `vite.config.ts`, so
if something else is already on 5173 the dev server **fails loudly** rather than quietly moving
to 5174 — which previously meant opening the wrong app's dev server without noticing.

Sign in with the mocked "Sign in" button (see Auth below) to reach Home.

## Auth (mocked locally)

`VITE_COGNITO_ENABLED=false` (default) makes Sign In an instant local mock — no AWS account
needed. The mock user's `oid` matches the backend's `STUB_DEFAULT_USER_OID`, so
locally-created jobs are owned by the same identity the backend expects out of the box.

`VITE_COGNITO_ENABLED=true` mounts a real OIDC client (`react-oidc-context` over
`oidc-client-ts`) against a Cognito user pool. That pool doesn't exist until Phase 3, so
sign-in won't work with the flag on locally. Unlike the MSAL bridge this replaced, the
Cognito path does produce a real `Authorization: Bearer` header — which is exactly what API
Gateway's JWT authorizer will expect, so there's nothing left to fill in once the pool is
provisioned.

## Environment variables

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend base URL (default `http://localhost:3000`) |
| `VITE_COGNITO_ENABLED` | `false` (default) mocks sign-in; `true` mounts a real OIDC client (inert until Phase 3) |
| `VITE_COGNITO_AUTHORITY`, `VITE_COGNITO_CLIENT_ID` | Phase 3 placeholders — unused while `VITE_COGNITO_ENABLED=false` |
| `VITE_STUB_AUTH_HEADER_NAME`, `VITE_STUB_DEFAULT_USER_OID` | Must match the backend's `STUB_AUTH_HEADER_NAME`/`STUB_DEFAULT_USER_OID` |

## Build / typecheck

```bash
npm run build   # tsc -b && vite build
npm run lint     # tsc --noEmit only
```

## Architecture notes

- **Styling**: CSS Modules + `src/styles/tokens.css` (design tokens as CSS custom
  properties, values sourced verbatim from the design handoff). Mobile-first — the app shell
  is width-constrained to a phone column even in a desktop browser (see `#root` in
  `src/styles/global.css`), since this is a phone-app UI, not a responsive marketing site.
- **Two-stage job flow**: capturing a photo only *identifies* the dish — the backend
  auto-saves it to the cookbook at status `Identified` with no recipe. `JobScreen` then shows a
  **Reverse engineer** button, and only that generates the ingredients and method (status
  `Generating` → `Completed`). Recipe generation is the most expensive call in the pipeline, so
  it's opt-in per dish; see `docs/decisions.md`. Both stages share the same full-screen
  `ProcessingOrb` loading view.
- **Real-time seam**: `src/lib/jobs/useJobPolling.ts` polls `GET /api/jobs/{jobId}` today.
  This is the seam Phase 3 swaps for a push subscription (API Gateway WebSockets or AWS IoT Core) — consumers
  (`JobScreen`) don't need to change when that happens. It stops polling on terminal statuses
  (including `Identified`) and exposes `refetch()`, which `JobScreen` calls after pressing
  Reverse engineer to resume polling once the job is back in flight.
- **Camera**: `src/lib/camera/useCamera.ts` uses `getUserMedia` for a live in-app viewfinder
  (per the Capture design), not an OS-camera handoff via `<input capture>`.
- **Cookbook filter chips**: only "All" is functionally wired — the other chips
  (Mains/Sauces/Desserts) have no backing category field on the backend yet
  (the result item's cuisine isn't the same thing), so they render but don't filter. See the
  comment in `src/screens/CookbookScreen.tsx`.
