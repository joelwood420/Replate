# Decisions

A log of decisions the project owner has made about how Replate is built, and why. Per
CLAUDE.md's global rules, whenever a decision like this comes up Claude asks for the
reasoning first, then adds an entry here — newest first.

---

## 2026-08-05 — Rate limiting: separate quotas per pipeline stage, not one shared cap

**Decision:** Cap `POST /jobs` (scan) and `POST /jobs/{jobId}/reverse-engineer` (recipe
generation) with independent per-user quotas — 10/hour and 30/day for scans, 5/hour and
15/day for generations — counted in a new `RateLimitCounters` table rather than by counting
`Jobs` rows.

**Why:** The owner's description of the intended flow settled it: a photo is matched to the
menu and saved to the cookbook automatically, but is only reverse-engineered when the user
opens the cookbook and presses the button. Those are two different user actions with
different cost and frequency profiles — scanning is casual and happens on every plate, while
generation is deliberate and is the heaviest AI call in the app. One shared limit would have
to be either too tight to scan freely or too loose to cap generation spend.

**Context worth recording:**

- CLAUDE.md Phase 3 step 5 says "rate limiting on the upload endpoint", which was written
  before the pipeline was split into two stages. Following it literally would have left the
  most expensive call in the app uncapped.
- Counting `Jobs` rows would have avoided a new table, but only stage 1 inserts a job — there
  is no row to count for a generation, and no way to distinguish the two actions.
- Counters are bucketed by hour: the hourly limit reads the current bucket and the daily
  limit sums the last 24, so both windows come from one bucket granularity and cannot drift
  apart. The daily window slides at hour resolution rather than resetting at midnight.
- A rejected request consumes nothing. Incrementing on rejection would let a client that
  retries into a closed window push its own reset out indefinitely.

---

## 2026-08-05 — Image moderation fails closed on a verdict, open on an error

**Decision:** An explicit "unsafe" verdict from Azure AI Content Safety fails the job. A
service error, timeout, missing configuration or exhausted quota does **not** — it logs a
warning and lets the scan continue.

**Why:** "This image is unsafe" and "I could not check this image" are different answers and
should not produce the same outcome. The Content Safety free tier rejects requests outright
once its 5,000 images/month allowance is used, so treating a failed check as unsafe would
take scanning offline for the rest of the calendar month on the busiest month of the year.

**Context worth recording:**

- Moderation runs as the first activity in stage 1, ahead of the vision call and the menu
  fetch, so a rejected photo costs one moderation call and no AI spend at all.
- A **missing** blob is deliberately outside the fail-open rule: it means the client never
  finished uploading, not that the service was unavailable, and passing it downstream would
  fail the vision call a step later with a much less obvious error.
- The rejection threshold is severity 4 ("medium") of the 0/2/4/6 scale, configurable via
  `CONTENT_SAFETY_REJECT_SEVERITY`. Rejecting at 2 ("low") risks failing plausible food
  photos that read low on a category.
- The failure mode is invisible by design, so it has to be watched: if the endpoint or key is
  wrong, everything passes and nothing looks broken. Check the Key Vault references blade
  after deploying.

---

## 2026-08-05 — Start the pipeline from an explicit upload-complete call

**Decision:** `POST /jobs` no longer enqueues the job. A new `POST /jobs/{jobId}/uploaded`,
called by the client after its blob `PUT` succeeds, is what starts stage 1.

**Why:** The old sequence had a race: the queue message was sent while creating the job row,
but the client can only upload the photo after that call returns the SAS URL, so the
orchestrator could start — and open the blob — before the image existed. Nothing caught it
because the vision step was still canned and never read the image. Image moderation reads it,
and so will the real vision call, so the choice was to fix the sequencing or to have the
first activity poll for the blob and pay for the wait on every scan.

**Context worth recording:**

- The owner chose the extra round trip over papering over the race, accepting a small
  frontend change (`CaptureScreen.tsx`) in what was otherwise a backend-only task.
- A side benefit: an abandoned upload now costs nothing. The job sits at `Queued` and no
  orchestration is ever started.
- The endpoint is idempotent by status — only a `Queued` job enqueues — and
  `orchestrator_starter_queue` starts the orchestration with `instance_id=job_id`, so even a
  duplicated message cannot double-process.

