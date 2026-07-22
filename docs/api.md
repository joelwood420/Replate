# Replate Backend API (Phase 1)

Local base URL: `http://localhost:7071/api`. Every endpoint below except `/ping` requires an
`X-Debug-User-Oid` header (stand-in for a real Entra ID token until Phase 3) — the backend
scopes every query to that caller's own jobs.

## `GET /ping`

Health check. No auth. Returns `pong`.

## `POST /jobs`

Starts a new scan.

**Body:** `{"latitude": number, "longitude": number}`

**201 response:**
```json
{ "job_id": "...", "upload_url": "...", "blob_url": "..." }
```
`upload_url` is a short-lived, write-only SAS URL. The client `PUT`s the photo bytes
directly to Blob Storage with it (header `x-ms-blob-type: BlockBlob`) — never through the
Function App.

**400** if `latitude`/`longitude` are missing or not numbers.

## `GET /jobs/{jobId}`

Poll a single job's status/result.

**200 response (always):**
```json
{ "job_id": "...", "status": "Queued|Processing|Completed|Failed", "image_url": "...", "is_saved": false, "created_at": "..." }
```
`image_url` is a freshly-minted **read-only** SAS URL, re-signed on every call (the upload
SAS can't be reused for viewing).

- `status: "Failed"` → adds `"error_message"`.
- `status: "Completed"` → adds `"result"`:
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
  against the restaurant's real menu or is vision-only guesswork.

**403** if the job belongs to a different user. **404** if it doesn't exist.

## `GET /jobs`

List the caller's jobs, newest first.

**Query params:** `?saved=true` (filter to saved-only), `?limit=` (default 20).

**200 response:** array of summaries (no ingredients/steps):
```json
[{ "job_id": "...", "status": "...", "is_saved": false, "created_at": "...", "dish_name": "...", "restaurant_name": "...", "image_url": "..." }]
```

## `PATCH /jobs/{jobId}/save`

Toggle saved state.

**Body:** `{"saved": true|false}`

**200 response:** `{ "job_id": "...", "is_saved": true }`

**403/404** same ownership rules as `GET /jobs/{jobId}`.

## Typical flow

1. `POST /jobs` → get `job_id` + `upload_url`.
2. `PUT` the photo to `upload_url`.
3. Poll `GET /jobs/{jobId}` until `status` is terminal.
4. `PATCH /jobs/{jobId}/save` to add/remove from the user's cookbook.
5. `GET /jobs` (optionally `?saved=true`) to populate the Home/Cookbook list screens.

## Local dev CORS

`func start` and Azurite both allow no cross-origin requests by default — required for the
browser-based frontend to reach either. See `backend/README.md` ("CORS" and "Local
services" sections) for the one-time setup.
