# Decisions

A log of decisions the project owner has made about how Replate is built, and why. Per
CLAUDE.md's global rules, whenever a decision like this comes up Claude asks for the
reasoning first, then adds an entry here — newest first.

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
