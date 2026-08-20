---
name: Replate
description: Shazam for restaurant dishes — a candlelit, precise, culinary dark UI
colors:
  candlelit-gold: "oklch(76% 0.10 82)"
  gold-hover: "oklch(82% 0.09 82)"
  gold-tint: "oklch(76% 0.10 82 / 0.15)"
  gold-border: "oklch(76% 0.10 82 / 0.5)"
  dark-roast: "oklch(14% 0.008 55)"
  camera-black: "oklch(10% 0.006 55)"
  surface: "oklch(19% 0.012 60)"
  warm-cream: "oklch(93% 0.015 80)"
  cream-bright: "oklch(95% 0.01 80)"
  cream-softer: "oklch(85% 0.015 80)"
  ash: "oklch(62% 0.02 75)"
  ash-light: "oklch(80% 0.02 75)"
  smoke: "oklch(45% 0.01 60)"
  border: "oklch(30% 0.01 60)"
  border-chip: "oklch(35% 0.01 60)"
  border-hairline: "oklch(24% 0.01 60)"
typography:
  display:
    fontFamily: "Pinyon Script, cursive"
    fontSize: "34px"
    fontWeight: 400
    lineHeight: 1.25
    letterSpacing: "normal"
  headline:
    fontFamily: "Playfair Display, Georgia, serif"
    fontSize: "21px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "normal"
  title:
    fontFamily: "Playfair Display, Georgia, serif"
    fontSize: "17px"
    fontWeight: 500
    lineHeight: 1.3
    letterSpacing: "normal"
  body:
    fontFamily: "Manrope, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.55
    letterSpacing: "normal"
  label:
    fontFamily: "Manrope, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "0.1em"
rounded:
  sm: "10px"
  md: "12px"
  lg: "14px"
  xl: "20px"
  pill: "999px"
spacing:
  screen-x: "22px"
  status-bar: "54px"
components:
  button-primary:
    backgroundColor: "{colors.candlelit-gold}"
    textColor: "{colors.dark-roast}"
    rounded: "{rounded.pill}"
    padding: "11px 30px"
    typography: "{typography.label}"
  button-primary-hover:
    backgroundColor: "{colors.gold-hover}"
    textColor: "{colors.dark-roast}"
  chip-active:
    backgroundColor: "{colors.candlelit-gold}"
    textColor: "{colors.dark-roast}"
    rounded: "{rounded.pill}"
    padding: "7px 16px"
  chip-inactive:
    backgroundColor: "transparent"
    textColor: "{colors.ash-light}"
    rounded: "{rounded.pill}"
    padding: "7px 16px"
  card-surface:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.warm-cream}"
    rounded: "{rounded.md}"
    padding: "12px"
  badge-matched:
    backgroundColor: "{colors.gold-tint}"
    textColor: "{colors.candlelit-gold}"
    rounded: "{rounded.pill}"
    padding: "5px 12px"
---

# Design System: Replate

## Overview

**Creative North Star: "The Candlelit Tasting Menu"**

Replate is a fine-dining table after dark. The background is near-black and warm — not cold
UI-grey but the color of dark roast and low candlelight — and against it sits a single flame:
one gold. Dish names are set in a handwritten calligraphic script, the way a name is written
on a place-card or the header of a printed tasting menu; everything else is set in a precise
editorial serif or a quiet functional sans. The room is intimate, the light is low, and the
gold is the only thing that glows.

The personality is **quiet, intimate, and precise** — the authority of a good cookbook and
the hush of a good restaurant, aimed at a casual diner who should never feel out of their
depth. Density is generous and calm: one thing at a time, room to breathe, a phone-width
column even on desktop. The system earns its feeling through restraint, not decoration —
flat surfaces, hairline borders, and gold used as punctuation rather than paint. The one
place light is allowed to bloom is the processing orb, where a live gold glow signals that
the kitchen is working.

