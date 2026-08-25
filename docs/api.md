# Replate Backend API (Phase 1)

Local base URL: `http://localhost:7071/api`. Every endpoint below except `/ping` requires an
`X-Debug-User-Oid` header (stand-in for a real Entra ID token until Phase 3) — the backend
scopes every query to that caller's own jobs.

## `GET /ping`

Health check. No auth. Returns `pong`.

## `POST /jobs`

Reserves an upload slot and creates the job row. **This does not start the pipeline** —
`POST /jobs/{jobId}/uploaded` does, once the photo is actually in Blob Storage.

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
{ "job_id": "...", "upload_url": "...", "image_key": "..." }
```
`upload_url` is a short-lived, write-only **presigned S3 URL**. The client `PUT`s the photo
bytes directly to S3 with it — never through the backend. No special headers are required.

`image_key` is the S3 object key the job was created against (`uploads/<uuid>.jpg`). It is
returned for traceability; the client does not need to send it back.

**400** if `latitude`/`longitude` are missing or not numbers, if `selected_restaurant` is
missing a required field, or if both location sources (or neither) are supplied.

**429** if the caller's scan quota is spent — see [Rate limits](#rate-limits). No job row is
created.

## `POST /jobs/{jobId}/uploaded`

Signals that the `PUT` to `upload_url` finished. **This is what starts stage 1.**

It exists because `POST /jobs` cannot start the pipeline itself: the client only uploads the
photo after that call returns the SAS URL, so enqueuing there raced the upload and the
orchestrator could try to read the blob before it existed.

No body.

**202 response:** `{ "job_id": "...", "status": "Queued" }`

**409** if the job is past `Queued` — its photo was already submitted. Makes the call safe to
retry.

**403/404** same ownership rules as `GET /jobs/{jobId}`.

A job whose client never calls this simply stays `Queued` forever and costs nothing.

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

**429** if the caller's recipe-generation quota is spent — see [Rate limits](#rate-limits).
The job stays `Identified`, so it can be retried once the window reopens.

**403/404** same ownership rules as `GET /jobs/{jobId}`.

## `POST /jobs/{jobId}/cancel`

Abort an in-flight scan (stage 1). Stops the identify state-machine execution so no further
model spend accrues, and moves the job to `Cancelled` — a normal terminal state kept distinct
from `Failed`. A job cancelled while still `Queued` is also caught by the SQS starter, which
skips a `Cancelled` job rather than starting it.

No body.

**200 response:** `{ "job_id": "...", "status": "Cancelled" }`

**409** if the job isn't `Queued` or `Processing` — there is no scan in flight to cancel
(recipe generation is not cancellable through this endpoint).

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

## `GET /profile`

The caller's profile. Created lazily on first read, so a brand-new user gets an item with
null `display_name`/`email`.

**200 response:**
```json
{ "display_name": "Amara Silva", "email": "amara@example.com", "created_at": "..." }
```

## `PUT /profile`

Update the caller's display name. `email` is the sign-in identity and is not editable here;
profile photo is not yet supported.

**Body:** `{"display_name": "Amara Silva"}`

**200 response:** the updated profile, same shape as `GET /profile`.

**400** if `display_name` is missing, blank after trimming, or longer than 80 characters.

## `GET /restaurants/search`

Restaurant name typeahead, backing the manual-selection flow shown when an uploaded photo has
no EXIF GPS. Backed by OpenStreetMap Nominatim, called server-side. No API key is required.

**Query params:** `query` (required), `latitude`/`longitude` (optional). The coordinates only
*bias result ranking* — they are not a hard filter, and never become the job's location.

**200 response:**
```json
{ "restaurants": [{ "place_id": "...", "name": "...", "address": "...", "latitude": 0, "longitude": 0 }] }
```
A `place_id` from here is what goes into `POST /jobs`'s `selected_restaurant`.

**400** if `query` is missing or blank. **502** if the Nominatim service is unreachable.

## Rate limits

Per-user quotas cap AI spend from any single account. The two pipeline stages are counted
**separately**, because scanning happens automatically on every photo while recipe generation
is a deliberate button press and the most expensive call in the app.

| Action | Endpoint | Default per hour | Default per day |
|---|---|---|---|
| `scan` | `POST /jobs` | 10 | 30 |
| `recipe` | `POST /jobs/{jobId}/reverse-engineer` | 5 | 15 |

Both defaults are app settings (`SCAN_RATE_LIMIT_PER_HOUR` and friends — see
`backend/.env.example`), and `RATE_LIMIT_ENABLED=false` turns quotas off for local dev.

A throttled call returns **429** with a `Retry-After` header and:

```json
{ "error": "You have used all 10 scans allowed per hour. Try again in 23 minutes.", "retry_after_seconds": 1380 }
```

The daily window slides at hour resolution rather than resetting at midnight, so capacity
returns gradually. A rejected request consumes nothing — neither a 429 nor a 403/404/409 —
so retrying into a closed window can't push the reset further out.

## Image moderation

Uploaded photos go through Azure AI Content Safety as the very first step of stage 1, before
any AI call is made, so a rejected image costs one moderation call and nothing else. A
rejected photo lands in `Failed` with an `error_message` naming the categories.

If the check itself can't complete — service error, timeout, or the free tier's monthly
allowance exhausted — the scan **proceeds** and a warning is logged. "This image is unsafe"
and "I couldn't check this image" are treated as different answers on purpose; see
`docs/decisions.md`.

## Typical flow

Stage 1 — automatic, on upload:

1. `POST /jobs` → get `job_id` + `upload_url`.
2. `PUT` the photo to `upload_url`.
3. `POST /jobs/{jobId}/uploaded` → the pipeline starts.
4. Poll `GET /jobs/{jobId}` until `status` is `Identified` (or `Failed`). The job is now in
   the user's cookbook with `is_saved: true` — no save call needed.

Stage 2 — only when the user asks for the recipe:

5. `POST /jobs/{jobId}/reverse-engineer` → `202`, status becomes `Generating`.
6. Resume polling `GET /jobs/{jobId}` until `Completed`, then read `result.elements`.

Either way:

7. `GET /jobs` (optionally `?saved=true`) to populate the Home/Cookbook list screens. The
   summary's `status` distinguishes dishes that still need reverse-engineering.
8. `PATCH /jobs/{jobId}/save` with `{"saved": false}` to remove one from the cookbook.

## Local dev CORS

`func start` and Azurite both allow no cross-origin requests by default — required for the
browser-based frontend to reach either. See `backend/README.md` ("CORS" and "Local
services" sections) for the one-time setup.
