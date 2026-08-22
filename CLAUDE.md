# CLAUDE.md

Project instructions for Claude Code working in this repo, for **Replate**.

## Project overview

Replate — "Shazam for restaurant dishes." A user at a restaurant takes a photo of their meal + shares
GPS location → the app identifies the restaurant from GPS, finds/scrapes that restaurant's
actual menu, analyzes the photo with a vision model, **matches the vision model's guess
against the real menu** (this match is the primary anti-hallucination mechanism — a menu
item's real name/description is trusted over the vision model's unaided guess), then
generates a full, reproducible **method to recreate each element of the dish at home**
(not just "what is this dish" — a per-component ingredient list + step-by-step technique).
Result is returned to the client (polled today; a real-time channel is a future option).

Pipeline is a dependency chain, not just parallel fan-out:
`GPS → nearby restaurant candidates → fetch/scrape that restaurant's menu` runs alongside
`photo → vision model's preliminary dish/element guess`, then both feed into a
`match guess against real menu items` step, then a `generate per-element recipe` step
that also grounds itself against culinary technique/recipe embeddings.

**Stack**
- Frontend: React (Vite + TypeScript)
- Backend: Python on **AWS Lambda**, with **AWS Step Functions** (Standard workflows) for
  orchestration
- Database: **Amazon DynamoDB**, single-table design. Culinary-technique embeddings live in
  the same table and are scanned brute-force in the Lambda — no separate vector database
- Auth: **Amazon Cognito** user pool
- AI: **first-party Anthropic API** (Claude for vision/menu/generation, incl. the server-side
  `web_search` tool for menu fetch). Embeddings are a pseudo-embedding stub — no provider yet
  (Anthropic has no embeddings endpoint). See `docs/decisions.md` (2026-08-17).
- Infra: **AWS SAM** (a CloudFormation transform — the deployed artifact is a CloudFormation
  stack)
- CI/CD: GitHub Actions

> **This project moved from Azure to AWS on 2026-08-14.** Phases 1 and 2 were originally
> built on Azure Functions + Azure SQL and have since been ported to AWS (Phase 0). Phases 0
> through 4 are done; **Phase 5 (unit + e2e testing in CI/CD) is the current phase.** `docs/decisions.md` records the
> migration and its reasoning; the pre-migration Bicep is recoverable from git history at
> commit `07354af`.

## Global rules (apply in every phase)

1. **AWS cost discipline.** Before adding or provisioning any AWS resource, check whether it
   has a free tier / free monthly grant, **and whether that grant is always-free or expires
   after 12 months** — this distinction matters more on AWS than it did on Azure. Call out
   (in the PR description or commit message) what happens once the free tier is exceeded.
   Prefer serverless / per-request pricing over anything with a fixed hourly cost. If a
   resource has no free tier and no per-request option (e.g. OpenSearch Serverless, NAT
   Gateway, ElastiCache), flag it explicitly before adding it rather than assuming it's fine.

   Three specific traps, because they are easy to get wrong and expensive to discover late:
   - **DynamoDB must use provisioned capacity, not on-demand.** The perpetual free tier
     covers 25 GB storage + 25 provisioned RCU + 25 provisioned WCU. On-demand tables bill
     per request from the very first request. Cap any autoscaling at or below 25 so a bug
     cannot scale past the grant.
   - **API Gateway's free tier expires after 12 months.** If per-request cost becomes a
     concern, Lambda Function URLs cost nothing beyond the Lambda invocation — the tradeoff
     is validating the Cognito JWT inside the handler instead of getting an API Gateway JWT
     authorizer for free.
   - **No VPC unless something genuinely requires one.** A NAT Gateway is a fixed hourly
     charge with no free tier and is the single most common way a "serverless" AWS project
     starts costing real money. Nothing in this design needs a VPC.
2. **Prod only for now.** We are building a single **production** environment first. Do not
   create staging/dev SAM parameter overrides, GitHub environments, or duplicate stacks yet —
   that comes later, once prod is stable. Structure code so adding a staging env later is
   straightforward (parameterized templates, environment variables, no hardcoded resource
   names), but don't build the staging plumbing itself yet.
