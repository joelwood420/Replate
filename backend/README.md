# Replate — Backend

Python backend for "Shazam for restaurant dishes", on **AWS Lambda + Step Functions**.

The pipeline is live in prod with real model calls, and runs locally with no keys at all:
each paid integration falls back to canned data or a cheaper path when its key or model is
blank (see [What's real vs. stubbed](#whats-real-vs-stubbed)). The one stub left in prod is
the technique embeddings, which are deterministic hashes until Phase 6; see the root
[`CLAUDE.md`](../CLAUDE.md).

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
pip install -r requirements-dev.txt
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

**Not local:** the Anthropic API, the TypeSafe API, Rekognition and Cognito.

- **Anthropic API** — model calls go to the first-party Anthropic API (an external HTTPS
  service). Leave `ANTHROPIC_API_KEY` blank locally. The vision guess and recipe generator
  then return canned data, and menu fetch raises `MenuExtractionError`, which the pipeline
  degrades to the vision-only medium-confidence outcome, so the flow still works end to end.
- **SerpApi** - finds the restaurant's menu URL before the page is fetched and extracted.
  Leave `SERPAPI_KEY` blank locally and discovery falls back to the OSM `website` hint.
- **TypeSafe API** - the menu match asks Jev, TypeSafe's decision model, to pick the menu
  item first (docs/decisions.md, 2026-11-21). Leave `TYPESAFE_API_KEY` blank locally and the
  match falls back to the Claude classifier, then difflib, so it still works with no keys.
- **Rekognition** — `MODERATION_ENABLED=false` (the default) reports every photo as
  `unchecked` and lets it through, matching the documented fail-open rule. Set it to `true`
  with real AWS credentials to exercise the real thing; it reads straight from S3, so unlike
  the Azure version this actually works against local storage.
- **Cognito** — stays stubbed via `COGNITO_ENABLED=false` and the `X-Debug-User-Oid` header.

## Running the API

```bash
cd ../infra
sam build --use-container && sam local start-api
```

Or drive a handler directly, with no SAM or Docker:

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

- **`dish-identify.asl.json`** - runs automatically on upload. Moderate → vision guess (the
  food gate: a non-food photo stops here) → select or geocode restaurant → fetch menu →
  match → persist. Stops at `Identified`. The vision guess runs first, not in parallel, so a
  non-food photo never pays for a menu fetch (docs/decisions.md, 2026-09-01).
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

Both suites run in CI on every pull request (`.github/workflows/ci.yml`): `backend-unit`
runs `pytest`, and `backend-integration` starts LocalStack with `docker compose up -d`, waits
for its health endpoint, bootstraps + seeds, then runs `pytest -m integration`. The health
wait is load-bearing: because the integration fixtures *skip* on an unreachable endpoint, CI
blocks until LocalStack is up so the tests genuinely run rather than passing all-skipped.

Two LocalStack details worth knowing (both set in `docker-compose.yml`):

- **The image is pinned to `localstack/localstack:3.8.1`, not `:latest`.** The `:latest` tag
  drifted to a 2026 build that refuses to start without a LocalStack Pro auth token (exit 55).
  3.8.1 is the last-known token-free Community image covering S3/SQS/DynamoDB/Step Functions/SSM.
  Bump it deliberately, checking a new tag still starts token-free.
- **`S3_SKIP_SIGNATURE_VALIDATION=0`** makes LocalStack enforce S3 signatures; without it the
  "upload URL is write-only" security test cannot verify anything (unsigned or wrong-verb GETs
  return 200). One further check, that an anonymous read is denied, is S3 Block Public Access
  behaviour LocalStack Community does not emulate, so `test_the_bucket_is_not_publicly_readable`
  skips against LocalStack and only runs against real S3.

## What's real vs. stubbed

| Step | Prod | Locally, with no keys |
|---|---|---|
| Upload, presigned URLs, job lifecycle | Real | Real (LocalStack) |
| Rate limiting (per-user, per-stage, TTL buckets) | Real | Real (LocalStack) |
| Food pre-check at upload | Real (Rekognition `DetectLabels`) | Skipped |
| Image moderation | Off (`ModerationEnabled=false`) | Off |
| Vision guess + food gate | Real (Claude) | Canned (`CANNED_GUESSES`) |
| Restaurant lookup from GPS | Real (OSM Overpass, Claude `web_search` fallback) | Real (Overpass is key-less) |
| Menu fetch | Real (SerpApi finds the URL, Claude extracts the page) | Degrades to vision-only |
| Menu matching (the anti-hallucination check) | Real (Jev, then Claude, then difflib) | difflib |
| Vector retrieval | Real query, **pseudo-embeddings** (Phase 6) | Same |
| Recipe generation | Real (Claude) | Canned |
| Auth | Real (Cognito JWT, validated by API Gateway) | Stub (`X-Debug-User-Oid`) |

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
| `ANTHROPIC_API_KEY` | The one stored credential the model calls introduce; everything else is IAM. Blank locally |
| `ANTHROPIC_MENU_MODEL` | Only extracts the fetched menu page now (no `web_search`), so it must be vision-capable: menus are often PDFs or images. Default `claude-sonnet-5-5` |
| `SERPAPI_KEY` | Menu-URL discovery. Blank locally falls back to the OSM `website` hint |
| `TYPESAFE_API_KEY` | Key for Jev, the menu-match decision model. Blank locally skips Jev; the Claude classifier (then difflib) matches instead |
| `TYPESAFE_MATCH_MODEL` | Pinned (`jev-1.14.0`), not `jev-latest`, because `MENU_MATCH_CONFIDENCE_THRESHOLD` is tuned against one version's probabilities |
| `COGNITO_ENABLED` | `true` in prod: API Gateway validates the JWT and handlers read `sub` from its claims. `false` locally uses `X-Debug-User-Oid` |

## Notes for future work

- **`sam build` produces a separate zip per function.** With a dozen handlers sharing one
  `CodeUri`, third-party dependencies belong in a shared `LayerVersion` or numpy gets
  uploaded twelve times. `boto3` is already in the Lambda runtime and must not be vendored.
- **DynamoDB must be provisioned capacity, not on-demand.** The perpetual free tier covers
  25 RCU/WCU; on-demand bills from the first request.
- **Do not put these Lambdas in a VPC.** A NAT Gateway is a fixed hourly charge with no free
  tier, and nothing here needs one.
