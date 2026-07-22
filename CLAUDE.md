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
Result is pushed back to the client over a real-time channel.

Pipeline is a dependency chain, not just parallel fan-out:
`GPS → nearby restaurant candidates → fetch/scrape that restaurant's menu` runs alongside
`photo → vision model's preliminary dish/element guess`, then both feed into a
`match guess against real menu items` step, then a `generate per-element recipe` step
that also grounds itself against a vector DB of culinary technique/recipe embeddings.

**Stack**
- Frontend: React
- Backend: Python (Azure Functions, Durable Functions for orchestration)
- Database: Azure SQL Database (free-offer tier), including its native VECTOR data type for
  culinary-technique embeddings — no separate vector DB
- Auth: Microsoft Entra External ID (consumer user pool)
- Infra: Bicep
- CI/CD: GitHub Actions

## Global rules (apply in every phase)

1. **Azure cost discipline.** Before adding or provisioning any Azure resource, check whether
   it has a free tier / free monthly grant, and call out (in the PR description or commit
   message) what happens once free tier is exceeded. Prefer serverless / consumption-based
   SKUs over anything with a fixed hourly cost. If a resource has no free tier and no
   consumption-based option (e.g. Redis, SignalR Standard), flag it explicitly before adding
   it rather than assuming it's fine.
2. **Prod only for now.** We are building a single **production** environment first. Do not
   create staging/dev Bicep parameter files, GitHub environments, or duplicate resource
   groups yet — that comes later, once prod is stable. Structure code so adding a staging
   env later is straightforward (parameterized Bicep, environment variables, no hardcoded
   resource names), but don't build the staging plumbing itself yet.
3. **One phase at a time.** Implement strictly in phase order (below). Don't start Phase 2
   work while Phase 1 is incomplete, and don't reach ahead into a later phase's resources
   (e.g. don't provision infra in Phase 1 — assume local emulators/mocks until Phase 3).
4. **No secrets in code or Bicep params.** API keys (Claude/OpenAI, Google Places/Yelp, etc.)
   and connection strings go in Azure Key Vault (provisioned in Phase 3) and are referenced,
   never hardcoded or committed.
5. **Don't fabricate Azure pricing.** Pricing changes; if a cost claim matters for a decision,
   note that it should be re-verified against the current Azure/Anthropic pricing pages
   rather than asserting a possibly-stale number as fact.
6. **Document the user's engineering/architecture decisions.** Whenever the user makes an
   engineering or architecture decision — a stack/library choice, a structural or scope
   call, picking between competing approaches, etc. (not routine/trivial choices) — ask them
   for the reasoning behind it before proceeding, then record the decision and their stated
   reason in `docs/decisions.md`. Keep entries dated, concise, and reason-first (decision,
   why, brief context) — not a transcript of the conversation.

---

## Phase 1 — Backend only

**Goal:** working backend code, runnable locally against emulators, no cloud resources yet.

Steps:
1. Scaffold an Azure Functions app (Python) with:
   - HTTP-triggered function: accept image upload metadata + GPS coordinates, generate a
     Blob Storage SAS URL for direct client upload, push a job message to a queue.
   - Queue-triggered function (or Durable Functions orchestrator) that picks up the job.
2. Implement the orchestration engine as a **Durable Functions** orchestrator. This is a
   dependency chain, not simple parallel fan-out — model it accordingly:
   - Activity: reverse-geocode the uploaded GPS coordinates → candidate restaurant(s) nearby
     (Google Places/Yelp Fusion) — mock/stub for now.
   - Activity: fetch/scrape the top candidate restaurant's menu (web search + fetch + LLM
     extraction into structured menu items — most restaurant APIs don't return full menu
     text) — mock/stub for now. Cache results keyed by restaurant ID (menus don't need
     re-fetching every visit).
   - Activity (runs in parallel with the two above): call the vision model (Claude API or
     Azure OpenAI vision) with the uploaded image, prompted for a preliminary dish/element
     breakdown (component names + visual description per element) — this is a *guess*, not
     the final answer.
   - Fan-in step: match the vision model's guess against the real scraped menu items (by
     name/description similarity). Record which of three outcomes occurred: menu item
     matched (high confidence), restaurant/menu found but no item matched (medium — fall
     back to vision-only), no restaurant found near that GPS (low — vision-only). This
     match is the primary anti-hallucination mechanism, so don't skip it even when stubbed.
   - Activity: query the vector DB (Azure SQL's native `VECTOR` column, brute-force
     `VECTOR_DISTANCE` at this scale — no separate vector database) for the closest known
     culinary technique/recipe embeddings relevant to the matched (or guessed) dish —
     stub against a local SQL Server container for now.
   - Activity: structured generator — using the matched real menu item (if found) + visual
     details + retrieved technique embeddings, generate a full per-element recreation
     method: component list, ingredients per component, step-by-step instructions per
     component. This is the heaviest-output step in the pipeline — expect it to be the
     largest single cost/latency contributor, budget accordingly.