This is deliberately **not** a bright, chirpy consumer-food app (no tomato-red, no rounded
cartoon iconography, no busy grids of stock photography), and **not** a cold analytics
dashboard. Warmth and calm are the whole point.

**Key Characteristics:**
- Warm near-black field; every hue lives in the warm band (OKLCH hue 55–82), never cool.
- A single chromatic accent — candlelit gold — used on ≤10% of any screen.
- Three-voice type: script for names, serif for titles, sans for everything functional.
- Flat by default; the only glow in the system is the processing orb.
- Pill geometry for actions, generously rounded cards, circular hairline-gold medallions.

## Colors

A monochromatic warm-neutral field lit by one gold flame. There is no second accent; the
palette's discipline is the identity.

### Primary
- **Candlelit Gold** (`oklch(76% 0.10 82)`): the sole accent. Primary buttons, active states,
  medallion borders, step numbers, the confidence check, the orb. Its scarcity is the point —
  it reads as the light source in the room, not as a brand color splashed everywhere. A
  brighter **Gold Hover** (`oklch(82% 0.09 82)`) lifts it on interaction; translucent
  derivatives (`gold-tint` at 15%, `gold-border` at 50%) tint matched badges and hairline
  borders.

### Neutral
- **Dark Roast** (`oklch(14% 0.008 55)`): the app background — a warm near-black, the color of
  the room after dark. **Camera Black** (`oklch(10% 0.006 55)`) goes one step deeper for
  capture/viewfinder surfaces.
- **Surface** (`oklch(19% 0.012 60)`): raised cards and panels, one tonal step above the
  field; often used as a `155deg` gradient into Dark Roast for a soft top-lit lift.
- **Warm Cream** (`oklch(93% 0.015 80)`): primary text and titles. **Cream Bright**
  (`oklch(95% 0.01 80)`) for the script names that sit over imagery; **Cream Softer**
  (`oklch(85% 0.015 80)`) for long body copy like method steps.
- **Ash** (`oklch(62% 0.02 75)`): secondary text — captions, place names, hints. **Ash Light**
  (`oklch(80% 0.02 75)`) for slightly louder secondary text; **Smoke** (`oklch(45% 0.01 60)`)
  for placeholders and the quietest labels.
- **Borders**: **Border** (`oklch(30% 0.01 60)`) for standard dividers, **Border Chip**
  (`oklch(35% 0.01 60)`) for unselected pills, **Border Hairline** (`oklch(24% 0.01 60)`) for
  the faintest ingredient dividers.

### Named Rules
**The Single Flame Rule.** Candlelit gold is the only chromatic accent and appears on ≤10% of
any given screen. If a screen needs a "second color," the answer is a different tonal step of
the neutral field, never a new hue. The gold's rarity is what makes it read as light.

**The Warm-Band Rule.** Every color in the system sits in the warm OKLCH hue band (55–82). A
cool grey, blue, or true-neutral value is off-system by definition — warmth is not decoration
here, it is the identity.

## Typography

**Display Font:** Pinyon Script (cursive) — the calligraphic accent, reserved for names.
**Headline / Title Font:** Playfair Display (with Georgia, serif fallback).
**Body / Label Font:** Manrope (sans-serif).

**Character:** Three voices, each with one job. The script is a handwritten menu place-card —
intimate, human, used only where a *name* appears. The serif is the printed menu and the
brand's editorial authority. The sans is the calm, legible functional layer that never
competes for attention. Together they read as "a fine restaurant's printed materials," which
is exactly the register a precise-and-culinary voice wants.

### Hierarchy
- **Display / Script** (Pinyon Script, 400, ~30–34px, line-height 1.25): dish titles, the home
  greeting name, the cookbook owner's name. Names only.
- **Headline** (Playfair Display, 500, ~21px): card and section titles (e.g. the Scan card),
  the orb glyph.
