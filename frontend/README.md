# Replate — Frontend (Phase 2)

React (Vite + TypeScript) mobile-first frontend for Replate. This is the **Phase 2** scope
from the root [`CLAUDE.md`](../CLAUDE.md): a working UI wired against the Phase 1 backend's
real API contract, with Entra ID sign-in mocked locally since no real tenant exists yet.

## Setup

```bash
cd frontend
npm install
cp .env.example .env
```

The backend must be running locally for any of this to talk to real data — see
[`../backend/README.md`](../backend/README.md) (`docker compose up -d`, `func start`).

## Run

```bash
npm run dev
```

Opens on `http://localhost:5173` by default. Sign in with the mocked "Sign in with
Microsoft" button (see Auth below) to reach Home.

## Auth (mocked locally)

`VITE_ENTRAID_ENABLED=false` (default) makes Sign In an instant local mock — no real
Microsoft account needed. The mock user's `oid` matches the backend's
`STUB_DEFAULT_USER_OID`, so locally-created jobs are owned by the same identity the backend
expects out of the box. `VITE_ENTRAID_ENABLED=true` mounts a real MSAL provider, but it's
inert until Phase 3 provisions an actual Entra tenant — don't expect sign-in to work with it
on locally.

## Environment variables

| Variable | Purpose |
|---|---|
| `VITE_API_BASE_URL` | Backend base URL (default `http://localhost:7071/api`) |
| `VITE_ENTRAID_ENABLED` | `false` (default) mocks sign-in; `true` mounts real MSAL (inert until Phase 3) |
| `VITE_ENTRA_CLIENT_ID`, `VITE_ENTRA_AUTHORITY_URL` | Phase 3 placeholders — unused while `VITE_ENTRAID_ENABLED=false` |
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
- **Real-time seam**: `src/lib/jobs/useJobPolling.ts` polls `GET /api/jobs/{jobId}` today.
  This is the seam Phase 3 swaps for a SignalR/Web PubSub subscription — consumers
  (`JobScreen`) don't need to change when that happens.
- **Camera**: `src/lib/camera/useCamera.ts` uses `getUserMedia` for a live in-app viewfinder
  (per the Capture design), not an OS-camera handoff via `<input capture>`.
- **Cookbook filter chips**: only "All" is functionally wired — the other chips
  (Mains/Sauces/Desserts) have no backing category field on the backend yet
  (`JobResults.Cuisine` isn't the same thing), so they render but don't filter. See the
  comment in `src/screens/CookbookScreen.tsx`.
