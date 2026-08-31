# Decisions

A log of decisions the project owner has made about how Replate is built, and why. Per
CLAUDE.md's global rules, whenever a decision like this comes up Claude asks for the
reasoning first, then adds an entry here — newest first.

Entries are never deleted. When a later decision reverses an earlier one, the earlier entry
is marked **superseded** and left in place — a log that hides its own reversals is worth
less than one that shows where the thinking changed.

---

## 2026-09-01: The vision food gate runs before restaurant lookup and menu fetch, not in parallel

**Decision:** `dish-identify` no longer fans the vision guess out in a `Parallel` state alongside
restaurant lookup and menu fetch. The vision guess now runs alone, right after moderation, as a
food gate: `Moderate -> Vision -> is_food? -> (stop | restaurant lookup -> menu fetch -> match)`.
A non-food photo ends the job before any geocode or paid menu fetch runs. The state-machine data
paths move with it (`$.parallel[0]` / `$.parallel[1]` become `$.vision`, `$.restaurant` and
`$.menu`).

**Why:** a non-food photo (the last prod scan was a blister pack of pills) was still triggering a
real SerpApi search and a Claude menu extract, because the paid menu branch ran concurrently with
the vision guess and was only short-circuited at the join, after the spend. Making the cheap
vision call gate the expensive ones, the same way moderation already gates vision, drops menu
spend to zero on every non-food photo. The cost is latency: the menu fetch no longer overlaps the
vision call, so a food photo whose menu is not cached waits the vision call's few seconds before
the fetch starts. Given the menu fetch is the ~45s long pole and the vision call is a low-effort
Sonnet call, that overlap was worth little, and not spending money on junk input is worth more.

**Context worth recording:**

- Moderation stays off in prod for now (the Phase 3a stub, `MODERATION_ENABLED` false), so the
  vision food gate is currently the first check that actually runs.
- Geocode (free Overpass) now runs only for food photos too. It could have stayed parallel with
  vision since it is free, but the rule chosen was simpler and stricter: if it is not food,
  nothing else runs.

---

## 2026-09-01: The menu match keeps a confidence floor on top of the Claude classifier

**Decision:** The menu-match step stays a Claude in-context classifier (pick the single best
menu item or none) with a numeric confidence floor layered on top: a positive pick must clear
`MENU_MATCH_CONFIDENCE_THRESHOLD` (default 0.6) to record `menu_matched`; below it, or a "none",
degrades to `vision_only_medium`. The floor is deliberately kept, not dropped in favour of
trusting the classifier's own item-or-none verdict alone. Separately,
`docs/identify-pipeline.md` now models only the post-submit, fire-and-forget pipeline; the
interactive steps (location sourcing, re-shooting a not-food photo) are documented as pre-submit
frontend behaviour, because a polled Step Functions execution cannot stop to prompt or loop.

**Why:** the classifier can return a confident-looking but wrong pick, and this match is the
anti-hallucination spine of the product, so a cheap second guard earns its place. "We are not
sure" (the medium badge) is a more honest result than a bad match shown as definitive, and the
floor is one dial to tune matching strictness without touching the prompt. The diagram split
reflects how the system is actually built: prompting and retries live in the app before submit,
not as pipeline states, so drawing them inside the pipeline misrepresented it.

**Context worth recording:**

- The owner initially expected the match to be "just a Claude call"; retaining the floor was a
  deliberate call for defense in depth, not a leftover.
- A `difflib` character-similarity matcher remains the fallback when the model is unconfigured
  (stub deploys), so the step always yields one of the three outcomes and never fails the job.

---

## 2026-08-26: Removing a dish is a hard delete, not a soft un-save

**Decision:** The trash control on a dish (in the Cookbook and on the dish detail screen) now
**permanently deletes** the job - a new `DELETE /api/jobs/{jobId}` endpoint (`job_delete_http`
+ `repository.delete_job`) removes the job's whole partition (META, RESULT, every ELEMENT#) and
the owner's cookbook listing projection. There is no soft-hide and no undo. The endpoint is
ownership-guarded and refuses (409) to delete a scan that is still in flight (Queued /
Processing / Generating) - stopping a live scan stays the job of Cancel. The old
`setJobSaved(false)` "remove from cookbook" path (which just flipped `is_saved` to hide the
row) is retired from the frontend. `is_saved` itself stays: the pipeline still sets it true on
auto-save at identification, and the Cookbook still reads it.

**Why:** removing a dish has no undo either way, so a soft-hide just leaves dead rows
accumulating in DynamoDB - pointless data the user can never see or recover. The soft-save/
un-save model was leftover from an earlier design that had a heart-to-favourite gesture; with
that gone, "remove" should mean delete. This also fixes the concrete bug that surfaced it: the
2026-08-26 "scan lands in the cookbook" change made Failed scans appear in the Cookbook but
gave them no working remove control (they're `is_saved=false`, so an un-save was a no-op), so
failed scans piled up with no way to clear them.

**Context worth recording:**

- **Hard delete is right for a failed scan specifically:** a failed job holds no identified
  dish and no recipe, so there is nothing worth keeping - deleting it outright is the honest
  action, not hiding it.
- **In-flight deletes are blocked server-side,** not just hidden in the UI, so a delete can't
  orphan a running Step Functions execution (which could otherwise re-create partial rows as it
  finishes).
- The backend `PATCH /jobs/{jobId}/save` endpoint is now unused by the client but left in place;
  retiring that Lambda/route is a separate cleanup, and `is_saved` is still live.

---

## 2026-08-26: Scanning lands in the Cookbook, not a dedicated processing screen; photos are permanent

**Decision:** After a scan (camera or upload) the app navigates straight to the **Cookbook**
instead of the full-screen `/jobs/:id` processing view. The just-scanned dish appears as a
Cookbook card that processes **in place** - the captured photo under a dim scrim with the
loading orb over it - and resolves to its normal state when identification finishes. Tapping
a still-processing card opens the full-screen processing view, which is now a **plain
near-black screen with the orb, the reassuring copy and a Cancel control** and **no photo
behind it** (the old identify-stage view put the photo behind a scrim; that is removed). The
top-left control on that screen is a **back arrow** (was a close X). A **failed** scan now
surfaces as a Cookbook card in a "Scan failed - retry" state that opens the retry screen when
tapped; **cancelled** scans are hidden from the Cookbook. The **"Recently Identified" list on
the Home screen is removed entirely** (Home is now just the greeting and the Scan card), as it
duplicated the Cookbook. Separately, uploaded photos are **no longer expired** from the S3
uploads bucket - the `ExpireUploads` lifecycle rule is removed so a saved dish keeps its photo
indefinitely.

**Why:** sitting in a restaurant, snapping a dish and being dropped on a processing-orb screen
makes it feel like you have to sit and wait for the scan to finish. Landing in the Cookbook
with the dish already there and quietly processing gives an instant "it's saved, I'm done, I
can put my phone away" feeling - the identification finishes on its own and the result is
waiting whenever you come back. The photo-behind-the-orb full screen was disliked visually, so
the tap-through processing view is the calmer plain-orb treatment. Photos were disappearing
from older dishes because the uploads bucket deleted objects after 7 days; a cookbook of dishes
you saved to cook later is worthless if the photo vanishes, so the dish photo must persist.

**Context worth recording:**

- **The "Recently Identified" removal** followed an `/impeccable critique` of that list (baseline
  18/36): because dishes auto-save at capture, Home's list and the Cookbook read the same cache
  and overlapped almost entirely, and the list was where duplicate rows and broken thumbnails
  were most visible. Rather than polish a redundant surface, it was cut.
- **Photo permanence is a cost tradeoff** (Global Rule 1). Removing `ExpireUploads` means the
  uploads bucket grows without bound; S3 has no always-free storage tier (5 GB free for 12
  months only), so this is an accepted, flagged cost. A future refinement is to expire only
  *orphaned* uploads (scans that were never saved / were cancelled) rather than everything, but
  lifecycle rules cannot read DynamoDB save state, so that needs object tagging and is deferred.
- Already-deleted photos (dishes older than 7 days at the time of this change) are **not
  recoverable**; the fix is forward-looking only.

---

## 2026-08-25: Menu fetch follows linked menus (PDFs and sub-pages) when the HTML page has no dishes

**Decision:** `menu_extraction` extracts the fetched page's own content first (with the full
remaining budget), and **only when that yields no dishes** follows the menus it links to: it
detects menu links, ranks the food/menu ones above drinks/kids, and follows up to
`MENU_LINKS_MAX_FOLLOW` (default 4), fetching and extracting each - whatever it turns out to be,
a PDF, an image, or an HTML menu page - and merging/de-duplicating items by name. A "menu link"
is either a `.pdf` href (any host) or a **same-host page whose URL path reads as a menu**, which
catches menus served at pretty, extensionless URLs. `page_fetch` surfaces the ranked links on
its HTML result and sorts out PDF-vs-HTML per target; the whole thing stays under the same
menu-fetch budget. HTML-first (rather than links-first) is deliberate - see "Why the ordering".
Separately, `SERPAPI_TIMEOUT_SECONDS` was raised 10 -> 20 after a scan lost its whole menu to a
slow (>10s) SerpApi call; the budget and Lambda timeout leave room to wait.

