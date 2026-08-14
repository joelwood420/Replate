# Replate — Backend

Python backend for "Shazam for restaurant dishes", on **AWS Lambda + Step Functions**.

The pipeline is structurally complete and runs locally. Every external integration that
costs money is still stubbed or partial — the vision guess and the recipe generator return
canned data, restaurant lookup is a stub, and embeddings are deterministic hashes rather
than real vectors. Making those real is **Phase 3**; see the root [`CLAUDE.md`](../CLAUDE.md).

> **Ported from Azure on 2026-08-14.** This was Azure Functions + Durable Functions +
> Azure SQL. Nothing had been deployed, so the move cost no data and no downtime. See
> [`docs/decisions.md`](../docs/decisions.md) for the reasoning, and git history before
> `77f091a` for the Azure version.

## Prerequisites

- Python 3.12
- Docker — for LocalStack. **Not needed to run the unit tests**, only for the
  integration suite and `sam local`.
- [AWS SAM CLI](https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html)
  — for running handlers locally. Not needed for `pytest`.

## Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
```

`.env` is read by `python-dotenv` at import time. The defaults in `.env.example` point at
LocalStack and use dummy credentials, so nothing needs filling in to run the test suite.

There is no `local.settings.json` any more, and no CORS block to remember — that was an
Azure Functions host concern. The bucket's CORS rule (which the browser upload does need)
is set by `scripts/bootstrap_local.py`.

## Local services

One container, one endpoint:

```bash
docker compose up -d          # LocalStack: S3, SQS, DynamoDB, Step Functions, SSM
python scripts/bootstrap_local.py   # creates the table, bucket (+CORS) and queue
python db/seed_embeddings.py        # seeds the culinary-technique vectors
```

`bootstrap_local.py` is idempotent — re-run it freely, and after any `docker compose down`.
`AWS_ENDPOINT_URL` in `.env` is the only setting that differs between local and deployed;
it must be **blank** in a real deployment or boto3 will try to reach LocalStack from Lambda.

**Not emulated by LocalStack Community:** Bedrock, Rekognition and Cognito.

- **Bedrock** — leave `BEDROCK_*_MODEL_ID` blank locally. Menu fetch then raises
  `MenuExtractionError`, which the pipeline already degrades on (it becomes the vision-only
  medium-confidence outcome), so the flow still works end to end.
- **Rekognition** — `MODERATION_ENABLED=false` (the default) reports every photo as
  `unchecked` and lets it through, matching the documented fail-open rule. Set it to `true`
  with real AWS credentials to exercise the real thing; it reads straight from S3, so unlike
  the Azure version this actually works against local storage.
- **Cognito** — stays stubbed via `COGNITO_ENABLED=false` and the `X-Debug-User-Oid` header.

## Running the API

```bash
sam local start-api      # once infra/template.yaml exists (Phase 3)
```

Until the SAM template lands in Phase 3 there is no local HTTP server. Handlers can be
driven directly in the meantime:

```bash
python -c "
from triggers import upload_http
import json
print(upload_http.handler({
    'headers': {'X-Debug-User-Oid': '00000000-0000-0000-0000-000000000001'},
    'body': json.dumps({'latitude': 51.5, 'longitude': -0.12}),
}))"
```

## Endpoints

| Method | Route | Handler |
|---|---|---|
| `POST` | `/jobs` | `triggers/upload_http.handler` |
| `POST` | `/jobs/{jobId}/uploaded` | `triggers/job_uploaded_http.handler` |
| `GET` | `/jobs/{jobId}` | `triggers/job_result_http.handler` |
| `GET` | `/jobs` | `triggers/jobs_list_http.handler` |
| `PATCH` | `/jobs/{jobId}/save` | `triggers/job_save_http.handler` |
| `POST` | `/jobs/{jobId}/reverse-engineer` | `triggers/recipe_starter_http.handler` |
| `GET` | `/restaurants/search` | `triggers/restaurant_search_http.handler` |

Plus `triggers/orchestrator_starter_queue.handler`, driven by an SQS event source mapping
rather than HTTP. Full request/response detail is in [`docs/api.md`](../docs/api.md).

Every endpoint takes the caller's id from the `X-Debug-User-Oid` header while
`COGNITO_ENABLED=false`, falling back to `STUB_DEFAULT_USER_OID`.

## The pipeline

Two Step Functions state machines, defined in [`statemachines/`](statemachines/):

- **`dish-identify.asl.json`** — runs automatically on upload. Moderate → (select or
  geocode restaurant → fetch menu) ‖ vision guess → match → persist. Stops at `Identified`.
- **`dish-recipe.asl.json`** — runs only when the user presses "Reverse engineer".
  Retrieve technique embeddings → generate → persist. Ends at `Completed`.

The split exists because generation is the heaviest call in the app and nobody wants to wait
for it at the table. A stage-2 failure reverts to `Identified`, not `Failed`, so a transient
model error never discards a good menu match.

## Testing

```bash
pytest                    # unit tests - no Docker, no credentials, no network
pytest -m integration     # needs `docker compose up -d` first
```

The unit suite uses [moto](https://github.com/getmoto/moto) for in-process DynamoDB, so it
needs nothing running. The integration suite hits LocalStack for real and **skips rather
than fails** when nothing is listening.

## What's real vs. stubbed

| Step | State |
|---|---|
| Upload, presigned URLs, job lifecycle | **Real** |
| Rate limiting (per-user, per-stage, TTL buckets) | **Real** |
| Menu matching (the anti-hallucination check) | **Real** |
| Menu fetch — search → fetch → extract | **Real**, needs `SERP_API_KEY` + a Bedrock model id |
| Image moderation | **Real**, needs `MODERATION_ENABLED=true` + AWS credentials |
| Vector retrieval | Real query, **pseudo-embeddings** (Phase 3: Titan V2) |
| Restaurant lookup from GPS | **Stub** (`CANNED_CANDIDATES`) |
| Vision guess | **Stub** (`CANNED_GUESSES`) |
| Recipe generation | **Stub** |
| Auth | **Stub** (`X-Debug-User-Oid`) |

## Environment variables

Names and defaults live in [`.env.example`](.env.example), grouped by concern. Notes on the
ones that are easy to get wrong:

| Variable | Note |
|---|---|
| `AWS_ENDPOINT_URL` | LocalStack locally. **Must be blank when deployed.** |
| `DDB_TABLE_NAME` | Single table; key layout is documented in `shared/ddb.py` |
| `SQS_QUEUE_URL` | Set from the SAM template. Blank locally — the queue is created by name |
| `MODERATION_ENABLED` | `false` locally. There is no key to omit any more — Rekognition uses IAM |
| `MODERATION_MIN_CONFIDENCE` | 0–100, not Azure's 0/2/4/6. Default 80, deliberately high |
| `BEDROCK_*_MODEL_ID` | No API key. Model access must be granted per-model per-region in the console |
| `SERP_API_KEY` | The only stored credential in the design; everything else is IAM |
| `PAGE_FETCH_MAX_CHARS` | A cost cap — page text goes straight into a model prompt |
| `COGNITO_ENABLED` | `true` raises `NotImplementedError` until Phase 3 |

## Notes for future work

- **`sam build` produces a separate zip per function.** With a dozen handlers sharing one
  `CodeUri`, third-party dependencies belong in a shared `LayerVersion` or numpy gets
  uploaded twelve times. `boto3` is already in the Lambda runtime and must not be vendored.
- **DynamoDB must be provisioned capacity, not on-demand.** The perpetual free tier covers
  25 RCU/WCU; on-demand bills from the first request.
- **Do not put these Lambdas in a VPC.** A NAT Gateway is a fixed hourly charge with no free
  tier, and nothing here needs one.
