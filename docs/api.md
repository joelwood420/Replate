# Replate Backend API (Phase 1)

Local base URL: `http://localhost:7071/api`. Every endpoint below except `/ping` requires an
`X-Debug-User-Oid` header (stand-in for a real Entra ID token until Phase 3) — the backend
scopes every query to that caller's own jobs.

## `GET /ping`

Health check. No auth. Returns `pong`.

## `POST /jobs`

Starts a new scan (stage 1).

**Body:** exactly one of the two location sources —

```json
{ "latitude": number, "longitude": number }
```
Device location for a live capture, or the photo's EXIF coordinates for an upload.

```json
{ "selected_restaurant": { "place_id": "...", "name": "...", "address": "...", "latitude": number, "longitude": number } }
```
Used when an uploaded photo has no EXIF GPS and the user picked a restaurant by name via
`GET /restaurants/search`.

**201 response:**
```json
{ "job_id": "...", "upload_url": "...", "blob_url": "..." }
```
`upload_url` is a short-lived, write-only SAS URL. The client `PUT`s the photo bytes
directly to Blob Storage with it (header `x-ms-blob-type: BlockBlob`) — never through the
Function App.

**400** if `latitude`/`longitude` are missing or not numbers, if `selected_restaurant` is
missing a required field, or if both location sources (or neither) are supplied.

## `GET /jobs/{jobId}`

Poll a single job's status/result.

**200 response (always):**
```json
{ "job_id": "...", "status": "Queued|Processing|Identified|Generating|Completed|Failed", "image_url": "...", "is_saved": false, "created_at": "..." }
```
`image_url` is a freshly-minted **read-only** SAS URL, re-signed on every call (the upload
SAS can't be reused for viewing).

The pipeline runs in two stages, and `status` says which one a job is in:

| Status | Meaning |
|---|---|
| `Queued` | Job created, waiting to be picked up. |
| `Processing` | Stage 1 running — identifying the restaurant, fetching its menu, analysing the photo, matching. |
| `Identified` | **Stage 1 done.** The dish is in the user's cookbook with a matched restaurant and menu item, but has no recipe yet. This is a terminal state until the user asks for one. |
| `Generating` | Stage 2 running — the user pressed "Reverse engineer". |
| `Completed` | Recipe generated. `result.elements` is populated. |
| `Failed` | Stage 1 failed. A **stage 2** failure reverts to `Identified` instead, keeping the dish usable and the action retryable. |

- `"error_message"` is present whenever the job has one. On a `Failed` job that's why it
  failed; on an `Identified` job it means a previous reverse-engineer attempt failed and can
  be retried.
- `"result"` is present from `Identified` onward — **not** only when `Completed` — so the
  client can show the dish, restaurant and confidence badge before any recipe exists.
  `result.elements` is an empty array until stage 2 has run.
  ```json
  {
    "dish_name": "...", "cuisine": "...", "confidence": 0.8,
    "matched_restaurant_id": "...", "restaurant_name": "...",
    "matched_menu_item_id": "...", "match_confidence": 0.9,
    "match_method": "menu_matched | vision_only_medium | vision_only_low",
    "elements": [
      { "name": "...", "description": "...", "role": "Protein",
        "ingredients": [{ "ingredient_name": "...", "amount": "...", "unit": "..." }],
        "steps": [{ "step_number": 1, "instruction": "..." }] }
    ]
  }
  ```
  `match_method` is the anti-hallucination signal — whether the dish was cross-checked
  against the restaurant's real menu or is vision-only guesswork. It is available at
  `Identified`, i.e. before any recipe has been generated.

**403** if the job belongs to a different user. **404** if it doesn't exist.

## `POST /jobs/{jobId}/reverse-engineer`

Starts stage 2 — generating the per-component ingredients and method for a dish that has
already been identified. This is the expensive half of the pipeline, so it only ever runs on
explicit request (see `docs/decisions.md`).

No body.

**202 response:** `{ "job_id": "...", "status": "Generating" }`

Returns as soon as the orchestration is queued. Poll `GET /jobs/{jobId}` to watch it move
`Generating` → `Completed`.

**409** if the job isn't in the `Identified` state — covers "stage 1 hasn't finished",
"generation already in flight" and "this dish already has a recipe" in one check. Also
returned for jobs created before the pipeline was split, which have no stored vision
analysis to generate from.

**403/404** same ownership rules as `GET /jobs/{jobId}`.

## `GET /jobs`

List the caller's jobs, newest first.

**Query params:** `?saved=true` (filter to saved-only), `?limit=` (default 20).

**200 response:** array of summaries (no ingredients/steps):
```json
[{ "job_id": "...", "status": "...", "is_saved": false, "created_at": "...", "dish_name": "...", "restaurant_name": "...", "image_url": "..." }]
```

## `PATCH /jobs/{jobId}/save`

Set saved state. Jobs are saved into the cookbook **automatically** when stage 1 completes,
so this is now mainly how a user removes one.

**Body:** `{"saved": true|false}`

**200 response:** `{ "job_id": "...", "is_saved": true }`

**403/404** same ownership rules as `GET /jobs/{jobId}`.

## `GET /restaurants/search`

Restaurant name typeahead, backing the manual-selection flow shown when an uploaded photo has
no EXIF GPS. Real Google Places Text Search, called server-side so the client never holds the
Places API key.

**Query params:** `query` (required), `latitude`/`longitude` (optional). The coordinates only
*bias result ranking* — they are not a hard filter, and never become the job's location.

**200 response:**
```json
{ "restaurants": [{ "place_id": "...", "name": "...", "address": "...", "latitude": 0, "longitude": 0 }] }
```
A `place_id` from here is what goes into `POST /jobs`'s `selected_restaurant`.

**400** if `query` is missing or blank. **502** if the Places API is unreachable.

## Typical flow

Stage 1 — automatic, on upload:

1. `POST /jobs` → get `job_id` + `upload_url`.
2. `PUT` the photo to `upload_url`.
3. Poll `GET /jobs/{jobId}` until `status` is `Identified` (or `Failed`). The job is now in
   the user's cookbook with `is_saved: true` — no save call needed.

Stage 2 — only when the user asks for the recipe:

4. `POST /jobs/{jobId}/reverse-engineer` → `202`, status becomes `Generating`.
5. Resume polling `GET /jobs/{jobId}` until `Completed`, then read `result.elements`.

Either way:

6. `GET /jobs` (optionally `?saved=true`) to populate the Home/Cookbook list screens. The
   summary's `status` distinguishes dishes that still need reverse-engineering.
7. `PATCH /jobs/{jobId}/save` with `{"saved": false}` to remove one from the cookbook.

## Local dev CORS

`func start` and Azurite both allow no cross-origin requests by default — required for the
browser-based frontend to reach either. See `backend/README.md` ("CORS" and "Local
services" sections) for the one-time setup.