3. **One phase at a time.** Implement strictly in phase order (below). Don't start Phase 3
   work while Phase 0 is incomplete, and don't reach ahead into a later phase's resources
   (e.g. don't provision cloud infra during the port — assume LocalStack/mocks until Phase 3).
4. **No secrets in code or SAM templates.** API keys (the Anthropic API key) go in
   **AWS Systems Manager Parameter Store** as `SecureString` parameters and are read at
   runtime or referenced from the template — never hardcoded or committed. Prefer Parameter
   Store over Secrets Manager: Standard-tier parameters are free, whereas Secrets Manager
   bills per secret per month. Anything that can use **IAM instead of a key should** —
   S3, DynamoDB, SQS and Rekognition all authenticate via the Lambda execution role, so they
   need no stored credential at all. The Anthropic API is the only exception (it takes a key);
   restaurant lookups use key-less OpenStreetMap (Overpass + Nominatim), so no Places key is
   needed. Model calls moved off IAM-authenticated Bedrock deliberately — see
   `docs/decisions.md` (2026-08-17).
5. **Don't fabricate AWS pricing.** Pricing and free-tier terms change; if a cost claim
   matters for a decision, note that it should be re-verified against the current AWS /
   third-party pricing pages rather than asserting a possibly-stale number as fact.
6. **Document the user's engineering/architecture decisions.** Whenever the user makes an
   engineering or architecture decision — a stack/library choice, a structural or scope
   call, picking between competing approaches, etc. (not routine/trivial choices) — ask them
   for the reasoning behind it before proceeding, then record the decision and their stated
   reason in `docs/decisions.md`. Keep entries dated, concise, and reason-first (decision,
   why, brief context) — not a transcript of the conversation. When a new decision reverses
   an old one, **mark the old entry superseded rather than deleting it.**

---

## Phase 0 — Port the existing Azure code to AWS *(done)*

**Goal:** the Phase 1 backend and Phase 2 frontend run locally against AWS emulators and AWS
SDKs, with behaviour unchanged. This is a port, not a redesign — resist the urge to improve
logic while moving it, so that a failing test means the port broke something.

Nothing was ever deployed to Azure, so there is no data to migrate and no cutover. The work
is entirely code and local tooling.

### Service mapping

| Azure (current code) | AWS (target) |
|---|---|
| Azure Functions HTTP triggers | Lambda + API Gateway HTTP API (Cognito JWT authorizer) |
| Durable Functions orchestrators | Step Functions **Standard** state machines |
| Queue Storage + queue trigger | SQS + Lambda event source mapping |
| Blob Storage + SAS URLs | S3 + presigned PUT/GET URLs |
| Azure SQL + native `VECTOR(1536)` | DynamoDB single table + in-Lambda cosine scan |
| Microsoft Entra External ID | Amazon Cognito user pool |
| Azure Static Web Apps | S3 + CloudFront (Origin Access Control) |
| Key Vault | SSM Parameter Store (`SecureString`) |
| Azure AI Content Safety | Amazon Rekognition `DetectModerationLabels` |
| Microsoft Foundry (Claude Haiku 4.5) | first-party Anthropic API (Claude) |
| `text-embedding-3-small` (1536-d) | pseudo-embedding stub, 1024-d (real provider TBD) |
| Anthropic `web_search` server tool | first-party Anthropic API `web_search` server tool (unchanged) |
| App Insights + Log Analytics | CloudWatch Logs + Metrics |
| Bicep | AWS SAM |
| Azurite + SQL Server 2025 container | LocalStack + `sam local` |

### Steps

1. **Data layer first — everything else depends on it.** Replace `backend/shared/db.py` and
   all raw T-SQL (spread across every trigger and the persistence/query activities) with a
   DynamoDB access module built on `boto3`. Single-table design:

   ```
   PK                 SK                      access pattern
   USER#<oid>         PROFILE                 user by oid
   USER#<oid>         JOB#<ts>#<jobId>        jobs by user, newest first (GET /api/jobs)
   JOB#<jobId>        META | RESULT           job status + result
   JOB#<jobId>        ELEMENT#<n>             dish elements, ingredients, steps
   REST#<placeId>     META                    restaurant + MenuLastFetchedAt cache gate
   REST#<placeId>     MENUITEM#<n>            menu items for matching
   RATE#<oid>         SCAN#<hourBucket>       atomic ADD + TTL
   RATE#<oid>         RECIPE#<hourBucket>     atomic ADD + TTL
   EMBEDDINGS         TECHNIQUE#<n>           small corpus, scanned whole
   ```

   Every access pattern in the app is already a key lookup, which is why this fits without a
   GSI. Two things get *better* than the SQL version and should be taken advantage of, not
   ported literally:
   - **Rate limiting** becomes an atomic `UpdateItem` with `ADD` plus native TTL expiry — no
     read-modify-write race and no counter cleanup. The hourly-bucket scheme from the
     2026-08-05 decision maps directly onto the sort key; keep both the hourly and daily
     windows and keep the rule that a rejected request consumes nothing.
   - **Sorted job listing** falls out of the `JOB#<ts>#<jobId>` sort key, replacing the
     `ORDER BY` + `IX_Jobs_UserId` index.

   Delete `backend/db/schema.sql` and `backend/scripts/apply_schema.py`; the table is defined
   in the SAM template from Phase 3 onward, and locally by a small setup script.
2. **Vector search.** `query_culinary_embeddings` loads the `EMBEDDINGS` partition and
   computes cosine similarity with numpy in-process. This is the same brute-force approach
   `VECTOR_DISTANCE` was doing — it just moves from the database into the Lambda. Embedding
   dimension is **1024** and is now only a constant, since the vectors are no longer typed by a
   database column. Vectors stay a pseudo-embedding stub — no real embedding provider yet
   (Anthropic has no embeddings endpoint; see `docs/decisions.md`, 2026-08-17). Re-seed via
   `backend/db/seed_embeddings.py`.
3. **HTTP layer.** Convert the 7 HTTP triggers from `azure.functions` blueprints to Lambda
   handlers taking an API Gateway v2 (payload format 2.0) event. Keep the handlers thin
   adapters over `shared/` — that is already the shape of the code and it is what keeps the
   tests portable. Routes, request/response bodies and status codes must not change;
   `docs/api.md` and `docs/payload-schemas.json` are the contract and the frontend is built
   against them.
4. **Orchestration.** Convert both Durable orchestrators to Step Functions ASL, stored as
   standalone `.asl.json` files (not embedded in the template, so they stay readable and
   diffable). Stage 1, from `orchestrators/dish_orchestrator.py`:

   ```
   ModerateImage → Choice(safe?) ─false→ MarkJobFailed
                 └true→ Choice(has selected_restaurant?)
                          ├true → SelectRestaurantCandidate
                          └false→ GeocodeRestaurantCandidates
                        → Parallel[ VisionGuess | FetchRestaurantMenu ]
                        → MatchMenuItem → PersistMatchResult → (Identified)
   Catch(States.ALL) → MarkJobFailed
   ```

   Stage 2, from `orchestrators/recipe_orchestrator.py`: `QueryCulinaryEmbeddings →
   GenerateRecreation → PersistRecipeResult`, with `Catch → MarkRecipeFailed` preserving the
   revert-to-`Identified` behaviour rather than `Failed`.

   **Standard workflows, not Express**: the menu fetch (search + fetch + LLM) can plausibly
   exceed the 5-minute Express ceiling, and exactly-once execution suits a pipeline where
   every step costs money.
5. **Queue + starter.** `shared/queue.py` → SQS via `boto3`. The queue-triggered
   `orchestrator_starter_queue.py` becomes a Lambda with an SQS event source mapping that
   flips the job to `Processing` and calls `StartExecution`. Keep the two-call upload
   protocol exactly as-is (`POST /api/jobs` mints the URL and does *not* enqueue;
   `POST /api/jobs/{id}/uploaded` enqueues) — that shape exists to fix an upload race, per
   the 2026-08-05 decision.
6. **Storage.** `shared/blob.py` → S3 presigned URLs. `generate_blob_sas` (write-only, for
   direct client upload) → `generate_presigned_url("put_object")`; the read SAS used by
   moderation and `GET /api/jobs/{id}` → `generate_presigned_url("get_object")`. This removes
   the current dependency on reading `credential.account_key` directly — presigned URLs are
   signed with the Lambda's role credentials. Configure CORS on the bucket for the browser
   `PUT`, replacing `scripts/configure_azurite_cors.py`.
7. **Moderation.** `shared/content_safety.py` → Rekognition `DetectModerationLabels`
   (`boto3`, no key). **Preserve the existing policy exactly**: an explicit unsafe verdict
   fails the job; a service error, timeout, missing config or exhausted quota does not; a
   missing object is *not* covered by fail-open. Map Rekognition's confidence score onto the
   existing `CONTENT_SAFETY_REJECT_SEVERITY` threshold concept and rename the setting.
8. **Model calls.** Route Claude calls through the **first-party Anthropic API** (`anthropic`
   SDK, `ANTHROPIC_API_KEY` from Parameter Store) via `shared/anthropic_client.py`. This affects
   `vision_guess`, `generate_recreation` and `fetch_restaurant_menu` (only the last is wired
   today; the first two are stubs). Supersedes the earlier Bedrock plan — see `docs/decisions.md`
   (2026-08-17).
9. **Menu search.** `fetch_restaurant_menu` uses the Anthropic API's server-side `web_search`
   tool: **one call** finds, fetches and extracts the menu as structured JSON
   (`shared/menu_extraction.py`). The model must support `web_search_20260209` (Sonnet 4.6+/Opus
   4.6+). Keep the 24-hour `MenuLastFetchedAt` cache gate. (The Bedrock era split this into a
   SERP search→fetch→extract chain; that's reverted.)
10. **Auth.** `shared/auth.py` keeps returning a stubbed `oid` via `X-Debug-User-Oid` — do not
    implement real validation here, it belongs in Phase 3. Swap the frontend's
    `@azure/msal-react` / `@azure/msal-browser` for a Cognito OIDC client behind the same
    `useAuth()` interface, still mock-by-default. Both sides are stubs today, which is why
    this is the cheapest possible moment to switch identity providers.
11. **Local dev loop.** Rewrite `backend/docker-compose.yml` around **LocalStack (Community)**
    — S3, SQS, DynamoDB, Step Functions and SSM — replacing Azurite and the SQL Server 2025
    container. Use `sam local start-api` / `sam local invoke` in place of `func start`.
    The Anthropic API (external HTTPS), Rekognition and Cognito are **not** local: the first two
    call the real service (cheap per call), and Cognito stays stubbed. Keep the
    `docker compose up -d` → run → `pytest` shape.
12. **Tests.** Most of the ~133 tests mock at the `shared/` boundary and survive largely
    intact. Two exceptions: `tests/unit/test_orchestrator.py` (10 tests that drive the Durable
    generator directly) is replaced by ASL definition tests and/or Step Functions Local, and
    the 4 integration test files repoint from Azurite/SQL Server to LocalStack. **The suite
    must be green before Phase 3 starts.**
13. **Docs.** Update `README.md`, `backend/README.md` and `frontend/README.md` last, once the
    local loop actually works — they currently document a working Azure-based setup, and
    rewriting them ahead of the code would replace accurate docs with aspirational ones.

**Explicitly out of scope for Phase 0:** any real AWS resource deployment, real auth, the SAM
template (Phase 3), CI/CD. Behaviour changes beyond the `web_search` split above.

---

## Phase 1 — Backend only *(done)*

**Goal:** working backend code, runnable locally against emulators, no cloud resources.

This phase is **complete in substance** — the pipeline, the two-stage split, rate limiting and
moderation all exist and are tested. What follows is the target-state description; Phase 0 is
what brings the existing code up to it.

1. Lambda handlers:
   - HTTP: accept image upload metadata + GPS coordinates, generate an S3 presigned PUT URL
     for direct client upload; a second endpoint enqueues the job to SQS once the upload
     completes.
   - SQS-triggered starter Lambda that begins the Step Functions execution.
2. Orchestration as **Step Functions Standard workflows**. This is a dependency chain, not
   simple parallel fan-out — model it accordingly:
   - Task: reverse-geocode the uploaded GPS coordinates → candidate restaurant(s) nearby
     (OpenStreetMap Overpass, key-less, with a Claude web_search fallback), real persistence.
   - Task: fetch the top candidate restaurant's menu (one Anthropic API call with the
     server-side `web_search` tool, extracted into structured menu items — most restaurant APIs
     don't return full menu text). Cache keyed by restaurant, gated on `MenuLastFetchedAt`.
   - Task (runs in parallel with the two above): call the vision model via the Anthropic API
     with the uploaded image, prompted for a preliminary dish/element breakdown (component names +
     visual description per element) — this is a *guess*, not the final answer.
   - Fan-in: match the vision model's guess against the real scraped menu items (by
     name/description similarity). Record which of three outcomes occurred: menu item
     matched (high confidence), restaurant/menu found but no item matched (medium — fall
     back to vision-only), no restaurant found near that GPS (low — vision-only). This
     match is the primary anti-hallucination mechanism, so don't skip it even when stubbed.
   - Task: retrieve the closest culinary technique/recipe embeddings for the matched (or
     guessed) dish — cosine similarity computed in-process over the `EMBEDDINGS` partition.
   - Task: structured generator — using the matched real menu item (if found) + visual
     details + retrieved technique embeddings, generate a full per-element recreation
     method: component list, ingredients per component, step-by-step instructions per
     component. This is the heaviest-output step in the pipeline — expect it to be the
     largest single cost/latency contributor, budget accordingly.
3. "Read result" HTTP Lambda: given a job ID, return current status/result from DynamoDB.
4. Local dev setup: LocalStack for S3/SQS/DynamoDB/Step Functions/SSM, `.env` (gitignored)
   for local config.
5. Unit tests for each task Lambda and the state machine's chained fan-out/fan-in logic
   (including the menu-matching step and its three confidence outcomes), mocking external
   API/model calls.
6. Document required environment variables in `README.md` / `.env.example` (names only, no
   real values) so Phase 3 knows what to wire into Parameter Store and function config.

**Local testing method:**
- **AWS SAM CLI** to run handlers locally (`sam local start-api`, `sam local invoke`).
- **LocalStack (Community)** via `docker compose` for S3, SQS, DynamoDB, Step Functions and
  SSM. Point `AWS_ENDPOINT_URL` at it. **DynamoDB Local** is a lighter alternative when only
  the data layer is needed.
- The Anthropic API, Rekognition and Cognito are not local — the first two call the real
  service, Cognito stays stubbed via `X-Debug-User-Oid`.
- The DynamoDB table definition lives in the SAM template (single source of truth from Phase
  3 onward) and is created locally by a setup script, so local and prod never drift apart.
- Connect from Python via `boto3`. For interactive poking-around, use the AWS CLI against the
  LocalStack endpoint or NoSQL Workbench — the same tooling works against real DynamoDB later,
  so there's no switch between local and prod.
- Unit tests: `pytest` with external calls (Anthropic API, OpenStreetMap, Rekognition)
  mocked — no real credentials needed to run the suite.
- Integration-style local tests: a smaller set hitting LocalStack directly (SQS round-trip,
  presigned URL generation, real DynamoDB writes/queries, the embedding scan) to catch what
  mocked unit tests would miss.
- Document the exact run commands (`docker compose up -d`, `sam local start-api`, `pytest`)
  in `README.md` so this is repeatable without re-deriving the setup.

**Explicitly out of scope for Phase 1:** any real AWS resource deployment, the React
frontend, auth/token validation (build the endpoints assuming an authenticated `oid` is
already present on the request — wire real validation in Phase 3), CI/CD.

---

## Phase 2 — Frontend only *(done)*

**Goal:** working React app that talks to the Phase 1 backend, no infra/CI yet.

The app is built — Vite + React 18 + TypeScript, six screens, seventeen components, polling
job status. The only migration work is step 4 below, handled in Phase 0.

1. React app scaffolded with Vite.
2. Core screens: photo capture/upload (with GPS permission prompt), job status view, result
   view showing the matched restaurant/menu item (with its confidence level/outcome —
   menu-matched vs. vision-only) plus the per-element recreation: each dish component as its
   own card/section with an ingredient list and step-by-step method.
3. Photo upload hits the backend's presigned-URL endpoint, then uploads directly to S3 using
   the returned URL (not through Lambda).
4. **Amazon Cognito** sign-in/sign-out and token acquisition via an OIDC client, configured
   through environment variables (user pool domain, client ID) — the real user pool won't
   exist until Phase 3, so keep the existing mock behind the same `useAuth()` interface.
5. Result delivery is **polling** (`GET /api/jobs/{id}` every 3s). `lib/jobs/useJobPolling.ts`
   is the documented seam if a push channel (AWS IoT Core / API Gateway WebSockets) is ever
   added — see `docs/decisions.md`, 2026-07-28.
6. Loading/error states, especially for: upload failure, job still processing, job failed,
   unauthenticated.

**Explicitly out of scope for Phase 2:** any AWS resource deployment, CI/CD, finalizing the
AI feature logic (that's Phase 3).

---

## Phase 3 — Infra only + AI feature *(done)*

**Goal:** all AWS resources provisioned via SAM/CloudFormation, and the AI feature (GPS →
restaurant lookup, menu scraping, vision model, menu-matching/grounding, per-element
structured recipe generator, embedding retrieval) fully wired end-to-end against real cloud
resources, in prod only.

Do not start this phase until Phase 0's test suite is green.

1. Write `infra/template.yaml` (SAM) declaring:
   - **S3 + CloudFront** for the React build, with Origin Access Control and a lifecycle rule
     on the uploads bucket so photos don't accumulate forever.
   - **Lambda functions** — one `CodeUri` shared via `Globals:`, one `Handler:` per function.
     Note `sam build` produces a separate zip per function, so put third-party dependencies in
     a shared `AWS::Serverless::LayerVersion` rather than the function package; `boto3` is
     already present in the runtime and must not be vendored.
   - **API Gateway HTTP API** with a Cognito JWT authorizer (see Global Rule 1 on the
     12-month free tier and the Function URL alternative).
   - **Step Functions** state machines referencing the `.asl.json` files via `DefinitionUri`.
   - **DynamoDB table** — provisioned 25/25 or below, TTL enabled on the rate-limit attribute.
   - **SQS** job queue with a dead-letter queue.
   - **Cognito** user pool + SPA app client (hosted UI or a custom sign-in page).
   - **SSM Parameter Store** `SecureString` parameters for the Anthropic API key and Google
     Places key. Prefer SAM policy templates and `Connectors` over hand-written IAM where
     possible; everything else (S3, DynamoDB, SQS, Rekognition) authenticates by role.
   - **CloudWatch** log groups with an explicit retention period — the default is "never
     expire", which is a slow-burning cost.
2. Put the Anthropic API key into Parameter Store as a `SecureString` (a one-time manual step —
   CloudFormation cannot create `SecureString` values). No per-model console access grant is
   needed on the first-party API.
   **✓ Done (2026-08-18):** `/replate/anthropic-api-key` created as a `SecureString`
   (default AWS-managed SSM key, so the Lambda's `SSMParameterReadPolicy` covers decryption).
3. Create the DynamoDB table from the template, not the console, so local and prod stay in
   lockstep.
4. Finalize the AI feature against real resources:
   - Restaurant lookup: real OpenStreetMap calls against the uploaded GPS (Overpass, key-less,
     with a Claude web_search fallback), replacing the earlier Google Places plan. See
     docs/decisions.md, 2026-08-22. The manual name-search typeahead uses OSM Nominatim, so no
     Google dependency remains.
   - Menu fetch: real Anthropic API call with the server-side `web_search` tool (see Global
     Rule 1 — check per-token and per-web_search cost).
   - Vision model call: Anthropic API Claude — implement retries, timeouts, and structured-output
     parsing/validation for the preliminary dish/element breakdown.
   - Menu-matching step: real matching logic (name/description similarity between the vision
     guess and the real menu items) and persist which of the three confidence outcomes
     occurred — this is the anti-hallucination mechanism, so add specific test coverage for
     all three outcomes, not just the happy path.
   - Embeddings: **moved to Phase 6 (the final phase).** The technique-grounding retrieval is
     deferred; the pseudo-embedding stub stands until then, so recipe generation runs on the
     matched menu item + vision breakdown alone. See Phase 6.
   - Structured generator: final Anthropic API call producing the per-element ingredient lists +
     steps, grounded in the matched menu item (if any) + retrieved technique embeddings (a stub
     until Phase 6) — the
     heaviest-output, highest-cost call in the pipeline, so budget and rate-limit around it
     specifically (see step 6).
5. Real Cognito JWT validation on the API, replacing the `X-Debug-User-Oid` stub on both the
   backend and the frontend.
6. Per-user rate limiting already exists in DynamoDB — verify the separate scan and recipe
   quotas hold against the real table, including the TTL expiry behaviour.
7. Image content moderation via Rekognition before an uploaded photo is processed.
8. Cache aggressively: the `MenuLastFetchedAt` gate should prevent re-scraping the same
   restaurant's menu on every visit, not just every job.
9. Deploy manually (`sam build && sam deploy --guided`) to validate everything end to end
   before automating deployment in Phase 4.
10. For every resource above, note in the PR/commit: does it have a free tier, is that grant
    always-free or 12-month, and what's the overage rate — per Global Rule 1.

**Explicitly out of scope for Phase 3:** GitHub Actions workflows (deployment stays manual
this phase), staging environment, and the real embedding provider / technique-corpus grounding
(moved to Phase 6, the final phase).

---

## Phase 4 — CI/CD *(done)*

**Goal:** automate what Phases 0-3 built manually, still prod-only.

1. GitHub Actions workflow: `deploy-infra.yml` — runs `sam build && sam deploy
   --no-confirm-changeset --no-fail-on-empty-changeset` on merge to `main` (or manual
   trigger), authenticating via **OIDC federated credentials to an AWS IAM role** (no
   long-lived access keys stored in GitHub).
2. GitHub Actions workflow: `deploy-backend.yml` — builds and deploys the Lambda functions on
   merge to `main`. (With SAM this may reasonably fold into `deploy-infra.yml`, since the
   functions and their infrastructure are one stack — decide and record which.)
3. GitHub Actions workflow: `deploy-frontend.yml` — builds the React app, syncs to the S3
   site bucket, and creates a CloudFront invalidation.
4. A minimal lint/build-check job that runs on every PR (before merge, not just on `main`) —
   including `sam validate --lint` — just enough to catch obvious breakage. Full unit + e2e
   test automation is deferred to Phase 5, so don't build out the full test suite integration
   here.
5. Store non-secret config (stack name, region, bucket names) as GitHub Actions variables;
   secrets referenced by the workflows (if any are needed beyond OIDC) go in GitHub Actions
   secrets, never committed.
6. A manually-triggered "teardown" workflow (`sam delete`) to help control cost between active
   development/demo periods, since this is prod-only with no staging safety net yet. Note that
   most of this stack scales to zero on its own — the teardown is for peace of mind, not a
   standing hourly bill.

**Explicitly out of scope for Phase 4:** staging environment/second GitHub environment,
blue-green or canary deployments (defer until staging exists), full unit/e2e test automation
in the pipeline (Phase 5).

---

## Phase 5 — Unit testing + e2e testing in CI/CD *(current phase)*

**Goal:** the backend unit tests and frontend tests run automatically on every PR, plus a
proper end-to-end test suite exercising the full flow against prod (or a production-like
deployed instance), all wired into the GitHub Actions pipeline.

1. **Backend unit tests in CI:** a GitHub Actions job that runs LocalStack as a service
   container (or via `docker compose up` in the job) and runs the `pytest` suite — both the
   mocked unit tests and the container-backed integration tests, including the menu-matching
   outcome tests — on every PR. Fail the PR check if tests fail.
2. **Frontend unit tests in CI:** a job that runs the React test suite (Vitest + React Testing
   Library) and lint on every PR. Note the frontend currently has **zero** tests; this phase
   is where that gets fixed.
3. **E2E test suite:** Playwright, covering the full user journey: sign in (Cognito test/demo
   account) → upload a photo with GPS → poll for the job result → press "Reverse engineer" →
   verify the structured result is returned and displayed correctly.
4. **Where e2e runs:** against the deployed prod environment after a deploy (a `post-deploy`
   job, or a dedicated `e2e.yml` triggered after the deploy workflows succeed), since there's
   no staging environment yet — be mindful this means e2e runs incur real Anthropic API (tokens
   + web_search) cost and consume Cognito MAU (OpenStreetMap lookups are free), so keep the suite lean (happy
   path + a couple of key failure paths) rather than exhaustive.
5. **Test data hygiene:** use a dedicated test/demo user account (not a real user) for e2e
   runs, and clean up any DynamoDB items / S3 objects the run creates afterward (or tag them
   so they're excluded from real usage metrics). The uploads bucket lifecycle rule helps but
   is not a substitute.
6. **Gate deploys on tests where practical:** make the backend/frontend unit test jobs
   (steps 1-2) required checks before merge to `main`. E2E (steps 3-4) runs post-deploy by
   necessity here, so treat e2e failures as an alert/rollback trigger rather than a pre-merge
   gate for now — this gap closes once a staging environment exists.

**Explicitly out of scope for Phase 5:** running e2e against a staging environment pre-deploy
(not possible yet — no staging exists), load/performance testing.

---

## Phase 6 — Recipe grounding (real embeddings / RAG) *(final phase)*

**Goal:** make the culinary-technique retrieval real, so recipe generation is grounded in
trusted technique references rather than the model's unaided knowledge. This hardens the
*method* (the how); it is separate from the menu match, which already hardens the dish
*identity* (the what). Deliberately last: the generator is already usable without it (it runs
on the matched menu item + vision breakdown), so this is quality polish, not a blocker.

Do not start this phase until Phases 3, 4 and 5 are done.

1. **Decide whether the corpus is worth it first.** A technique-RAG step only improves output
   if the corpus holds something the model does not already know well: authoritative, unusual,
   or curated technique beyond its training. If a curated corpus is not worth building, the
   honest outcome of this phase may be "skip retrieval, rely on the model," which is a valid,
   defensible result. Decide this before wiring anything.
2. **Pick a real embedding provider.** Anthropic has no embeddings endpoint, so this needs a
   third-party provider. Record the choice and reasoning in `docs/decisions.md` (Global Rule
   6). Keep the 1024-d width or re-baseline the `EMBEDDING_DIM` constant to the provider's.
3. **Build and seed the corpus.** Curate the technique/reference snippets, embed them, and seed
   the vectors into the `EMBEDDINGS` partition via `backend/db/seed_embeddings.py`.
4. **Wire real semantic retrieval.** Replace `models.pseudo_embedding` with a real
   embed-the-query call in `query_culinary_embeddings`; the in-Lambda cosine scan over the
   `EMBEDDINGS` partition stays as-is.
5. **Alternative to weigh:** instead of a static embedded corpus, ground the generator with the
   server-side `web_search` tool at generation time (the mechanism the menu fetch already uses),
   pulling live technique references for the specific dish. More current and no corpus to
   curate, at the cost of latency and per-call spend. Pick one and record why.
6. **Scale the vector store only if needed.** The brute-force in-Lambda scan is fine for a small
   corpus. Only if it outgrows that, move to a real vector index (OpenSearch Serverless, Aurora
   + pgvector, or S3 Vectors). Note OpenSearch Serverless has a minimum billed capacity and no
   free tier, so this is a "when it is actually needed" change, per Global Rule 1.

7. **Set honest accuracy expectations in the UI.** Add an unobtrusive note (for example on the
   capture screen, or near the result's confidence badge) that Replate is designed for
   restaurant dishes: the menu match is what keeps identification honest, so a home-cooked meal
   with no restaurant menu to match against (the `vision_only_low` outcome) may be less
   accurate. This is UX copy rather than technique grounding, but it belongs with this phase's
   "be honest about accuracy" theme, and it is a small standalone frontend change that could
   also land earlier if wanted.

**Explicitly out of scope for Phase 6:** anything beyond technique grounding and the
accuracy-expectation UI note above.

---

## Future (not yet scoped — do not build ahead of this)

- Staging environment: second CloudFormation stack, second Cognito app client (or a different
  callback URL), a GitHub environment with its own secrets/variables, a promotion workflow
  (staging → prod), and — once staging exists — running the Phase 5 e2e suite pre-deploy
  against staging instead of post-deploy against prod.
- Push-based result delivery (API Gateway WebSockets or AWS IoT Core over MQTT) replacing the
  3-second poll, if polling ever becomes a real cost or UX problem.
- Any paid-tier upgrades once free-tier limits are actually being approached in practice
  (DynamoDB capacity, Cognito MAU, CloudFront transfer, etc.).
