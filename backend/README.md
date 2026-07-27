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

**CORS (required for the Phase 2 frontend):** `func start` does not allow any browser
origin by default — the frontend's `fetch()` calls will be blocked by the browser even
though `curl`/Postman work fine, since CORS is enforced client-side, not something a plain
HTTP test can catch. Add a `Host` block to `local.settings.json`:

```json
{
  "IsEncrypted": false,
  "Values": { "...": "..." },
  "Host": {
    "CORS": "*"
  }
}
```

`"*"` is fine for local dev since this app doesn't use cookie-based auth (no
`CORSCredentials` needed). Restart `func start` after adding it.

## Local services

**Azurite** (Blob + Queue + Table emulator):

```bash
docker compose up -d azurite
# or: npm install -g azurite && azurite --location azurite --skipApiVersionCheck
python scripts/configure_azurite_cors.py   # required once per fresh Azurite volume - see below
```

Azurite has no CORS rules by default, so the frontend's photo upload (a browser `fetch` PUT
straight to a SAS blob URL, i.e. a different origin than the Functions host) gets blocked
with `CorsPreflightFailure` until `scripts/configure_azurite_cors.py` has been run once
against it. This is a runtime blob-service property Azurite persists in its data volume, so
you only need to re-run it if the `azurite-data` volume is ever wiped (`docker compose down
-v`, or deleting the `azurite/` folder if running the npm package instead of the container).

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

- `POST /api/jobs` — upload metadata + GPS **or** a manually-selected restaurant, returns a
  Blob SAS URL + job ID, queues the job
- `GET /api/jobs/{jobId}` — job status/result (includes a readable `image_url` and `is_saved`)
- `GET /api/jobs` — list the caller's jobs, newest first (`?saved=true` to filter, `?limit=`)
- `PATCH /api/jobs/{jobId}/save` — body `{"saved": true|false}`, toggles a job's saved state
- `GET /api/restaurants/search?query=...&latitude=&longitude=` — real Google Places text
  search (`latitude`/`longitude` are an optional ranking bias, not a hard filter). Used by
  the frontend's manual restaurant-search flow when an uploaded photo has no EXIF GPS.

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

**Restaurant search + manual selection** (the fallback path when an uploaded photo has no
EXIF GPS):

```bash
curl "http://localhost:7071/api/restaurants/search?query=Luigis&latitude=40.7128&longitude=-74.0060" \
  -H "X-Debug-User-Oid: 11111111-1111-1111-1111-111111111111"

curl -X POST http://localhost:7071/api/jobs \
  -H "Content-Type: application/json" \
  -H "X-Debug-User-Oid: 11111111-1111-1111-1111-111111111111" \
  -d '{"selected_restaurant": {"place_id": "ChIJ...", "name": "Luigi'"'"'s", "address": "123 Main St", "latitude": 40.7128, "longitude": -74.0060}}'
```

### Resolved: the queue trigger not firing against Azurite

Earlier in Phase 1 build-out, `orchestrator_starter_queue` appeared not to fire against
Azurite — messages got dequeued and immediately poisoned (`MaxDequeueCount` reached) without
ever reaching the Python worker, even though a minimal bare queue trigger with zero business
logic failed identically and HTTP-triggered Durable orchestration always worked fine. This
was suspected to be an Azurite/Core Tools compatibility issue, but the actual root cause was
simpler: the Storage Queues extension bundled in extension bundle `4.*` defaults to expecting
**base64-encoded** message bodies, while `shared/queue.py`'s `send_job_message` (via
`azure-storage-queue`'s `send_message()`) sends plain UTF-8 JSON. The runtime's failed
base64-decode threw during binding resolution — before the function code ever ran — which is
exactly the "dequeued, poisoned, worker never invoked" signature, and why a from-scratch
minimal repro hit the same wall (it also sent unencoded text).

