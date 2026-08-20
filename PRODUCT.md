# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary users are **casual food lovers** — diners out at a restaurant who love good food
and are curious how the dish in front of them is made. They may or may not actually cook it
later. The core situation is: seated at a table, phone in hand, having just been served a
dish they find striking. The job is *"tell me what this is and, when I'm ready, how I'd make
it at home."*

The audience is a **broad consumer** one, but the design bar is set for the casual end —
approachability wins over culinary rigor in the interface, even though the generated recipe
content itself is precise (see Positioning and Brand Commitments).

## Product Purpose

Replate is **"Shazam for restaurant dishes."** A user photographs their meal and shares GPS
location; the app identifies the restaurant, fetches that restaurant's real menu, analyzes
the photo, matches the vision guess against the real menu, and — on a later, deliberate
action — generates a full, reproducible method to recreate each element of the dish at home
(a per-component ingredient list + step-by-step technique, not just a "what is this" label).

Success means a diner can go from photo → correctly-identified dish → a recipe they trust
enough to actually cook, without the AI inventing a dish that isn't on the menu.

## Positioning

Two mechanisms competitors could not truthfully copy without doing the same work:

1. **Menu-matching as the anti-hallucination spine.** The vision model's guess is
   cross-checked against the restaurant's *real, fetched* menu (identified from GPS). A menu
   item's real name and description are trusted over the vision model's unaided guess. This
   is the primary trust mechanism, and it is what separates Replate from "point a vision
   model at a plate and hope." Three confidence outcomes are recorded and surfaced to the
   user: `menu_matched` (high — matched against the real menu), `vision_only_medium`
   (restaurant found, no item matched), `vision_only_low` (no restaurant found).

2. **The deliberate two-stage split: identify now, reverse-engineer later.** Snapping the
   photo *identifies and auto-saves* the dish to a personal cookbook (fast, cheap). The
   heavy, expensive recipe generation ("Reverse engineer") is a separate opt-in action taken
   only when the user actually wants to cook — nobody needs the full method while still
   sitting at the table.

## Operating Context

- **Where it's used:** at the restaurant table (identify), then later at home (reverse-engineer
  and cook). Mobile-first, phone-in-hand.
- **Core flow:** open → (sign in) → Home (recent scans) → Capture → job Processing (stage 1:
  moderation → restaurant + menu + vision + match) → Identified (auto-saved, confidence badge)
  → later open the saved dish → Reverse engineer (stage 2: embedding retrieval + recipe
  generation) → Result (per-component recipe cards).
- **Location sourcing has three branches** that carry real product weight: live camera → device
  geolocation; uploaded photo → EXIF GPS; EXIF absent → manual restaurant search by name
  (device location only biases ranking, the user's tap sets the restaurant).
- **Delivery is polling** today (`GET /api/jobs/{id}` every 3s); a push channel is a documented
  future option, not a current fact.
- The API contract lives in `docs/api.md` and `docs/payload-schemas.json`; the frontend is
  built against it. `docs/user-flow.md` and `docs/decisions.md` are the canonical narrative
  and rationale.

## Capabilities and Constraints

- **Identify (stage 1):** GPS → nearby restaurant candidate(s) → fetch/scrape that
  restaurant's menu, running alongside photo → vision model's preliminary dish/element guess,
  then fan-in to match guess against real menu items. Auto-saves to the user's cookbook
  server-side (no "save this?" prompt; a heart removes a dish).
- **Reverse-engineer (stage 2):** retrieve closest culinary-technique embeddings (in-process
  cosine scan) → generate per-component recreation method grounded in the matched menu item +
  visual details + retrieved technique embeddings. This is the heaviest-output, highest-cost
  call in the pipeline.
- **Personal cookbook:** saved dishes, a "not yet reverse-engineered" badge until the recipe
  is generated, filtering.
- **A failed generation is not a failed job:** stage 2 errors revert the dish to `Identified`
  with an inline retry, never discarding a good identification. `Failed` means stage 1 failed
  (includes a photo rejected by moderation).
- **Content moderation** gates uploaded photos before processing (fail-closed only on an
  explicit unsafe verdict; service errors do not fail the job).
- **Per-user rate limiting** on scans and recipe generations, in separate quotas.
- Terminology to preserve: **identify** vs **reverse-engineer**, **cookbook**, **match_method**
  / the three confidence outcomes, **element/component** (a dish is broken into components,
  each with its own ingredient list and method).

## Brand Commitments

- **Name:** Replate.
- **Positioning line:** "Shazam for restaurant dishes."
- **Voice:** **precise & culinary** — confident, chef-like, technique-respecting; the
  authority of a good cookbook. This is a deliberate counterpoint to the casual-diner
  audience: the *interface* stays approachable while the *content and voice* carry culinary
  authority. Future work must not flatten the recipe content into vague, hand-wavy
  instructions.
- Existing frontend visual implementation (React components + CSS modules under `frontend/src`)
  is the incumbent visual world; it is evidence, not a locked brand constraint, and any
  redesign is governed separately by DESIGN.md / new-work, not this file.

## Evidence on Hand

- **Working software:** a full React frontend (six screens, ~17+ components) and a Python/AWS
  backend pipeline exist and are tested (~133 backend tests). A live stub deploy runs at
  `https://d8j5itd2nds9.cloudfront.net/home` (Phase 3a: real auth + infra live, paid AI
  integrations off — "Reverse engineer" returns stub output until Phase 3b).
- **Documentation:** `README.md`, `docs/api.md`, `docs/architecture.md`, `docs/user-flow.md`,
  `docs/decisions.md`, `CLAUDE.md` (phase plan).
- **No real user testimonials, benchmarks, press, pricing, or usage metrics exist yet** —
  future work must not fabricate them. Sample/demo dish content is illustrative, not real
  user data.

## Product Principles

1. **Trust the real menu over the model's guess.** The menu-match is the product's spine;
   never present an identification or recipe in a way that hides which of the three
   confidence outcomes it came from.
2. **Identify fast, cook later.** Keep the at-the-table identify step cheap and instant;
   reserve the expensive, deliberate work for when the user actually chooses to cook.
3. **Approachable surface, authoritative content.** The interface serves a casual diner; the
   recipe content and voice carry precise culinary authority. Don't let either bleed into the
   other's territory.
4. **Cost discipline is a product feature, not just ops.** The two-stage split, caching, and
   rate limits exist because the AI calls cost real money; product decisions respect that.
5. **A good identification is never thrown away.** Failures in the expensive later steps
   revert gracefully rather than destroying an earlier trusted result.

## Project Context

Replate is **portfolio-first but built to a real, shippable standard** — the immediate
purpose is to demonstrate engineering and design range, so decisions should be
interview-defensible and the craft bar visibly high, while still holding to production-grade
reliability and cost discipline (it is not a throwaway demo).
