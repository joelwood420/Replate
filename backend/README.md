# Replate — Backend (Phase 1)

Azure Functions (Python, Durable Functions) backend for "Shazam for restaurant dishes."
This is the **Phase 1** scope from the root [`CLAUDE.md`](../CLAUDE.md): a locally-runnable
pipeline with every external integration (restaurant lookup, menu scraping, vision model,
embeddings) stubbed but structurally correct, so Phase 3 can swap in real API calls without
reshaping anything. No real Azure resources, no auth, no CI in this phase.

## Prerequisites

- Python 3.12
- [Azure Functions Core Tools v4](https://learn.microsoft.com/azure/azure-functions/functions-run-local) (`func`)
- ODBC Driver 18 for SQL Server
- Docker (optional — only needed if you don't already have a local SQL Server / Azurite)

## Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env   # fill in SQL_UID/SQL_PWD; mirror values into local.settings.json too
```

`local.settings.json` (gitignored) is what the Functions host actually reads at runtime —
keep it in sync with `.env` manually. `.env` is used by anything run directly with `python`
(seed script, pytest integration tests) outside the Functions host.

## Local services

**Azurite** (Blob + Queue + Table emulator):

```bash
docker compose up -d azurite
# or: npm install -g azurite && azurite --location azurite --skipApiVersionCheck
```

`--skipApiVersionCheck` is required — newer `azure-storage-blob`/`azure-storage-queue` SDK
versions send API versions Azurite may not recognize yet otherwise.

**SQL Server 2025** (needed for the `VECTOR` column type):

This user's environment already has a **native SQL Server 2025** install on `localhost:1433`
— point `.env`/`local.settings.json` at it directly, no container needed. If you don't have
one, run the bundled container instead:

```bash
docker compose up -d sqlserver   # only if you don't already have a local SQL Server 2025
```

(Don't run both at once — they'll fight over port 1433.)

**Apply schema + seed embeddings:**

```bash
# Apply db/schema.sql via sqlcmd, Azure Data Studio, or the VS Code mssql extension
python db/seed_embeddings.py
```

## Run the Function App

```bash
func start
```

Exposed endpoints:

- `POST /api/jobs` — upload metadata + GPS, returns a Blob SAS URL + job ID, queues the job
- `GET /api/jobs/{jobId}` — job status/result

Phase 1 has no real auth — endpoints read a stub user ID from the `X-Debug-User-Oid` header
(configurable via `STUB_AUTH_HEADER_NAME`), falling back to `STUB_DEFAULT_USER_OID`. This is
controlled by `ENTRAID_ENABLED` (default `false`); flipping it to `true` raises
`NotImplementedError` today — that's the seam Phase 3 plugs real Entra ID JWT validation
into once the frontend and a real tenant exist:

```bash
curl -X POST http://localhost:7071/api/jobs \
  -H "Content-Type: application/json" \
  -H "X-Debug-User-Oid: 11111111-1111-1111-1111-111111111111" \
  -d '{"latitude": 40.7128, "longitude": -74.0060}'

curl http://localhost:7071/api/jobs/{jobId} -H "X-Debug-User-Oid: 11111111-1111-1111-1111-111111111111"
```

### Known local limitation: the queue trigger

In this dev environment, `orchestrator_starter_queue` (the queue-triggered function that
starts the Durable orchestration once a job is queued) does not reliably fire against
Azurite — messages get dequeued and immediately poisoned (`MaxDequeueCount` reached) without
ever reaching the Python worker. This was root-caused during Phase 1 build-out to be an
Azurite/Azure Functions Core Tools compatibility issue local to this machine (confirmed via:
a minimal bare queue trigger with zero business logic fails identically; the same failure
persists across two different Azurite versions and fully wiped/fresh state; meanwhile
HTTP-triggered Durable orchestration starts and completes correctly every time) — **not** a
bug in `orchestrator_starter_queue`'s own logic, which is unit-tested independently
(`tests/unit/test_orchestrator_starter_queue.py`) and was manually verified end-to-end by
directly invoking its `build_orchestration_input()` + `client.start_new()` code path.

If you hit this: `POST /api/jobs` and `GET /api/jobs/{jobId}` will keep working, but the job
will stay stuck at `"status": "Queued"` instead of progressing to `"Processing"`/`"Completed"`.
Re-test this specific path once deployed to real Azure Storage in Phase 3 — this class of
local-emulator bug is not expected to reproduce there.

If Azurite starts returning `500 EBADF: bad file descriptor` on blob writes (a separate,
known Windows-specific Azurite bug in its extent-file cache), stop it, delete the
`azurite/` data directory contents, and restart — that clears its corrupted file-descriptor
cache.

## Run tests

```bash
pytest                  # unit tests only - no services required, all external calls mocked
pytest -m integration   # integration tests - requires Azurite + SQL Server running
```

## Environment variables

| Variable | Purpose |
|---|---|
| `SQL_SERVER`, `SQL_DATABASE`, `SQL_UID`, `SQL_PWD`, `SQL_ODBC_DRIVER` | SQL Server connection |
| `AzureWebJobsStorage` | Blob/Queue/Table connection string (Azurite locally) |
| `BLOB_CONTAINER_UPLOADS`, `QUEUE_NAME_JOBS` | Storage resource names |
| `SAS_TOKEN_EXPIRY_MINUTES` | Upload SAS URL lifetime |
| `MENU_CACHE_TTL_HOURS` | How long a scraped menu is considered fresh before re-fetching |
| `MENU_MATCH_CONFIDENCE_THRESHOLD` | Minimum similarity score to count as a menu-item match |
| `VECTOR_SEARCH_TOP_K` | Default number of culinary-technique embeddings to retrieve |
| `STUB_AUTH_HEADER_NAME`, `STUB_DEFAULT_USER_OID` | Phase 1 stub-auth config (see above) |
| `ENTRAID_ENABLED` | `false` (default) uses stub auth; `true` raises `NotImplementedError` until Phase 3 wires real Entra ID JWT validation in |
| `GOOGLE_PLACES_API_KEY`, `YELP_API_KEY`, `VISION_MODEL_API_KEY`, `EMBEDDING_MODEL_API_KEY` | **Phase 3 placeholders** — names only, not read by any Phase 1 code |
| `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, `ENTRA_AUTHORITY_URL`, `ENTRA_JWKS_URI` | **Phase 3 placeholders** — names only, not read by any Phase 1 code |

## Architecture: what's real vs. stubbed

The orchestrator (`orchestrators/dish_orchestrator.py`) models a dependency chain, not flat
fan-out: vision analysis runs concurrently with the geocode→menu-fetch chain, then both join
at the menu-matching fan-in step.

| Activity | Real | Stubbed |
|---|---|---|
| `geocode_restaurant_candidates` | Writes to `JobRestaurantCandidates` | Candidate lookup (canned list) |
| `fetch_restaurant_menu` | Cache check via `MenuLastFetchedAt`, upserts `Restaurants`/`MenuItems` | Fetch content |
| `vision_guess` | — | Entirely stub |
| `match_menu_item` | Real `difflib`-based matching → one of 3 confidence outcomes | — (this is the anti-hallucination mechanism, never skipped) |
| `query_culinary_embeddings` | Real `VECTOR_DISTANCE` SQL query | Query-text → pseudo-embedding (deterministic hash, not a real embedding call) |
| `generate_recreation` | — | Entirely stub, output shaped for `DishElements`/`ElementIngredients`/`ElementSteps` |
| `persist_job_result` | Real DB writes | — |

Everything under "Stubbed" is where Phase 3 plugs in a real API call — the interfaces and
data shapes are already correct.