---

## 2026-08-04 — Delete the unused payload dataclasses instead of adopting them

**Decision:** Remove `DishElementGuess`, `VisionGuess`, `RestaurantCandidate` and `MenuItem`
from `backend/shared/models.py` rather than wiring them into the activities that build the
same shapes by hand. `models.py` now holds only what code actually imports: `MatchMethod`,
`JobStatus`, `EMBEDDING_DIM` and `pseudo_embedding`.

**Why:** The owner's rule — if it's dead and no longer used at all, get rid of it. Nothing in
the repo imported these four names; a repo-wide grep found them only inside `models.py`
itself.

**Context worth recording:**

- They were found by a knowledge-graph pass over the repo, which flagged them as isolated
  nodes — no inbound or outbound edges anywhere in the codebase.
- Passing plain dicts across the Durable Functions activity boundary
  (`activities/vision_guess.py`, `activities/geocode_restaurant_candidates.py`,
  `shared/places.py`) stays the intended pattern: activity inputs and outputs have to be
  JSON-serializable, so a dataclass would only be a wrapper that gets `asdict()`-ed
  immediately.
- The deleted definitions had already **drifted**, which is the real argument against keeping
  them as documentation: `RestaurantCandidate` in `models.py` still had
  `restaurant_id`/`distance_m`/`menu_source_url`, while the live shape returned by
  `shared/places.py` and specified in `docs/payload-schemas.json` uses `place_id` and carries
  no distance. An unused type that contradicts the real contract is worse than no type.
- The payload shapes remain defined in two places that are actually load-bearing:
  `docs/payload-schemas.json` `$defs` (the API contract) and `frontend/src/lib/apiClient.ts`
  (the TypeScript consumer).

## 2026-07-30 — Split the pipeline: identify on capture, reverse-engineer on demand

**Decision:** Break the single orchestrator into two stages. Uploading a photo runs stage 1
only — identify the restaurant, fetch its menu, get the vision guess, match the guess against
the menu — and **auto-saves the dish to the user's cookbook**. The per-element recreation
method is generated by a second, separate orchestrator that only runs when the user opens
that dish and presses **Reverse engineer**. The explicit "save to cookbook?" choice is gone.

**Why:** Three reasons, all the owner's:

- **Cost.** Recipe generation is the heaviest-output, highest-cost call in the pipeline
  (CLAUDE.md says as much), and it was firing on every single photo regardless of whether the
  user ever intended to cook that dish. Making it opt-in means only paying for the dishes
  someone actually wants.
- **Wrong moment.** The user is sitting in a restaurant. They don't need the method to
  recreate the dish while they're eating it, and waiting at the table on the slowest step in
  the chain is annoying. Stage 1 gets them the identified dish quickly; the recipe can wait
  until they're home.
- **Better UX than the old save prompt.** If you bothered to photograph your meal, you
  obviously want to keep it — so asking was friction with a foregone conclusion.

**Consequences worth recording:**

- The vision model's guess now has to be **persisted** (`JobResults.VisionGuessJson`). It was
  previously only ever materialised as `DishElements` rows by the generator, so a dish with a
  match but no recipe would have lost it entirely and stage 2 would have had nothing to work
  from. Added as a separately-guarded `ALTER` batch, since `schema.sql`'s `CREATE TABLE`
  statements are no-ops on an existing database.
- Two new statuses, `Identified` and `Generating`. `Identified` is terminal — polling stops
  there and only resumes when the user triggers stage 2.
- A stage-2 failure reverts to `Identified` rather than `Failed`, so a transient generator
  error can't discard a successful restaurant identification and menu match. `Failed` now
  means specifically "stage 1 failed".
- `GET /jobs/{jobId}` returns `result` from `Identified` onward instead of only when
  `Completed`, because the confidence badge and matched dish name are exactly what makes a
  freshly-saved cookbook entry worth looking at before any recipe exists.
- Stage 2 must be idempotent — `DishElements` has no unique key on `(JobId, SortOrder)`, so
  `persist_recipe_result` deletes any previous recipe before writing, and the endpoint returns
  `409` unless the job is `Identified`.
- The two orchestrations need distinct Durable instance ids (`{job_id}` and
  `{job_id}:recipe`) or the second `start_new` collides with the first.