**Why:** a real scan of Baduzzi (2026-08-25) found the restaurant and its menu page but matched
no dish. The page (`baduzzi.co.nz/our-menus-2/`) is a WordPress shell whose real menus are
separate files: the set menus are `.pdf` links (followed, matched), but the **a-la-carte** menu
- the one the diner's dish was actually on - is served at `baduzzi.co.nz/menu1-2/`, a pretty URL
with **no `.pdf` extension** that nonetheless returns `Content-Type: application/pdf`. `page_fetch`
would have read it correctly as a PDF; the gap was that link detection only surfaced hrefs
ending in `.pdf`, so that URL was never followed. Detecting same-host menu-path links closes the
gap, and generalizes: many sites serve menus at extensionless URLs or as HTML sub-pages.

**Context worth recording:**

- **Why the ordering (HTML-first).** Following the links before extracting the page's own text
  would let a slow or empty linked menu consume the budget and starve an extraction that would
  otherwise have succeeded from the already-fetched HTML - a page that both shows a menu and
  links others could regress to vision-only. Extracting the page first, with the full budget,
  removes that risk; the follow only runs when the page genuinely has no dishes.
- **A transient follow failure retries, it does not cache a false "no menu".** If every followed
  link fails to *fetch or extract* transiently (a network or model error, as opposed to one that
  genuinely lists no items) and nothing else yielded a menu, the step raises `MenuExtractionError`
  so the next job retries - preserving the raise-don't-cache contract the primary fetch upholds.
  A link that cleanly extracts to zero items is a real empty result and is cached like any other.
- **Same-host only for path-matched pages; `.pdf` links may be cross-host.** Path-matched menu
  pages are restricted to the restaurant's own domain so we do not chase a site's social/nav
  links; a `.pdf` link is followed even cross-host, since menus are sometimes hosted on a CDN.
  Menu-word matching is on the URL *path*, not the query, so API links (`/wp-json/oembed?url=...menu`)
  are excluded.
- **Bounded by design.** Following is capped (`MENU_LINKS_MAX_FOLLOW`, default 4) and gated on the
  remaining budget, so a page linking many menus costs at most a few extra fetch+extract calls,
  not an unbounded sweep - the same discipline that replaced the web_search thrash. 4 covers a
  site's food + set + a-la-carte menus; restaurant sites rarely host unrelated PDFs.
- **Merges multiple menus.** Food, set and a-la-carte menus are often separate files, so items
  from the top few are merged (de-duped by name) to give the matcher more real dishes.

---

## 2026-08-25: The menu match is an in-context LLM classifier, not a difflib string match

**Decision:** `activities/match_menu_item.py` now matches the vision guess to the restaurant's
menu with a small in-context LLM classifier (`generate_structured`, effort low, model
`ANTHROPIC_MATCH_MODEL`, default `claude-sonnet-5`): it is handed the vision guess plus the one
restaurant's numbered menu and returns the best item's index or -1 for "none", with a
confidence, which maps onto the existing three outcomes against the same
`MENU_MATCH_CONFIDENCE_THRESHOLD`. The model may only pick a listed item or none - never invent
one - so the anti-hallucination property holds, and an out-of-range index is coerced to
"none". The old `difflib` character matcher is kept as a fallback for a stub deploy (no key) or
a failed/errored call, so the step always yields one of the three outcomes and never fails the
job.

**Why:** the owner's - `difflib.SequenceMatcher` compares characters, so it misses matches
where the same dish is written differently ("The Classic Benny" vs "Eggs Benedict"): near-zero
character overlap scored as no match, silently downgrading a real menu hit to the lower-
confidence vision-only outcome. An LLM matches on meaning and fixes exactly that, while the
"choose only from this menu or none" constraint keeps it from inventing a dish.

**Context worth recording:**

- **Not embeddings.** The match is against ONE restaurant's short menu, so a vector store /
  embedding provider is overkill and would pull in the paid embedding dependency deliberately
  deferred to Phase 6. An in-context classifier needs neither.
- **Cost.** This adds one small structured call per scan that finds a menu (previously the
  match was free and local) - tiny input and output, cents at most, `effort` low to keep it
  cheap. `ANTHROPIC_MATCH_MODEL` is the lever; a missing key costs nothing (difflib fallback).
  `MatchMenuFunction` gains `ssm:GetParameter` on `replate/*` to read the key.

---

## 2026-08-25: Photo upload has its own screen, separate from the camera capture flow

**Decision:** Uploading a photo no longer routes into `CaptureScreen`. A new `UploadScreen`
(`/upload`) owns the upload flow: it shows the chosen photo, takes the location from the
photo's **EXIF GPS**, and when the photo has none, asks the user to search for the restaurant.
It never opens the camera and never requests device geolocation. `CaptureScreen` is now
camera-only (live viewfinder + device GPS); its uploaded-mode branches, EXIF reading, and
camera/upload mode toggles are removed. Home's "Upload a photo" navigates to `/upload`.
`useGeolocation` also gained an `enabled` flag as a safety net so device location is only ever
requested by the camera path.

**Why:** the owner's - dropping an uploaded photo into the camera-oriented capture screen was
confusing: it wore camera chrome (viewfinder, shutter, flip) and, worst of all, prompted for
device location, which an upload should never do. An upload should "just upload." Splitting the
two flows makes each screen do one thing: the camera uses the device's GPS, an upload uses the
photo's own EXIF (or a manual restaurant pick), and neither leaks the other's behaviour.

**Context worth recording:**

- **The manual restaurant search stays, for uploads with no EXIF location.** It is not camera
  chrome - it is the only way to give the pipeline a restaurant to match the menu against, so a
  location-less upload does not silently collapse to the low-confidence vision-only outcome.