3. Implement the "read result" HTTP-triggered function: given a job ID, return current
   status/result from Azure SQL Database.
4. Local dev setup: Azurite (Storage emulator) for Blob/Queue, a local SQL Server container
   for the database, `local.settings.json` (gitignored) for local secrets/config.
5. Write unit tests for each activity function and the orchestrator's chained fan-out/fan-in
   logic (including the menu-matching step and its three confidence outcomes), mocking
   external API/LLM calls.
6. Document required environment variables / app settings in `README.md` or `.env.example`
   (names only, no real values) so Phase 3 knows what to wire into Key Vault / app settings.

**Local testing method (Phase 1):**
- Install **Azure Functions Core Tools** to run the Function App locally (`func start`).
- Run **Azurite** locally (Docker container or npm package) to emulate Blob Storage and
  Queue Storage — point `local.settings.json`'s `AzureWebJobsStorage` at it.
- Run **SQL Server in Docker** locally — use the `mcr.microsoft.com/mssql/server:2025-latest`
  image specifically (not `2022-latest`), since the `VECTOR` data type used for culinary
  technique embeddings requires SQL Server 2025. Point the connection string in
  `local.settings.json` at the container (SA password local-dev only, never a real secret).
- Provide a `docker-compose.yml` in the backend folder that spins up Azurite + the SQL Server
  2025 container together, so `docker compose up` + `func start` is the full local dev loop.
- Keep a `schema.sql` (or Alembic migrations if using SQLAlchemy) as the single source of
  truth for table definitions — applied locally by the setup script and later in Phase 3 by
  the deployment pipeline, so local and prod schemas never drift apart.
- Connect from Python via `pyodbc` or `SQLAlchemy` (`mssql+pyodbc` dialect). For interactive
  poking-around during development, use Azure Data Studio or the VS Code `mssql` extension —
  both connect to the local container the same way they'll connect to the real Azure SQL
  Database later, so there's no tooling switch between local and prod.
- Unit tests: `pytest` for the activity functions and orchestrator logic, with external
  calls (Claude/OpenAI vision, restaurant/menu scraping, menu-matching) mocked — no real API
  keys or network calls needed to run the test suite.
- Integration-style local tests: a smaller set of tests that hit the running
  Azurite/local SQL Server container directly (queue message round-trip, blob SAS URL
  generation, real INSERT/SELECT and `VECTOR_DISTANCE` queries) to catch issues unit tests
  with mocks would miss.
- Document the exact local run commands (e.g. `docker compose up -d`, `func start`,
  `pytest`) in `README.md` so this is repeatable without re-deriving the setup each time.

**Explicitly out of scope for Phase 1:** any real Azure resource deployment, the React
frontend, auth/token validation (build the endpoints assuming an authenticated `oid` is
already present on the request — wire real validation in Phase 3), CI/CD.

---

## Phase 2 — Frontend only

**Goal:** working React app that talks to the Phase 1 backend (running locally or against
whatever backend endpoint exists), no infra/CI yet.

Steps:
1. Scaffold the React app (Vite or CRA — pick one and stick with it).
2. Build the core screens: photo capture/upload (with GPS permission prompt), job status
   view, result view showing the matched restaurant/menu item (with its confidence
   level/outcome — menu-matched vs. vision-only) plus the per-element recreation: each
   dish component as its own card/section with an ingredient list and step-by-step method.
3. Wire photo upload to hit the backend's SAS-URL endpoint, then upload directly to Blob
   Storage using the returned SAS URL (not through the Function).
4. Add `@azure/msal-react` for Entra External ID sign-in/sign-out and token acquisition,
   configured via environment variables (tenant authority URL, client ID) — actual tenant
   won't exist until Phase 3, so stub/mock auth locally until then, but build the integration
   points now.