Fix: `host.json` now sets `"extensions.queues.messageEncoding": "none"` to match the plain
JSON the queue producer actually sends. Verified end-to-end locally — `POST /api/jobs`
progresses through `orchestrator_starter_queue` → `dish_orchestrator_trigger` → all activities
→ `Completed` on the first dequeue attempt, no poisoning.

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
| `GOOGLE_PLACES_API_KEY`, `PLACES_TIMEOUT_SECONDS` | Real — powers `GET /api/restaurants/search` (Google Places Text Search) |
| `ANTHROPIC_API_KEY`, `MENU_FETCH_MODEL`, `MENU_FETCH_TIMEOUT_SECONDS`, `MENU_FETCH_MAX_RETRIES` | Real — powers `fetch_restaurant_menu`'s Claude + web-search call. `MENU_FETCH_MODEL` defaults to `claude-sonnet-5`, not the API-wide default, per this project's cost-discipline rule for a repeated, cache-gated extraction task — see `docs/decisions.md` |
| `CLAUDE_BASE_URL`, `VISION_MODEL_DEPLOYMENT` | **Phase 3** — Microsoft Foundry endpoint and Claude deployment name. Set by `infra/`; not read by any code yet. Note that on Foundry the `model` parameter must be a *deployment name*, not a model id |
| `AZURE_OPENAI_ENDPOINT`, `EMBEDDING_DEPLOYMENT_NAME` | **Phase 3** — Azure OpenAI `text-embedding-3-small` (1536-dim, matching `CulinaryEmbeddings`). Set by `infra/`; not read by any code yet |
| `CONTENT_SAFETY_ENDPOINT`, `CONTENT_SAFETY_KEY` | **Phase 3** — image moderation. Set by `infra/`; not read by any code yet |
| `ENTRA_TENANT_ID`, `ENTRA_API_CLIENT_ID`, `ENTRA_AUTHORITY_URL`, `ENTRA_JWKS_URI` | **Phase 3 placeholders** — names only, not read by any Phase 1 code. `ENTRA_API_CLIENT_ID` is the **API** app registration (the token audience), *not* the SPA client ID the frontend uses as `VITE_ENTRA_CLIENT_ID` |
| `YELP_API_KEY` | Unused placeholder for a possible Yelp Fusion fallback |

## Architecture: what's real vs. stubbed

The orchestrator (`orchestrators/dish_orchestrator.py`) models a dependency chain, not flat
fan-out: vision analysis runs concurrently with the geocode→menu-fetch chain, then both join
at the menu-matching fan-in step. A job either arrives with GPS coordinates (device or photo
EXIF) or with a manually-selected restaurant (`Jobs.SelectedRestaurantId`, set when an
uploaded photo has no EXIF GPS); the orchestrator branches to `geocode_restaurant_candidates`
or `select_restaurant_candidate` accordingly, but the two activities return an identical
shape so everything downstream is unaffected by which path a job took.

| Activity | Real | Stubbed |
|---|---|---|
| `geocode_restaurant_candidates` | Writes to `JobRestaurantCandidates` | Candidate lookup (canned list) — GPS reverse-geocode stays stubbed this pass |
| `select_restaurant_candidate` | Fully real — loads the manually-selected `Restaurants` row, writes `JobRestaurantCandidates` | — |
| `fetch_restaurant_menu` | Fully real — Claude API + native web-search tool, cache check via `MenuLastFetchedAt`, upserts `Restaurants`/`MenuItems`. On extraction failure, degrades to an empty menu (`source: "fetch_failed"`) rather than failing the job | — |
| `vision_guess` | — | Entirely stub |
| `match_menu_item` | Real `difflib`-based matching → one of 3 confidence outcomes | — (this is the anti-hallucination mechanism, never skipped) |
| `query_culinary_embeddings` | Real `VECTOR_DISTANCE` SQL query | Query-text → pseudo-embedding (deterministic hash, not a real embedding call) |
| `generate_recreation` | — | Entirely stub, output shaped for `DishElements`/`ElementIngredients`/`ElementSteps` |
| `persist_job_result` | Real DB writes | — |

Everything under "Stubbed" is where Phase 3 plugs in a real API call — the interfaces and
data shapes are already correct.