- **Supersedes the 2026-08-?? "upload runs inside Capture" arrangement** (PR #15 moved the
  upload entry point onto the Home scan card but kept it pointed at `CaptureScreen`); the entry
  point stays on Home, now pointed at the dedicated screen.

---

## 2026-08-25: Scans process in the background with a Cancel, and cancelling is its own state

**Decision:** A scan no longer traps the user on a full-screen loader. After capture the dish
page shows the just-taken photo with the orb over it, honest "this usually takes under a
minute - you can leave" copy, and two controls: leave (the scan keeps running and the dish
shows a "still processing" pulse in the Home list, updating live) or **Cancel scan**, which
stops the identify state-machine execution so no further model spend accrues. A cancelled scan
becomes a new terminal status, **CANCELLED**, distinct from FAILED. A new endpoint
`POST /jobs/{jobId}/cancel` stops the execution and sets the status; the SQS starter also skips
a job cancelled while still QUEUED. No timed auto-redirect.

**Why:** the owner's:

- **Let the user stop money being spent.** The scan is where a menu fetch and the vision call
  cost tokens; a Cancel button is the escape hatch for a scan that is dragging or was a
  mistake, rather than watching spend accrue with no way out.
- **Background, not a wait.** Forcing the user to stare at a loader is the thing to remove. The
  live-updating Home list makes leaving safe, so the "background processing" feel comes from
  the list, not from kicking the user off the page.
- **No timed redirect.** A timer that yanks the user to Home mid-glance was considered and
  rejected: it feels janky at any interval, and since the result lands on the dish page it
  would only add a tap to get back to it. Leaving is offered, never forced.
- **CANCELLED over reusing FAILED.** A deliberate cancel is not an error; giving it its own
  status keeps it out of the red error screen and out of failure metrics, and lets the list
  hide it from "recently identified" the same way FAILED is hidden.

**Context worth recording:**

- **Scope is the identify scan only for now.** Recipe generation (GENERATING) is a separate,
  user-initiated stage and is not cancellable through this endpoint yet - a noted follow-up.
- **Execution ARN is derived, not stored.** Cancel reconstructs the execution ARN from the
  state-machine ARN + the job-id-derived execution name (`shared/sfn.execution_arn`), so no
  new persisted field was needed at StartExecution time.

---

## 2026-08-25: Menu fetch is a deterministic SerpApi pipeline, not an Anthropic web_search sweep

**Decision:** Replace the first-party `web_search` menu-fetch call with a deterministic,
wall-clock-bounded pipeline: **SerpApi** (Google engine) finds the restaurant's menu-page URL
from its name + address, `shared/page_fetch.py` fetches that one page (HTML, PDF or image), and
one cheap tool-free Claude structured-extract call (`generate_structured`, no server tool)
reshapes it into menu items. The whole step is bounded by `MENU_FETCH_BUDGET_SECONDS` (default
45s, below the now-60s fetch-menu Lambda timeout). SerpApi is queried first with the OSM
`website` tag as a fallback URL hint; the SerpApi key lives in SSM as a `SecureString`
(`/replate/serpapi-key`). This supersedes the menu-fetch **mechanism** of the 2026-08-17 entry;
the broader "model calls go through the first-party Anthropic API" decision there still stands
(vision, extract and recipe generation all remain first-party Anthropic calls), and the
2026-08-24 budget/reformat fixes are subsumed by this (there is no web_search sweep left to
bound or to reformat around).

**Why:** the owner's, three reasons:

- **Cost.** The `web_search` sweep was the pipeline's dominant cost — it kept searching and
  re-reading pages server-side (each read re-billed across pause-turn resumes), running to
  dollars per scan even after the 2026-08-24 caps. SerpApi is ~$0.01–0.015 per lookup and the
  one extract call is cents (a PDF menu ~$0.01–0.03, an image ~$0.005), so a first-ever scan
  drops well under the prior figure and a cached repeat costs nothing.
- **Latency / UX.** The sweep hit the 120s Lambda ceiling and timed out (the 2026-08-24
  Baduzzi incident). SerpApi + fetch + extract completes in seconds, and the hard budget means
  a slow restaurant degrades to vision-only in well under a minute instead of hanging.
- **Reliability.** `web_search` was effectively location-blind — it burned budget deciding
  *which* restaurant before looking for a menu — and gave up on menus that are PDFs, images or
  JS/aggregator pages. Grounding on name + address and fetching the page directly (with native
  PDF/image reading by Claude) fixes both root causes: it skips the "find the site" thrash and
  handles the formats most real menus actually use.

**Context worth recording:**

- **SerpApi is a new paid dependency with a small free tier** (~100 searches/month; overage
  moves to a paid plan — re-verify current terms, Global Rule 5). Free-tier protection comes
  from caching, not from avoiding SerpApi: the existing 24h `MenuLastFetchedAt` gate means a
  restaurant is searched once and reused, and a genuine "no menu online" result is cached as a
  successful empty menu (a negative cache) so it does not re-burn a search each scan.
  `MENU_CACHE_TTL_HOURS` is the lever to stretch the free tier further if needed.