5. Add a real-time result listener (SignalR/Web PubSub client) — stub against a local mock
   until the Phase 3 SignalR resource exists.
6. Basic loading/error states, especially for: upload failure, job still processing, job
   failed, unauthenticated.

**Explicitly out of scope for Phase 2:** any Azure resource deployment, CI/CD, finalizing the
AI feature logic (that's Phase 3 — assume the backend contract from Phase 1 is stable enough
to build against).

---

## Phase 3 — Infra only + AI feature

**Goal:** all Azure resources provisioned via Bicep, and the AI feature (GPS→restaurant
lookup, menu scraping, vision model, menu-matching/grounding, per-element structured
recipe generator, vector search) fully wired end-to-end against real cloud resources, in
prod only.

Steps:
1. Write Bicep modules for:
   - Static Web App (React hosting)
   - Function App (Consumption or Flex Consumption plan — check current free grant before
     picking the plan) + its required storage account (including the separate storage
     account Durable Functions needs for orchestration state)
   - Azure SQL Database (server + free-offer database — 100,000 vCore-seconds, 32 GB
     data/backup storage free/month, up to 10 free databases per subscription; set
     behavior-on-limit to auto-pause, not bill-overage, so a bug/spike can't surprise-bill)
   - Storage account: Blob container (uploads) + Queue (job queue)
   - Microsoft Entra External ID tenant + app registrations (SPA + API) — check current
     50,000 MAU free tier
   - Key Vault (for LLM API keys, any third-party API keys, Entra client secret if used)
   - SignalR Service or Web PubSub (start on Free tier; note its connection/message limits)
   - Azure AI Content Safety (for image moderation) if in scope — check free tier
2. Wire the Function App's app settings to Key Vault references for all secrets.
3. Apply `schema.sql` (from Phase 1) to the real Azure SQL Database via a deployment script
   step or idempotent migration tool — not the Azure Portal — so the schema stays in lockstep
   with local dev.
4. Finalize the AI feature against real resources:
   - Restaurant lookup: real Google Places/Yelp Fusion calls against the uploaded GPS.
   - Menu fetch/scrape: real web search + fetch + LLM extraction — decide here whether this
     uses Claude/OpenAI's native web search tool or a third-party SERP API (see Global Rule
     1 — check per-call cost); avoid Azure AI Foundry Grounding with Bing unless a specific
     requirement demands it, given its significantly higher per-transaction cost.
   - Vision model call: Claude API (Sonnet or Haiku) or Azure OpenAI (GPT-4o-mini), whichever
     was chosen — implement retries, timeouts, and structured-output parsing/validation for
     the preliminary dish/element breakdown.
   - Menu-matching step: implement the real matching logic (name/description similarity
     between the vision model's guess and real `MenuItems` rows) and persist which of the
     three confidence outcomes occurred — this is the anti-hallucination mechanism, so add
     specific test coverage for all three outcomes, not just the happy path.
   - Vector DB integration: real Azure SQL `VECTOR` column queries (`VECTOR_DISTANCE`)
     against real culinary-technique embeddings (generate embeddings via the chosen model's
     embedding endpoint) — note DiskANN indexing is still private-preview for Azure SQL, so
     this is a brute-force scan at MVP scale; revisit if the embeddings table grows large.
   - Structured generator: final call producing the per-element ingredient lists + steps,
     grounded in the matched menu item (if any) + retrieved technique embeddings — this is
     the heaviest-output, highest-cost call in the pipeline, so budget and rate-limit around
     it specifically (see step 6).
5. Add basic rate limiting on the upload endpoint (e.g. a per-user counter in Azure SQL) to
   cap AI-call spend from any single user — important here given the pipeline is now 5+
   chained AI/API calls per photo, not 3 parallel ones.
6. Add image content moderation before an uploaded photo is processed.
7. Cache aggressively: `Restaurants.MenuLastFetchedAt` should gate re-scraping the same
   restaurant's menu on every visit, not just every job.
8. Deploy Bicep to prod manually (`az deployment group create`) to validate everything end to
   end before automating deployment in Phase 4.
9. For every resource above, note in the PR/commit: does it have a free tier, what's the
   free-tier limit, and what's the overage rate — per Global Rule 1.

**Explicitly out of scope for Phase 3:** GitHub Actions workflows (deployment stays manual
this phase), staging environment.

---

## Phase 4 — CI/CD

**Goal:** automate what Phase 1-3 built manually, still prod-only.

Steps:
1. GitHub Actions workflow: `deploy-infra.yml` — runs `az deployment group create` against
   `infra/main.bicep` on merge to `main` (or manual trigger), using OIDC federated
   credentials for Azure login (no long-lived service principal secret stored in GitHub).
2. GitHub Actions workflow: `deploy-backend.yml` — builds and deploys the Function App
   (`func azure functionapp publish` or zip deploy) on merge to `main`.
3. GitHub Actions workflow: `deploy-frontend.yml` — builds the React app and deploys to
   Static Web Apps (SWA has an official GitHub Action for this).
4. Add a minimal lint/build-check job that runs on every PR (before merge, not just on
   `main`) — just enough to catch obvious breakage. Full unit + e2e test automation is
   deferred to Phase 5, so don't build out the full test suite integration here.
5. Store non-secret config (resource group name, region, etc.) as GitHub Actions variables;
   secrets referenced by the workflows (if any are needed beyond OIDC) go in GitHub Actions
   secrets, never committed.
6. Add a manually-triggered "teardown" or "scale to zero" workflow to help control cost
   between active development/demo periods, since this is prod-only with no staging safety
   net yet.

**Explicitly out of scope for Phase 4:** staging environment/second GitHub environment,
blue-green or slot-based deployments (defer until staging exists), full unit/e2e test
automation in the pipeline (Phase 5).

---

## Phase 5 — Unit testing + e2e testing in CI/CD

**Goal:** the Phase 1 backend unit tests and Phase 2 frontend tests run automatically on
every PR, plus a proper end-to-end test suite exercising the full flow against prod (or a
production-like deployed instance), all wired into the GitHub Actions pipeline.

Steps:
1. **Backend unit tests in CI:** add a GitHub Actions job that spins up Azurite + the
   `mssql/server:2025-latest` SQL Server container as service containers (or via
   `docker compose up` in the job) and runs the Phase 1 `pytest` suite (both the mocked unit
   tests and the container-backed integration tests, including the menu-matching outcome
   tests) on every PR — fail the PR check if tests fail.
2. **Frontend unit tests in CI:** add a job that runs the React app's test suite (Jest/Vitest
   + React Testing Library) and lint on every PR.