---

## 2026-07-28 — AI models served through Microsoft Foundry rather than the first-party Anthropic API

**Decision:** Deploy Claude through Microsoft Foundry (Azure AI Foundry) — a
`Microsoft.CognitiveServices/accounts` resource of kind `AIServices` with an Anthropic-format
model deployment — instead of calling `api.anthropic.com` with a first-party key. The
Anthropic SDK's `AnthropicFoundry` client speaks to it.

**Why:** The owner is already using Foundry API keys. Keeping the models inside Azure means
one identity and billing story for the whole stack: the Function App's managed identity can
authenticate to the models with `Cognitive Services User`, so the eventual target is zero
stored API keys, and model spend appears on the Azure bill alongside everything else rather
than a separate vendor invoice.

**Consequences worth recording:** Foundry hosts models in a restricted set of regions
(`eastus2`/`swedencentral` for Haiku), so `aiLocation` is a separate Bicep parameter from
the other regions. Model deployments must be serialized — Foundry returns 409 on concurrent
creates. Two things need verifying before the pipeline is built on this: the
`web_search_20260209` server tool (used by `fetch_restaurant_menu`, per the 2026-07-23 entry
below) appears to require a "Hosted on Anthropic" deployment on Foundry, which is why the
Bicep pins `model.version: '1'`; and Claude on Foundry bills through Azure Marketplace in
Claude Consumption Units, which free-trial, student and credit-only subscriptions cannot use
at all.

---

## 2026-07-28 — Claude Haiku 4.5 for the vision guess

**Decision:** Use Claude Haiku 4.5 for `vision_guess` (and the same deployment for menu
extraction) rather than a Sonnet- or Opus-tier model.

**Why:** The vision call is explicitly a *preliminary* guess. Its output gets cross-checked
against the restaurant's real scraped menu in the `match_menu_item` fan-in step, and that
match — not the vision model's unaided confidence — is the project's primary
anti-hallucination mechanism. A stronger model would mostly be paying for accuracy that the
menu match already supplies. It is also the highest-volume call in the pipeline, running on
every single photo upload, so it is the wrong place to spend. The heavyweight model spend
belongs on the recipe generator, which CLAUDE.md already identifies as the largest
cost/latency contributor.

---

## 2026-07-28 — Embeddings from Azure OpenAI `text-embedding-3-small`

**Decision:** Generate culinary-technique embeddings with Azure OpenAI
`text-embedding-3-small`, deployed under the same Foundry account as the Claude model.

**Why:** Anthropic has no embeddings endpoint, so the embedding provider was always going to
be a separate choice from the chat/vision model. `text-embedding-3-small` produces 1536-dimension
vectors, which matches the existing `CulinaryEmbeddings.Embedding VECTOR(1536)` column
exactly — no schema migration, no change to `models.EMBEDDING_DIM`, no re-seed beyond
replacing the placeholder vectors. Deploying it on the Foundry account already being
provisioned means one endpoint, one identity and one RBAC grant covering both models, rather
than introducing a third vendor.

**Note:** until this is wired up, both `db/seed_embeddings.py` and
`activities/query_culinary_embeddings.py` use `models.pseudo_embedding()`, a SHA-256 hash —
so vector retrieval is currently returning effectively random neighbours. Replacing it is
Phase 3 Part B work.

---

## 2026-07-28 — Skip SignalR/Web PubSub this phase; keep polling

**Decision:** Do not provision SignalR Service or Web PubSub in Phase 3, despite CLAUDE.md
listing it. The frontend continues to poll `GET /api/jobs/{id}` every 3 seconds.

**Why:** Polling already works end-to-end, and `frontend/src/lib/jobs/useJobPolling.ts` was
built as an explicit swap seam — consumers like `JobScreen` do not change when the polling
body is replaced with a subscription. Provisioning SignalR now would mean a Bicep module, a
negotiate HTTP endpoint, a push from `persist_job_result`, and a new frontend dependency, in
exchange for latency that is not currently a problem. Its Free tier (20 concurrent
connections, 20k messages/day) is also easy to outgrow, so adopting it early risks trading a
working solution for a capped one. Deferred until the real-time experience is worth the
wiring.