- **Title** (Playfair Display, 500, ~17px): the wordmark and smaller serif headings.
- **Body** (Manrope, 400, 13px, line-height ~1.55): method steps, descriptions, result copy.
- **Label** (Manrope, 600, 10–11px, letter-spacing 0.06–0.1em, UPPERCASE): section labels,
  component roles, pending badges, the tagline.

### Named Rules
**The Names-in-Script Rule.** Pinyon Script is used *only* for proper names — a dish's name, a
person's name, a cookbook's name — never for UI labels, buttons, body copy, or numbers.
Because its x-height is small, set it ~1.3× larger than the serif it replaces, add line-height
and ~2px bottom padding so swashes and descenders aren't clipped, and never below ~28px.

**The One-Serif-Voice Rule.** Playfair carries titles and brand marks; it never drops down to
body or label sizes. If text is functional (a button, a field, a caption), it is Manrope.

## Layout

A **mobile-first single column**, hard-capped at `max-width: 480px` and centered even in a
desktop browser — this is a phone app, not a responsive marketing site, so there is no
multi-column desktop reflow. Horizontal screen padding is a consistent **22px**
(`--space-screen-x`); the top of every screen clears the status bar with **54px**
(`--space-status-bar`) of headroom. Vertical rhythm is calm and sectional: a screen is a
stack of comfortably-spaced blocks (10–28px gaps), one idea per block, with generous internal
card padding (12–28px). Content scrolls within the column; full-bleed elements (the recipe
hero image, the camera viewfinder) span the full 480px and use scrims to hand off to the
dark field.

## Elevation & Depth

**Flat by default.** The system uses almost no drop shadows. Depth comes from **tonal
layering** — a raised surface is one OKLCH lightness step above the field, often as a subtle
`155deg` gradient from Surface into Dark Roast that reads as soft top-light — plus **hairline
borders** (gold at 50% opacity on feature cards, neutral elsewhere) and **gradient scrims**
that fade imagery into the background. There is no ambient shadow vocabulary; a card at rest
casts nothing.

The single exception is intentional and signature: the **processing orb's leading dot** carries
a live gold glow.

### Shadow Vocabulary
- **Orb glow** (`box-shadow: 0 0 6px 2px var(--color-gold), 0 0 14px 4px oklch(76% 0.1 82 / 0.75)`):
  used *only* on the ProcessingOrb's travelling dot, pulsing between two intensities. It is the
  one place in the app where light blooms.

### Named Rules
**The Flat-By-Default Rule.** Surfaces are flat at rest and gain separation from tonal
layering and hairline borders, never from a drop shadow. The only glow in the entire system is
the processing orb — do not introduce ambient shadows to "lift" a card.

## Shapes

