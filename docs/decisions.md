# Decisions

A log of decisions the project owner has made about how Replate is built, and why. Per
CLAUDE.md's global rules, whenever a decision like this comes up Claude asks for the
reasoning first, then adds an entry here — newest first.

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
