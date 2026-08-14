# Replate

The idea behind this app is that when a user is at a restaurant they would be able to take a
photo of their meal, AI would analyze the photo and essentially give you back the full method to
make each element on the dish and recreate it at home. Essentially a Shazam for restaurant
dishes.

It works in two steps, on purpose. Snapping the photo **identifies** the dish — it finds the
restaurant from your location, fetches that restaurant's real menu, and matches the photo
against it (this match is what keeps the AI honest). The dish is saved straight to your
cookbook. Then, whenever you actually want to cook it, you open it and hit **Reverse engineer**
to get the per-component ingredients and method. Generating that recipe is the slow, expensive
part, and nobody needs it while they're still sitting at the table.

## Where things are

| | |
|---|---|
| [`backend/`](backend/README.md) | Python on AWS Lambda + Step Functions — run it locally against LocalStack |
| [`frontend/`](frontend/README.md) | React (Vite + TypeScript), mobile-first — `npm run dev` |
| [`infra/`](infra/README.md) | AWS SAM template for the production environment (Phase 3, not written yet) |
| [`docs/`](docs/) | [API reference](docs/api.md), [architecture](docs/architecture.md), [user flow](docs/user-flow.md), and the [decision log](docs/decisions.md) |
| [`CLAUDE.md`](CLAUDE.md) | Project rules and the phase-by-phase build plan |

> **On AWS since 2026-08-14.** Replate was originally built on Azure and was ported before
> anything had been deployed, so the move cost no data and no downtime. See
> [`docs/decisions.md`](docs/decisions.md) for the reasoning, and the git history before
> `77f091a` for the Azure version.