A **pill-and-medallion** form language. Interactive controls — buttons, chips, badges, search
fields — are fully pill-shaped (`radius-pill`, 999px). Containers use a graduated rounding
scale: **10px** (`sm`) for tight inner surfaces, **12px** (`md`) for standard cards and result
rows, **14px** (`lg`) for thumbnails, and **20px** (`xl`) for feature cards and panels. The
recurring signature silhouette is the **circular gold-hairline medallion** — a perfect circle
with a 1–1.5px candlelit-gold border enclosing a serif glyph or a line-drawn icon (the scan
card's camera, the logo mark, method step numbers, the orb). Icons are thin line drawings in
gold, never filled shapes. Borders are always hairline (1–1.5px); nothing in the system uses a
heavy stroke.

## Components

### Buttons
- **Shape:** fully pill (`radius-pill`, 999px).
- **Primary:** solid Candlelit Gold fill with Dark Roast text, Manrope 700, letter-spacing
  0.03em; compact CTA padding `11px 30px` (~13px), or full-width footer padding `13px 18px`.
  Gold-on-dark is the loudest element on any screen and should appear once per view.
- **Hover / Disabled:** hover lifts the fill to Gold Hover; disabled drops to 0.6 opacity with
  a default cursor. Transitions are short (~0.15s).
- **No secondary "filled" button.** A lower-priority action is a ghost/text treatment or an
  inactive pill, never a second gold fill competing with the primary.

### Chips
- **Style:** pill, Manrope ~12px, 1px border.
- **State:** **active** = solid gold fill, Dark Roast text, gold border; **inactive** =
  transparent fill, Ash Light text, Border Chip outline. Used for cookbook filters.

### Cards / Containers
- **Corner Style:** `md` (12px) for standard list/result cards, `xl` (20px) for feature cards
  (the Scan card) and panels.
- **Background:** Surface, flat — or a `155deg` Surface→Dark Roast gradient on feature cards
  for a soft top-lit lift.
- **Shadow Strategy:** none (see Elevation & Depth). Separation is border + tonal step.
- **Border:** hairline. Feature cards use a 1px **gold** border at 50% opacity; standard cards
  use neutral Border; selected cards switch their border to full Candlelit Gold.
- **Internal Padding:** 12px standard, up to 28px on feature cards.

### Inputs / Fields
- **Style:** pill, Camera Black fill, 1px Border Chip outline, Warm Cream text, Manrope 14px.
  Placeholders are Smoke.
- **Focus:** border shifts toward gold; keep it a border change, not a glow (glow belongs to
  the orb alone).

### Navigation
- **Bottom tab bar:** a `1px` top divider over the dark field, evenly spaced items, each a
  small stacked line-icon (22px, thin 1.5px stroke) + Manrope ~10.5px label. Active state is
  understated: the icon lights **Candlelit Gold** and the label brightens from Ash to Warm
  Cream — no pill highlight, no fill. The active tab carries `aria-current="page"`.

### Signature Components
- **Processing Orb:** a 96px circle with a faint gold track ring, a rotating gold comet-trail
  arc, and a glowing leading dot that pulses as it travels — the one animated, light-emitting
  moment in the app. Reduced-motion slows the spin and stills the dot. Below it, single-line
  Manrope phrases cross-fade to narrate progress.
- **Recipe Hero:** a full-bleed 260px dish image with a bottom scrim fading to Dark Roast, the
  dish name overlaid in large Pinyon Script (Cream Bright), and circular overlay controls
  (back, remove) as dark translucent gold-icon buttons.
- **Confidence Badge:** a pill that surfaces the anti-hallucination outcome — **matched** =
  gold-tint fill, gold hairline border, gold check + Warm Cream text; **unmatched** =
  transparent with a neutral chip border and Ash Light text. It must always be visible on an
  identified dish; never hide which of the three outcomes produced the result.

## Do's and Don'ts

### Do:
- **Do** treat Candlelit Gold as the single light source — one gold moment per screen, ≤10% of
  the pixels, reserved for the primary action, active state, or the confidence signal.
- **Do** keep every color in the warm OKLCH band (hue 55–82); reach for a different tonal step
  before ever reaching for a new hue.
- **Do** reserve Pinyon Script for proper names only, sized ≥28px with descender headroom.
- **Do** convey depth with tonal layering and hairline borders; keep surfaces flat at rest.
- **Do** keep the layout a single 480px-capped phone column, with 22px side padding and 54px
  of status-bar headroom.

### Don't:
- **Don't** introduce a second accent hue, a cool grey, or a true-neutral value — it breaks the
  candlelit identity instantly.
- **Don't** add drop shadows to lift cards; the processing orb's glow is the only bloom of
  light in the system.
- **Don't** set body copy, buttons, numbers, or UI labels in the script or the serif — script
  is for names, serif is for titles, everything functional is Manrope.
- **Don't** place two gold-filled elements in competition in one viewport (two primary buttons,
  or a gold button beside a gold-filled chip).
- **Don't** widen into a multi-column desktop layout or full-bleed marketing grid; this is a
  phone app first, always.
