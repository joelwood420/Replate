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
| [`backend/`](backend/README.md) | Azure Functions (Python, Durable Functions) — run it locally with `func start` |
| [`frontend/`](frontend/README.md) | React (Vite + TypeScript), mobile-first — `npm run dev` |
| [`infra/`](infra/README.md) | Bicep for the production environment (written, not yet deployed) |
| [`docs/`](docs/) | [API reference](docs/api.md), [architecture](docs/architecture.md), [user flow](docs/user-flow.md), and the [decision log](docs/decisions.md) |
| [`CLAUDE.md`](CLAUDE.md) | Project rules and the phase-by-phase build plan |
