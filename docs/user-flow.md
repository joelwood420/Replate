# User Flow

The end-to-end journey through the Replate app, from opening it to seeing a recreated
recipe. Two parts carry most of the decisions — the Capture step's location-sourcing branch
(live GPS vs. EXIF vs. manual search), and the split between identifying a dish and
reverse-engineering it. See `docs/decisions.md` for the reasoning behind each.

The headline shape: **snapping a photo identifies and saves the dish; generating the recipe
is a separate, deliberate action later.**

```mermaid
flowchart TD
    Start(["Open app"]) --> Splash["Splash screen"]
    Splash -->|not signed in| SignIn["Sign In<br/>(mocked locally until Phase 3)"]
    Splash -->|already signed in| Home
    SignIn --> Home["Home<br/>recent scans"]

    Home --> Capture["Capture"]
    Home --> Cookbook["Cookbook<br/>saved scans"]

    subgraph CaptureFlow["Capture — choose a location source"]
        direction TB
        Capture --> Choice{"Live camera<br/>or upload a photo?"}
        Choice -->|"Live"| LiveGPS["Device geolocation"]
        Choice -->|"Upload existing photo"| ExifCheck{"EXIF GPS<br/>in the photo?"}
        ExifCheck -->|"Found"| ExifGPS["Use the photo's<br/>EXIF coordinates"]
        ExifCheck -->|"Not found<br/>(screenshot, re-saved,<br/>location tagging off)"| Search["Search for the restaurant<br/>by name (OSM Nominatim)<br/>device location only biases ranking"]
        Search --> SelectRestaurant["Tap a result to select it"]
    end

    LiveGPS --> Submit["Submit: photo + location<br/>POST /api/jobs → PUT photo to Blob<br/>→ POST /api/jobs/{id}/uploaded"]
    ExifGPS --> Submit
    SelectRestaurant --> Submit

    Submit --> Job["Job screen — Processing<br/>stage 1: moderation → restaurant + menu + vision + match<br/>polls GET /api/jobs/{id}"]

    Job -->|Identified| Identified["Dish identified<br/>matched dish + confidence badge<br/>auto-saved to Cookbook<br/>'Reverse engineer' button"]
    Job -->|Failed| Failed["Failed state<br/>with retry<br/>incl. photo rejected by moderation"]

    Identified --> Cookbook
    Cookbook --> ViewSaved["Open a saved dish"]
    ViewSaved --> Identified

    Identified -->|"Tap 'Reverse engineer'"| Generating["Generating<br/>stage 2: vector search + recipe generation<br/>POST /api/jobs/{id}/reverse-engineer<br/>same full-screen loading orb"]
    Generating -->|Completed| Result["Result<br/>per-component recipe cards<br/>ingredients + method"]
    Generating -->|"Generation failed"| Identified

    Cookbook --> ViewRecipe["Open an already<br/>reverse-engineered dish"]
    ViewRecipe --> Result
```

## Notes

- **Live capture** always uses device geolocation — a live camera frame has no EXIF to read.
- **Uploaded photo** prefers EXIF GPS (reflects where the photo was actually taken, which
  matters since the user may no longer be at the restaurant); only falls back to the manual
  search step when EXIF GPS is genuinely absent.
- **Manual search** never silently substitutes device location for the restaurant's
  location — device coordinates only bias which search results rank first. The user's tap is
  what actually sets the job's restaurant.
- **Auto-save** happens server-side the moment stage 1 finishes — there is no "save this?"
  prompt. Photographing a dish already implies wanting to keep it, so the old choice was
  friction with a foregone conclusion. The heart on a dish still removes it.
- **Reverse engineering is opt-in** because generating the method is the heaviest and most
  expensive call in the pipeline, and a user sitting in the restaurant doesn't need it yet.
  Stage 1 stops at `Identified`, and the recipe is generated only when the user opens the
  dish and asks. A cookbook card shows a "not yet reverse-engineered" badge until then.
- **Result confidence** comes from one of three outcomes computed server-side
  (`match_method` in the API response, see `docs/api.md`): `menu_matched` (the vision
  guess was cross-checked against the restaurant's real, fetched menu — the primary
  anti-hallucination signal), `vision_only_medium` (a restaurant was found but no menu item
  matched), or `vision_only_low` (no restaurant found at all). This badge now appears at the
  `Identified` stage, *before* any recipe exists — it is what makes a freshly-saved cookbook
  entry meaningful on its own.
- **A failed generation is not a failed job.** Stage 2 errors revert the dish to `Identified`
  with the error shown inline beside a working retry button, so a transient model error never
  throws away a good restaurant identification and menu match. `Failed` means stage 1 failed.