---

## 2026-07-28 — One storage account, not the separate Durable Functions account CLAUDE.md specifies

**Decision:** Provision a single storage account serving the `uploads` blob container, the
`jobs` queue, Durable Functions orchestration state, and the Flex Consumption deployment
package — rather than the separate Durable-state account named in CLAUDE.md Phase 3 step 1.

**Why:** Durable Functions does not require a dedicated account. It namespaces its own blobs,
queues and tables by task hub name (`ReplateHub`, set in `backend/host.json`), so there is no
collision with `uploads` or `jobs`. The documented reasons to split are task-hub throughput
contention and isolation between multiple apps sharing a hub, neither of which applies at
MVP scale. Storage has no free tier either way, so a second account is additional wiring for
no cost saving. Splitting later is a parameter change if throughput ever justifies it.

**The real argument for splitting is security, and it is being addressed differently:**
`shared/blob.py` mints SAS tokens with the account key, and that same key protects the
Durable orchestration state. Rather than isolating the blast radius with a second account,
the plan is to move `blob.py` to user-delegation SAS and set `allowSharedKeyAccess: false`,
which removes the shared key entirely.

---

## 2026-07-23 — `fetch_restaurant_menu` real implementation: Claude API + native web-search tool

**Decision:** Implement the real `fetch_restaurant_menu` activity using the Claude API with
the native `web_search_20260209` server tool, prompted to find and extract a restaurant's
menu as structured JSON, rather than a third-party SERP API or scraping service.

**Why:** Validates the AI-calling pipeline locally before Phase 3 infra work, matching the
earlier call to wire real AI calls locally first. It's also what makes the manual
restaurant-search flow (see the GPS-source decision below) meaningful end-to-end — a
manually-selected restaurant needs to return its real menu, not the existing `CANNED_MENUS`
stub. The existing `MenuLastFetchedAt` 24-hour caching logic is preserved completely
unchanged to keep this repeated, per-restaurant AI call from running more than necessary.

---

## 2026-07-23 — Restaurant-name typeahead search: Google Places API (Text Search, server-side)

**Decision:** Power the manual restaurant-search typeahead (shown when an uploaded photo has
no EXIF GPS) with the real Google Places API, called server-side via a new
`GET /api/restaurants/search` endpoint, rather than passing the typed name to an AI web
search per keystroke.

**Why:** Places is purpose-built for fast, structured name+address search-as-you-type —
lower latency and cost than an LLM call per keystroke, and no risk of a hallucinated address.
It's also the same API `CLAUDE.md`'s Phase 3 section already earmarks for real GPS
reverse-geocode later, so this is one integration serving two needs rather than two separate
ones. Called server-side so the client never holds the Places API key. AI web search remains
the right tool for the separate menu-fetching problem (see the entry above) — reading and
extracting from unstructured web pages is a different task than structured place lookup.

---

## 2026-07-23 — GPS source: device location for live capture, EXIF for uploads, manual entry as fallback

**Decision:** Live in-app photo capture uses device geolocation as the restaurant-location
signal. Uploading an existing photo instead prefers GPS read from that photo's EXIF
metadata. If an uploaded photo has no EXIF GPS, prompt the user to manually specify/search
for the restaurant rather than falling back to device location.

**Why:** A live camera frame has no EXIF, so device location is the only real signal there.
But an uploaded photo may have been taken earlier and the user may no longer be at the
restaurant, so the device's current location would misattribute the wrong restaurant — EXIF
reflects where the photo was actually taken and is more accurate for that case. EXIF GPS is
often missing though (screenshots, re-saves, messaging-app recompression, location tagging
disabled), and silently falling back to device location there would just reintroduce the
same inaccuracy problem. The user chose to accept the extra friction of a manual
restaurant-entry step in that case, preferring accuracy over a wrong-but-automatic guess.

---

## 2026-07-22 — Keep a decision log

**Decision:** Maintain this file, and have Claude ask for the reasoning behind engineering/
architecture decisions going forward rather than just executing them.

**Why:** So there's a single place to go back to and talk through the choices made
throughout the project — this is partly a portfolio project, and having the reasoning
written down in one place makes it easier to show future employers the thinking behind why
things were built a certain way, e.g. in job interviews.