- **SerpApi-first, not OSM-first.** OSM's `menu_source_url` is only the map entry's `website`
  tag — often missing or a generic homepage — so it is a fallback hint, not the primary source;
  SerpApi finds the real menu page (including Google's hosted menu and aggregators) wherever it
  lives.
- **Graceful-degrade posture preserved.** A missing key, a SerpApi error with no fallback URL,
  or the budget running out raises `MenuExtractionError` (not cached, retried next job); a clean
  "no menu found" returns an empty list (cached). Both surface downstream as the vision-only
  medium-confidence match, exactly as before. `web_search_completion` and the `WEB_SEARCH_*`
  config are kept as generic infrastructure (a candidate for the Phase 6 recipe-grounding
  alternative), not on the menu path.

---

## 2026-08-24: A slow menu fetch degrades to vision-only, never fails the scan

**Decision:** The menu web_search now runs under a wall-clock budget
(`WEB_SEARCH_TIMEOUT_SECONDS`, default 75s) that sits **below** the fetch-menu Lambda's
120s timeout, enforced across pause-turn resumes inside `web_search_completion`. When the
budget is exceeded it raises `AnthropicError`, which the caller already degrades to the
vision-only outcome. Also: lower the pause-turn resume cap 5 → 2, and raise the Lambda root
logger to INFO at cold start (`config.py`, override `LOG_LEVEL`) so the model usage/timing
logs actually appear.

**Why:** a real scan failed on 2026-08-24 with `replate-fetch-menu` hitting
`Sandbox.Timedout` at exactly 120.00s **twice** (initial + retry). The restaurant, vision and
geocode all succeeded in seconds; only the menu web_search hung. Root cause: the Anthropic
client timeout defaulted to 120s — **equal to** the Lambda timeout — so the Lambda was killed
at the same instant the client would have raised, meaning the graceful vision-only degrade
could never fire and a slow menu became a hard `Failed` scan. Making the client budget strictly
smaller than the Lambda timeout restores the safety net: a slow restaurant menu yields a
vision-only result (scan succeeds) instead of failing. The INFO-logging fix was needed because
the function emitted zero application logs — every `logging.info`, including the usage
diagnostics added the same day, was silenced by Lambda's default WARNING level.

---

## 2026-08-24: Menu-fetch parse failures reformat, never re-search

**Decision:** When the `web_search` menu-fetch call returns text that does not parse as clean
JSON, coerce that already-gathered text into the schema with a second, **tool-free** structured
call (`generate_structured`, which guarantees schema-valid JSON) instead of re-running the whole
`web_search` sweep. The web_search sweep now runs at most once per menu fetch. Also: cap web
searches per fetch with `WEB_SEARCH_MAX_USES` (default lowered 5 → 3, now env-tunable), drop the
Step Functions `FetchRestaurantMenu` retry from 2 attempts to 1 (the activity already degrades a
fetch failure to an empty menu internally, so a task-level failure is an infra hiccup, not a menu
miss), remove the now-unused `MENU_FETCH_MAX_RETRIES` knob, and log `usage` (input/output tokens +
web_search count) on every model call.

**Why:** the old parse-retry loop re-invoked `web_search_completion` from scratch on each failure,
each attempt spending a fresh 5-search budget — one dish scan was observed burning **15 searches
(5 × 3 attempts)** and multi-million input tokens (every read page re-billed across pause-turn
resumes), costing roughly $1–2 for a single scan and taking minutes. web_search responses routinely
carry citations/prose and cannot use structured outputs, so parse failures were common, not rare.
Reshaping the model's own text tool-free removes the re-search entirely: target cost drops to about
$0.15 for a first-ever scan of a restaurant and ~$0.02 for a cached repeat, an ~10× reduction, with
per-call usage now visible in logs instead of arriving as a surprise bill.

---

## 2026-08-23: Splash is a boot gate, not a routed timer screen

**Decision:** Replace the `/`-only splash screen (a fixed 2.4s timer that then navigated to
Home/Signin) with an `AppBootGate` mounted above the router. It shows the splash on every fresh
page load regardless of the entry URL, runs the boot work in the background (Cognito session
restore, then the first job-list fetch for a signed-in user), and reveals the app only once boot
is genuinely done AND a 2.4s minimum has elapsed. The Cognito auth provider no longer blank-holds
during restore (it exposes `isReady` instead); `JobsProvider` exposes `hasLoadedOnce`; `/` becomes
a redirect to Home/Signin. It fires once per page load, never on in-app tab navigation.

**Why:** the old splash only appeared at `/`, so opening or refreshing any other URL
(`/cookbook`, `/profile`) skipped it, and its 2.4s timer was decoupled from actual loading, so you
often landed on a screen that then showed a "Loading..." spinner. Gating reveal on real readiness
means the first screen is ready with no spinner, which reads as much lower latency (even the
half-second refresh flush on Cookbook is now absorbed by the splash). The 2.4s floor is kept
deliberately so the branding always has time to register rather than flashing by on a warm load.

---

## 2026-08-23: Profile edit persists server-side via new `/profile` endpoints

**Decision:** Wire the profile "Edit profile" row to real backend persistence rather than a
client-only edit. Add `GET /profile` and `PUT /profile` (Lambdas `triggers/profile_http.py`,
one route each in the SAM template), backed by the `USER#<oid> / PROFILE` item the single-table
design already reserved. Scope is the **display name** only: `email` is the Cognito sign-in
identity (changing it is a separate identity operation) and is shown read-only; profile photo is
deferred (needs S3-upload plumbing). DynamoDB `display_name` is the source of truth, and the
frontend also updates the in-memory auth session on save so the greeting/avatar reflect the new
name immediately.

**Why:** the user chose full backend integration so a renamed profile survives a reload and
across devices, not just in one browser session, and it demonstrates an end-to-end persisted
CRUD path for the portfolio. The PROFILE item and `repository.ensure_user` already existed, so
this only added a read/update helper pair and two thin routes rather than new data modelling.

**Cost (Global Rule 1):** two more Lambdas + two HTTP API routes. Lambda's 1M requests/month is
always-free; the HTTP API free tier is 12-month (then ~$1/million requests); DynamoDB access is
via the execution role on the existing provisioned table. No new standing or hourly cost.

---

## 2026-08-23: Frontend job list is one shared, stale-while-revalidate cache

**Decision:** Home and Cookbook no longer fetch `GET /api/jobs` independently on every mount.
A single `JobsProvider` (mounted above the router) fetches the user's full job list once with a
cap high enough to hold the whole list (`limit=1000`) and holds it; `useRecentJobs` and
`useSavedJobs` became pure client-side derivations (slice newest N / filter `is_saved`) over that
one cache. The cache is
stale-while-revalidate: it renders instantly on every tab visit and refreshes in the background,
so the loading spinner shows only on the first load, and a failed background refresh keeps the
stale data instead of erroring. It prefetches as soon as the user authenticates, and the save
toggle updates the cache optimistically.

**Why:** navigating to a tab re-showed a full-screen "Loading..." spinner every time because the
fetch hook restarted from `isLoading: true` with no cache, which made tab swiping feel slow. The
backend (`repository.list_jobs`) already reads the whole job partition on every call and applies
`saved`/`limit` in memory, so one capped read costs the same DynamoDB RCU as a single old fetch
while feeding every tab view. Collapsing to one shared read plus SWR removes the per-visit
spinner and makes tab switching feel instant, at no extra backend cost.

**Context worth recording:**
- Routes are statically imported, so the component code was never the bottleneck; the fetch was.
  Caching, not code-preloading, was the right lever.
- The cap must cover the user's ENTIRE list, not just a page. Because the Cookbook's `is_saved`
  filter now runs client-side over this one read, a smaller cap (e.g. 100) would silently drop a
  saved dish that sits outside the newest-N total jobs, even when the user has few saved items -
  the old server-side `saved=true` query filtered before applying the limit, so it never had this
  problem. `limit=1000` is therefore "effectively all jobs"; if a user ever exceeds it the fix is
  real server-side paging, not a bigger number.

---

## 2026-08-22: Phase 5 testing in CI (pytest + Vitest on every PR, Playwright e2e post-deploy)

**Update 2026-08-23 (supersedes the e2e cadence below):** e2e now runs **manually only**
(`workflow_dispatch`), not post-deploy. A half-finished happy-path run cost over $1 versus
~12c for a normal recipe generation, so an automatic run on every deploy was not worth the
spend. Trigger it by hand to validate the live journey. The rest of this entry (unit tests on
every PR, real ESLint) still stands.

**Decision:** Wire the existing backend pytest suite (unit via moto, integration via LocalStack)
and a new frontend Vitest suite into `ci.yml` so both run on every pull request, and add real
ESLint (typescript-eslint + react-hooks) as a frontend lint gate replacing the tsc-only `lint`
script. A new lean Playwright e2e suite (one full happy-path journey plus two no-cost failure
paths) runs against the deployed prod stack after the deploy workflows succeed on `main`
(`e2e.yml`, triggered by `workflow_run`), not as a pre-merge check.

**Why (e2e post-deploy on main):** running e2e against the real prod deployment is the truest
signal that the live journey works end to end, and current merge/deploy volume is low enough
that the per-run Anthropic cost (real vision, menu web_search, and recipe generation on
`claude-sonnet-5`) is acceptable for now. It cannot be a pre-merge gate because there is no
staging environment yet (the app only exists once deployed), so an e2e failure is treated as an
alert or rollback trigger rather than a merge blocker. That gap closes when staging is introduced.

**Why (real ESLint):** a real lint gate is expected of a production-quality repo and signals
engineering discipline for a portfolio project, catching what `tsc --noEmit` alone does not
(react-hooks dependency rules and unsafe patterns).

**Context worth recording:**
- The e2e suite is kept lean deliberately (one happy path, plus unauthenticated-redirect and
  bad-login), because only the happy path spends Anthropic money; the two failure paths are free.
- E2E uses a pre-provisioned demo Cognito user (admin-created, permanent password) driven through
  the in-app `/signin` form, not the hosted UI. Its email and password are GitHub Actions secrets
  (`E2E_USER_EMAIL`, `E2E_USER_PASSWORD`); a post-run cleanup step deletes that user's DynamoDB
  job items so e2e data does not pollute real usage metrics.
- The backend and frontend unit jobs are intended to be required status checks on `main`; e2e is
  not, since it runs post-deploy.

---

## 2026-08-22: CI/CD via GitHub Actions and OIDC, deploying the SAM stack as one unit

**Decision:** Automate Phase 4 deployment with GitHub Actions, prod only. Merges to `main`
deploy the whole SAM stack (`deploy-infra.yml`) and publish the React site
(`deploy-frontend.yml`); every pull request runs a minimal check (`ci.yml`: `sam validate
--lint`, a frontend `npm run build`, and a backend compile check); a manual `teardown.yml`
deletes the stack for cost control. GitHub authenticates to AWS through an OIDC federated IAM
role, not stored access keys. That role and the GitHub OIDC provider are created by a separate,
hand-deployed CloudFormation stack (`infra/github-oidc.yaml`), and the role is scoped to only
the services this stack manages. There is no separate backend deploy workflow: the Lambda
functions and their infrastructure are one SAM stack, so one `sam deploy` ships both. The
frontend workflow reads its build-time config (API URL, Cognito pool and client ids) from the
deployed stack's outputs rather than from stored copies.

**Why:** OIDC removes the standing risk of long-lived AWS keys sitting in GitHub secrets, which
is the explicit Phase 4 requirement. The deploy role cannot live in the application stack it
deploys (it is what grants permission to deploy that stack), so it needs a small separate
bootstrap stack; keeping that as its own CloudFormation template rather than console clicks
keeps it reproducible and reviewable. A scoped role over a broad power-user one demonstrates
least privilege and limits blast radius, accepting that a future new resource type may need the
policy widened (a deploy-time AccessDenied makes that gap obvious). Folding the backend into the
infra deploy avoids a second workflow racing the first over the same stack. Deriving the
frontend config from stack outputs at build time means the site can never drift from the
infrastructure it talks to, and keeps Cognito/API values out of committed files. The PR check is
deliberately minimal (lint plus build, no pytest or LocalStack) because Phase 4 only needs to
catch obvious breakage; the full unit and e2e suites are Phase 5.

**Context worth recording:**
- Non-secret config (region `ap-southeast-2`, stack name `replate`, the deploy role ARN) is
  stored as GitHub Actions variables. No Actions secrets are needed: OIDC replaces keys and the
  Anthropic key stays in SSM Parameter Store.
- The teardown workflow does not delete the SSM SecureString or the bootstrap OIDC stack, so
  redeploying later does not require recreating either.

---

## 2026-08-22: GPS restaurant lookup uses OpenStreetMap Overpass, not Google Places

**Decision:** Implement the GPS-to-nearby-restaurants lookup (`geocode_restaurant_candidates`)
against OpenStreetMap's Overpass API instead of Google Places, with a best-effort Claude
web_search fallback when Overpass is unavailable or returns nothing. Overpass needs no API key
and no billing account. The manual name-search path (`restaurant_search_http`) still calls
Google Places and is unchanged for now.

**Why:** Google Cloud requires a billing account to use the Places API, which the project owner
did not want to set up. Overpass is free and key-less, which also removes the "wire a Google
Places SSM key" task from the infra work and fits the project's cost-discipline rule. The
tradeoff is coverage: OSM is strong in cities and patchier in rural areas, and the public
Overpass instance is fair-use and rate-limited, so production-scale use would mean self-hosting
or a paid instance later. The Claude fallback reuses the web_search tool already wired for menu
fetch, so a transient Overpass failure still yields candidates rather than dropping straight to
the no-restaurant outcome. Distance is computed in-process with a haversine, since Overpass
returns coordinates but not distance.

---

## 2026-08-22: Vision guess wired to a real model (Claude Sonnet 5)

**Decision:** Wire the stage-1 vision guess (`vision_guess`, the preliminary dish/element
breakdown read from the uploaded photo) to a real Anthropic call on Claude Sonnet 5
(`claude-sonnet-5`), replacing the canned, hash-picked stub. It runs at `effort="low"`, reads
the photo from the uploads bucket, base64-encodes it into an image block, and returns a
structured breakdown. A blank `ANTHROPIC_VISION_MODEL` still degrades to the stub so local
runs and the smoke test need no model spend.

**Why:** Sonnet 5 balances quality and cost on what is the frequent, at-the-table stage-1
call, and its accuracy is backstopped by the menu match (`match_menu_item`), which trusts the
restaurant's real menu over the vision guess. Frontier-level naming precision is therefore not
needed here, since a wrong guess is corrected downstream. Reusing the same model the recipe
generator already runs (see 2026-08-18) keeps it to one model and one cost profile to reason
about. Claude Haiku 4.5 was considered as a cheaper option and stays a valid future switch if
per-scan cost becomes a concern; Claude Opus 5 was judged overkill for a guess that gets
corrected by the match step. No infrastructure change was needed: the vision Lambda already
held S3 read and SSM read permissions, and the call reuses the existing account API key.

---

## 2026-08-20 — Cookbook filter chips removed rather than made functional

**Decision:** Delete the `Mains / Sauces / Desserts` filter chips from the Cookbook screen
outright (leaving the dish grid and the header summary), rather than wiring them up or
keeping a lone `All` chip.

**Why:** The chips were a false affordance — they repainted on tap but never filtered
(`visibleJobs = jobs` unconditionally), because no whole-dish category field exists on the
backend (a component's `role` and the dish `cuisine` are neither of them a Mains/Sauces/
Desserts taxonomy). A control that responds but does nothing erodes trust. The honest
alternative considered was a status filter (`All / To cook / Cooked`) backed by the existing
`job.status`, but that adds a feature beyond a distill pass, and the header summary
("N dishes · M reverse-engineered") already surfaces that split; removal was chosen as the
leanest fix that stops the UI from lying. The `FilterChip` component itself is kept — it is a
documented design-system primitive and may back a real filter later. Surfaced by an
`/impeccable critique` of the frontend (P1 finding).

---

## 2026-08-18 — Recipe generation model: Claude Sonnet 5

**Decision:** Wire the "Reverse engineer" step (`generate_recreation`, the stage-2 recipe
generator) to a real Anthropic call on **`claude-sonnet-5`**, via structured outputs
(`output_config.format`). Deployed to prod ahead of the rest of Phase 3 — the vision and
menu models stay stubbed/key-gated for now. Kept as the `AnthropicGeneratorModel` parameter
so the model is a one-line change per environment.

**Why:** This is the heaviest-*output* call in the pipeline, and output tokens dominate its
cost. Sonnet 5 and Opus 5 are the same quality tier for this task — producing per-component
ingredient lists and method steps from a known dish is culinary knowledge plus structured
formatting, not deep reasoning — but Sonnet 5's output is $15/MTok vs Opus 5's $25, so Opus
would mostly add cost for marginal polish on a home-cook recipe. Sonnet 5 also supports
`output_config.format` (Sonnet 4.6 does not), which pins the element/ingredient/step schema
and removes fragile JSON parsing. It matches the menu-fetch model already in use, so there's
one capability profile and one cost line to reason about, consistent with the project's
AWS/model cost-discipline rule. Haiku was ruled out: this is the app's headline feature and
Sonnet's stronger grounding is worth the gap. If recipe volume ever makes the ~30%
new-tokenizer token premium matter, `ANTHROPIC_GENERATOR_MODEL` flips to 4.6 or Haiku with
no code change.

---

## 2026-08-17 — Model calls go through the first-party Anthropic API, not Amazon Bedrock

> **Menu-fetch mechanism superseded by the 2026-08-25 SerpApi entry.** The "single call using
> the server-side `web_search` tool" described below was replaced by a deterministic SerpApi +
> page-fetch + structured-extract pipeline. The broader decision — that Claude calls go through
> the first-party Anthropic API — still stands; only the web_search-for-menu mechanism changed.

**Decision:** Route Claude calls through the **first-party Anthropic API** (`anthropic` SDK,
`ANTHROPIC_API_KEY`), reversing the 2026-08-14 Bedrock decision. Menu extraction goes back to a
single call using Anthropic's server-side **`web_search`** tool, so the SERP
search→fetch→extract split (`shared/web_search.py`) and the SERP API key are removed. Supersedes
the 2026-08-14 **Bedrock** and **SERP API** decisions; reinstates the shape of the 2026-07-23
native-`web_search` menu-fetch decision.

**Why:** Two reasons, the owner's:

- **The native `web_search` tool.** Bedrock does not expose it; the first-party API does. That
  tool is what let `fetch_restaurant_menu` find, fetch and extract a menu in one call — the whole
  reason it had to be split into three stages on Bedrock. Going back to the Anthropic API
  collapses the split and deletes a module and a stored key.
- **Setup/billing simplicity for a portfolio demo.** One API key and no per-model, per-region
  Bedrock console access grant (the manual step CloudFormation can't do). One AI vendor line to
  reason about.

**Context worth recording:**

- **This is a plumbing swap, not a rewrite.** The only live model call today is menu extraction;
  `vision_guess` and `generate_recreation` are still canned stubs, so `shared/bedrock.py` becomes
  `shared/anthropic_client.py` and only `menu_extraction.py` changes behaviour. The blank-key
  posture is preserved: with no `ANTHROPIC_API_KEY`, menu fetch raises `MenuExtractionError` and
  the pipeline degrades to the vision-only medium-confidence outcome — exactly as the blank
  Bedrock model id did.
- **The trade-off, accepted knowingly:** an API key now lives in Parameter Store as a
  `SecureString`, giving up Bedrock's IAM-only, zero-stored-key story (the very thing the
  2026-08-14 Bedrock entry valued). It's the one stored credential the model calls introduce;
  everything else (S3, DynamoDB, SQS, Rekognition) still authenticates by IAM. Calling an
  external HTTPS API needs no VPC/NAT — Lambda has default internet egress (Global Rule 1).
- **Embeddings stay a pseudo-embedding stub.** Anthropic has no embeddings endpoint, so rather
  than keep Bedrock alive just for Titan, Bedrock is dropped entirely and the SHA-256
  `pseudo_embedding` stub stands until embeddings are actually wired — the real provider is a
  later, separate choice.
- **Menu model can't be Haiku 4.5 with the modern tool.** The `web_search_20260209` tool
  (dynamic filtering) requires Sonnet 4.6+/Opus 4.6+; Haiku 4.5 only has the basic
  `web_search_20250305`. So the 2026-07-28 "Haiku 4.5 for menu extraction" cost call can't stand
  as-is. `ANTHROPIC_MENU_MODEL` defaults to **`claude-sonnet-5`** (supports the modern tool); the
  24-hour menu cache keeps the per-call cost infrequent. Falling back to Haiku 4.5 + the basic
  tool is the cheaper option if cost ever bites.
- **Pricing note (Global Rule 5, re-verify):** the first-party API is pay-per-token with no free
  tier, same as Bedrock was; the recipe generator remains the heaviest call and the two-stage
  split plus the separate recipe quota are what contain it. `web_search` is billed per search on
  top of tokens — check the current rate before the real wiring.

## 2026-08-17 — Custom in-app Cognito auth UI instead of the hosted UI

**Decision:** Build sign-up, email verification, and sign-in as Replate's own React screens,
talking to the existing Cognito user pool via the browser SDK (`amazon-cognito-identity-js`,
SRP auth), rather than redirecting to Cognito's hosted UI. Account creation opens an in-app
onboarding form (name + email + password) with a verification-code step; "Continue with Google"
stays a placeholder. This replaces the `react-oidc-context` hosted-UI redirect that Phase 3a
first wired.

**Why:** The hosted UI is a generic AWS-styled page that breaks Replate's dark, mobile-first
aesthetic and yanks the user out of the app mid-flow. For a portfolio project, a custom auth UI
that matches the design and keeps the user in-app demonstrates materially more than redirecting
to a stock page — and it's the natural home for the name/email/password fields the onboarding
flow needs. It costs no infra change: the deployed app client already allows
`ALLOW_USER_SRP_AUTH`, is a public client (`GenerateSecret: false`), and permits self-signup
with email verification, so the SDK works against the existing pool and the tokens it issues
pass the same API Gateway JWT authorizer (audience = the same client id).

**Context worth recording:**

- **No backend or template change.** `shared/auth.py` still reads the verified `sub`; the
  authorizer is unchanged. Only the frontend provider and the two auth screens changed.
- **Mock parity preserved.** `VITE_COGNITO_ENABLED=false` keeps a full fake flow (sign-up →
  any 6-digit code → sign-in) so the UI can be built and demoed locally without a real pool or
  email codes, mirroring the backend's stub-auth seam.
- **Real Google sign-in is out of scope** and still requires a Cognito hosted-UI redirect
  (`identity_provider=Google`); the button is inert for now.
- **Known gotcha recorded:** `amazon-cognito-identity-js` references Node's `global`, absent in
  the browser — shimmed once in `frontend/index.html` (`window.global ||= window`) so the SDK
  loads under Vite.

## 2026-08-14 — Split Phase 3: deploy the infrastructure with stubs (3a) before wiring the real AI (3b)

**Decision:** Break CLAUDE.md's combined "Phase 3 — Infra + AI feature" into two passes. **3a**
provisions the full AWS stack via SAM and deploys it with every paid external call stubbed or
disabled — Bedrock (blank model ids), Rekognition (`MODERATION_ENABLED=false`), SERP + Google
Places (placeholder keys), Titan embeddings (the existing SHA-256 pseudo-embedding). **3b**
swaps those stubs for the real integrations. The stub deploy runs the whole two-stage pipeline
end-to-end in the cloud, returning canned data.

**Why:** Deploying the plumbing before the AI logic isolates failure domains and serves three
concrete goals: (1) build a working understanding of how the app behaves on real AWS — IAM
execution roles, Step Functions ↔ Lambda ARN wiring, the Cognito JWT authorizer, API Gateway
CORS, presigned S3 uploads — the parts that can't be exercised against LocalStack; (2) stand up
a demoable environment early (the identify → reverse-engineer flow, real screens, real sign-in)
without spending a token on Bedrock or SERP; and (3) produce the deployed stack that Phase 4's
CI/CD pipeline needs as a deployment target. A green 3a deploy means any failure in 3b is in the
model-calling code, not the infrastructure.

**Context worth recording:**

- The line is drawn at **cost, not infra realism**: everything free-tier (Lambda, API Gateway,
  Step Functions, DynamoDB, SQS, S3, CloudFront, Cognito, IAM) is real in 3a; only
  pay-per-token / pay-per-call services are held back. Stubbing the money rather than the
  plumbing keeps the free-tier posture intact while still exercising the great majority of the
  stack.
- The stubs already **degrade gracefully** — menu fetch raises `MenuExtractionError` → the
  vision-only medium-confidence outcome; moderation disabled → every photo `unchecked`/allowed —
  so the pipeline reaches `Identified` and `Completed` with the paid calls off.
- CLAUDE.md's Phase 3 step 2 (grant Bedrock model access) and step 4 (finalize the AI feature)
  move wholesale into 3b; step 5 (real Cognito auth) is pulled *forward* into 3a — see the front
  door entry below.
- Teardown is a single `sam delete` (empty the S3 buckets first). Most of the stack scales to
  zero, so the stub environment carries no standing cost between demos.

---

## 2026-08-14 — Deploy region: ap-southeast-2 (Sydney)

**Decision:** Deploy the production stack to `ap-southeast-2` (Sydney), replacing the `eu-west-2`
(London) placeholder currently in `backend/.env.example`.

**Why:** Sydney is the closest AWS region to the owner, minimising round-trip latency for the
live demo. The app is interactive — photo upload, direct-to-S3 PUT, 3-second job polling — and
reads partly on how responsive it feels when shown, so region proximity is the cheapest latency
win available and costs nothing.

**Context worth recording:**

- **Verified before committing** (Global Rule 5, don't assume availability): Amazon Bedrock is
  available in `ap-southeast-2`, and Titan Text Embeddings V2 lists Sydney in its
  regional-availability table — the embedding model the design depends on is present in-region.
- **Caveat for 3b:** the newest Claude models are often reached in APAC through a **cross-region
  inference profile** (`apac.anthropic.*`) rather than a strict in-region endpoint. The exact
  Claude model id / inference profile for Sydney must be confirmed in the Bedrock console when
  3b wires real model calls, and model access must be granted per-model in the **Sydney** console
  (the manual step CloudFormation can't perform).
- **No cost impact for 3a:** the stub deploy makes no Bedrock/Rekognition calls, so region only
  determines where the free-tier infra lands. Free-tier grants are per-region-account and
  identical in Sydney, so nothing about the free-tier posture changes with the move from London.

---

## 2026-08-14 — Phase 3a front door: API Gateway HTTP API with a real Cognito JWT authorizer

**Decision:** The deployed API is an API Gateway **HTTP API** fronted by a **Cognito JWT
authorizer**, and real Cognito sign-in is wired on both ends from the first (3a) deploy — rather
than shipping the stub deploy behind the `X-Debug-User-Oid` header, and rather than Lambda
Function URLs.

**Why:** Cognito is free-tier, so real auth costs nothing and is *infrastructure*, not a paid
integration — it belongs on the "real plumbing" side of the 3a/3b line. Shipping it in 3a means
the demo has genuine sign-in and the API is not a public, spoofable, unauthenticated endpoint.
API Gateway's JWT authorizer validates the token for free (no per-handler JWT code), which is
exactly the seam the backend was already written against — handlers read `sub` from the
authorizer claims. Choosing the HTTP API over Function URLs keeps that free authorizer and clean
path-based routing.

**Context worth recording:**

- **Trade-off accepted (Global Rule 1):** API Gateway's free tier is the **12-month** kind, not
  always-free. Fine at this stage; if per-request cost ever bites, the documented fallback is
  Lambda Function URLs with in-handler JWT validation — the cost is losing the free authorizer,
  noted here so the exit is known.
- This pulls CLAUDE.md Phase 3 **step 5** (real Cognito JWT validation) *forward* into 3a.
  `shared/auth.py`'s `NotImplementedError` path (guarded by `COGNITO_ENABLED`) gets its real
  implementation now, and the frontend flips from the mock to the real OIDC client against the
  deployed pool.
- The stub boundary is unaffected: auth being real doesn't make any paid AI call fire.

---

## 2026-08-14 — Move the whole project from Azure to AWS

**Decision:** Rebuild Replate on AWS — Lambda + Step Functions, DynamoDB, S3, SQS, Cognito,
Bedrock — replacing Azure Functions, Durable Functions, Azure SQL, Blob/Queue Storage, Entra
External ID and Microsoft Foundry. The product design, the two-stage pipeline and the API
contract are unchanged; only the platform underneath moves.

**Why:** AWS is where the owner's study is currently focused. Replate doubles as a portfolio
and interview artifact, so it should be built on the cloud they are actively learning — the
project is worth more when the platform it demonstrates is the one they can talk about in
depth.

**Context worth recording:**

- **Nothing had been deployed to Azure.** Phase 3's Bicep was written but never executed, and
  Phases 1-2 ran entirely against local emulators. So there was no data to migrate, no DNS to
  cut and no users to move — this was the cheapest moment the migration would ever have.
- The original constraints carry over unchanged: **serverless everywhere, stay in the free
  tier.** AWS arguably serves them better, since Lambda, DynamoDB, SQS, Step Functions and
  CloudFront all have *always-free* monthly grants rather than 12-month trials.
- The pipeline shape survives the move almost exactly. The two Durable orchestrators map 1:1
  onto two Step Functions state machines, including the parallel vision/menu branch and the
  menu-match fan-in.
- Cost of the move, honestly: the entire data layer is rewritten (see the next entry), the
  orchestrators are re-expressed in ASL, and `fetch_restaurant_menu` loses the tool it was
  built on (see the Bedrock and SERP entries). Roughly 133 tests need repointing, though most
  mock at the `shared/` boundary and survive.
- The port is tracked as **Phase 0** in `CLAUDE.md` and must have a green test suite before
  Phase 3 (real infrastructure) begins.

---

## 2026-08-14 — DynamoDB single-table, with vector search moved into the Lambda

**Decision:** Replace Azure SQL — 11 relational tables plus a native `VECTOR(1536)` column —
with a single DynamoDB table. Culinary-technique embeddings live in their own partition and
are scanned brute-force with numpy inside the Lambda rather than by the database.

**Why:** It is the only option that stays inside an *always-free* tier. DynamoDB grants 25 GB
plus 25 provisioned RCU/WCU with no 12-month cliff, whereas every relational option on AWS
either expires (RDS free tier, 12 months, then a fixed hourly instance) or never had a free
tier at all (Aurora Serverless v2). Given that the free-tier constraint was explicit, a
relational engine would have meant paying to keep a database idle.

**Context worth recording:**

- **Every access pattern in the app was already a key lookup** — job by id, jobs by user,
  restaurant by place id, rate counters by user and hour bucket. Nothing needed a join, which
  is why single-table design fits without a GSI, and is the reason this was a viable choice
  rather than a forced one.
- Two things get **better** than the SQL version. Rate limiting becomes an atomic `UpdateItem`
  with `ADD` plus native TTL expiry — no read-modify-write race and no counter cleanup job,
  which the `RateLimitCounters` table needed. And the newest-first job listing falls out of a
  `JOB#<ts>#<jobId>` sort key, replacing `ORDER BY` plus the `IX_Jobs_UserId` index.
- Moving the vector scan into the process is **less of a change than it looks**. CLAUDE.md
  already specified brute-force `VECTOR_DISTANCE` with no index, because the corpus is a few
  hundred rows; DiskANN was never in play. The scan just moves from the database to the
  Lambda. If the corpus ever outgrows that, a real index is a Future item.
- Embedding dimension changes 1536 → 1024 with the move to Titan V2. This stopped being a
  schema concern the moment vectors left the database — it is now just a constant.
- **The capacity mode is the trap.** The free tier covers *provisioned* capacity only;
  on-demand tables bill per request from the first request. This is written into CLAUDE.md's
  Global Rule 1 because it is silent, easy to get wrong, and only visible on the bill.
- Rejected: Aurora Serverless v2 + pgvector (no free tier; scale-to-zero still bills on any
  sustained traffic) and RDS Postgres free tier (12 months, and an always-on instance is not
  serverless — it broke both stated constraints).

---

## 2026-08-14 — Model calls go through Amazon Bedrock

> **Superseded by the 2026-08-17 Anthropic API entry.** The IAM-only, zero-stored-key argument
> below is exactly what was given up to regain the native `web_search` tool and a simpler
> one-vendor setup.

**Decision:** Route all Claude calls — vision guess, menu extraction, recipe generation — and
the embedding calls through Amazon Bedrock, rather than the first-party Anthropic API.
Supersedes the 2026-07-28 Microsoft Foundry decision.

**Why:** The same reasoning that chose Foundry on Azure: one cloud, one bill, one identity
story. Bedrock authenticates through the Lambda's IAM execution role, so there is **no API
key to store, rotate or leak** — one fewer `SecureString` in Parameter Store and one fewer
thing that can be committed by accident.

**Context worth recording:**

- This choice has a **real cost**, accepted knowingly: Bedrock does not expose Anthropic's
  server-side `web_search` tool, which `fetch_restaurant_menu` was built on and which
  currently works. See the next entry for what replaces it.
- Bedrock has **no free tier** — it is pay-per-token. The recipe generator remains the
  heaviest-output call in the pipeline and therefore the most likely line item to actually
  cost money, which is exactly what the two-stage split (2026-07-30) and the separate recipe
  quota (2026-08-05) were designed to contain.
- Model access must be granted per-model, per-region in the Bedrock console before the first
  call — a manual step CloudFormation cannot perform, so it is called out in Phase 3.
- Embeddings move to Titan Text Embeddings V2 (1024-d) for the same IAM-not-keys reason,
  superseding `text-embedding-3-small`.
- The Azure version of this decision was also partly forced: Foundry's Claude deployments are
  unavailable on free-trial, student and credit-only subscriptions, which was live friction.
  Bedrock has no equivalent eligibility gate.

---

## 2026-08-14 — Menu search: third-party SERP API, splitting one tool call into three steps

> **Superseded by the 2026-08-17 Anthropic API entry.** Moving back to the first-party API
> restores the native `web_search` tool, so the split collapses to one call again and the SERP
> key is gone. This entry's own "rejected: keep the Anthropic API for this one activity" is, in
> effect, what was adopted — for the whole pipeline, not just this activity.

**Decision:** `fetch_restaurant_menu` becomes **search** (a third-party SERP API) → **fetch**
(HTTP GET the top result) → **extract** (Bedrock Claude, structured output), replacing the
single Claude call that used the native `web_search` server tool. Supersedes the 2026-07-23
menu-fetch decision.

**Why:** Forced by the Bedrock decision above — the native tool simply isn't available there.
Given that the step had to be rebuilt anyway, an explicit search/fetch/extract chain is the
better shape: each step is independently testable and mockable, the search provider is
swappable, and the per-call cost is visible per step instead of hidden inside one opaque
tool-using call.

**Context worth recording:**

- **The extraction prompt survives nearly unchanged** — it was already "turn this page text
  into structured menu items". Only the acquisition of the page text is new code.
- The 24-hour `MenuLastFetchedAt` cache gate is unaffected and matters more now, since a cache
  miss costs a search call plus a fetch plus a model call rather than one call.
- The SERP API key is the **only** new stored credential the AWS migration introduces;
  everything else moved to IAM. It goes in Parameter Store as a `SecureString`.
- Rejected: keeping the Anthropic API for this one activity (would have preserved a working
  implementation, but left a lingering API key and a split model story that undercuts the
  whole reason for choosing Bedrock), and a Bedrock Knowledge Base web crawler (built for
  known seed URLs rather than ad-hoc lookups, and needs a vector store with real fixed cost).

---

## 2026-08-14 — Infrastructure as code: AWS SAM, not CDK

**Decision:** Replace the Bicep tree with an AWS SAM template. The Bicep is deleted, not
ported — it is recoverable from git history at commit `07354af`.

**Why:** Study alignment, the same reason behind the migration itself. **SAM *is*
CloudFormation** — a template transform producing an ordinary CloudFormation stack — so it
teaches the stacks, change sets, intrinsic functions and drift concepts that AWS
certification tracks actually test. CDK largely abstracts those away.

**Context worth recording:**

- **Why not CDK**, which was the initial recommendation on "same language as the backend"
  grounds: it weights developer ergonomics over the stated reason for being on AWS at all.
  CDK also needs a Node.js toolchain and a bootstrap stack in the account just to deploy
  Python, and adds a synth step between the source and the deployed artifact.
- **Step Functions is genuinely better under SAM.** The ASL lives in its own `.asl.json` file
  referenced by `DefinitionUri`, so the state machine stays readable and diffable, instead of
  being reconstructed through a Python DSL.
- **Why not raw CloudFormation**, which was the owner's initial instinct and is entirely
  viable at this size: the 12 Lambda handlers would mean 12 copy-pasted function + IAM role +
  log group blocks with no loop construct. SAM's `Globals:` and policy templates collapse that
  while leaving every non-serverless resource — CloudFront, Cognito, DynamoDB — as plain
  CloudFormation in the same file. Nothing is given up.
- `sam local start-api` / `sam local invoke` also replaces `func start` in the dev loop, which
  matters more than it sounds: LocalStack Community does not emulate Bedrock, Rekognition or
  Cognito, so a good local invoke story fills a real gap.
- One packaging gotcha to remember: `sam build` produces a separate zip per function, so
  shared dependencies belong in a `LayerVersion`, not the function package.

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

> **Superseded by the 2026-08-14 Bedrock entry.** The reasoning below — one cloud, one bill,
> one identity story — is exactly what carried over to Bedrock; only the cloud changed.

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

> **Superseded by the 2026-08-14 Bedrock entry.** Now Titan Text Embeddings V2 at 1024
> dimensions. The dimension-matching argument below no longer applies: vectors left the
> database with the move to DynamoDB, so the width is a constant rather than a column type.

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

> **Still current, amended 2026-08-14.** The decision holds — the client still polls, and
> `useJobPolling.ts` is still the seam. Only the named alternative changes: on AWS the push
> option would be API Gateway WebSockets or AWS IoT Core over MQTT, not SignalR.

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

> **Superseded by the 2026-08-14 migration entry — moot rather than reversed.** Step Functions
> keeps its own execution state, so there is no orchestration-state store to co-locate or
> separate. S3 holds uploads, SQS holds the job queue, and the shared-key concern that drove
> this entry disappears with presigned URLs signed by the Lambda's role.

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

> **Superseded by the 2026-08-14 SERP API entry.** Bedrock does not expose the native
> `web_search` server tool, so this became search → fetch → extract. This is the one place
> where the migration cost working functionality.

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