3. **E2E test suite:** build an end-to-end test suite (Playwright recommended — good Azure
   DevOps/GitHub Actions support and handles file upload + async waiting well) that covers
   the full user journey: sign in (Entra External ID test/demo account) → upload a photo with
   GPS → poll or listen for the job result → verify structured result is returned and
   displayed correctly.
4. **Where e2e runs:** run e2e tests against the deployed prod environment after a deploy (a
   `post-deploy` job in `deploy-frontend.yml`/a dedicated `e2e.yml` workflow triggered after
   `deploy-infra.yml`/`deploy-backend.yml`/`deploy-frontend.yml` succeed), since there's no
   staging environment yet — be mindful this means e2e runs will incur real AI-call cost
   (vision model + any internet-lookup tool) and consume Entra External ID MAU, so keep the
   e2e suite lean (happy path + a couple of key failure paths) rather than exhaustive.
5. **Test data hygiene:** use a dedicated test/demo user account (not a real user) for e2e
   runs, and clean up any Azure SQL Database rows / Blob Storage files the e2e run creates
   afterward (or tag them so they're excluded from real usage metrics/analytics).
6. **Gate deploys on tests where practical:** for the backend/frontend unit test jobs (step
   1-2), make them required checks before merge to `main`. E2E (step 3-4) runs post-deploy by
   necessity here (no staging to run it against pre-deploy), so treat e2e failures as an
   alert/rollback trigger rather than a pre-merge gate for now — this gap closes once a
   staging environment exists.

**Explicitly out of scope for Phase 5:** running e2e against a staging environment
pre-deploy (not possible yet — no staging exists), load/performance testing.

---

## Future (not yet scoped — do not build ahead of this)

- Staging environment: second resource group, second Entra External ID app registration (or
  reuse with a different redirect URI), GitHub environment with its own secrets/variables,
  a promotion workflow (staging → prod), and — once staging exists — running the Phase 5 e2e
  suite pre-deploy against staging instead of post-deploy against prod.
- Any premium/paid-tier upgrades once free-tier limits are actually being approached in
  practice (Azure SQL Database vCore-seconds/storage, SignalR connections, Entra MAU, etc.).
