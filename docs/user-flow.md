# User Flow

The end-to-end journey through the Replate app, from opening it to seeing a recreated
recipe. The Capture step's location-sourcing branch (live GPS vs. EXIF vs. manual search) is
the most decision-heavy part of the flow — see `docs/decisions.md` for the reasoning behind
each branch.

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
        ExifCheck -->|"Not found<br/>(screenshot, re-saved,<br/>location tagging off)"| Search["Search for the restaurant<br/>by name (Google Places)<br/>device location only biases ranking"]
        Search --> SelectRestaurant["Tap a result to select it"]
    end

    LiveGPS --> Submit["Submit: photo + location<br/>POST /api/jobs, PUT photo to Blob"]
    ExifGPS --> Submit
    SelectRestaurant --> Submit

    Submit --> Job["Job screen — Processing<br/>polls GET /api/jobs/{id}"]

    Job -->|Completed| Result["Result<br/>matched dish + confidence badge<br/>+ per-component recipe cards"]
    Job -->|Failed| Failed["Failed state<br/>with retry"]

    Result --> SaveChoice{"Save to Cookbook?"}
    SaveChoice -->|Yes| Cookbook
    SaveChoice -->|No, done| Home

    Cookbook --> ViewSaved["Open a saved job"]
    ViewSaved --> Result
```

## Notes

- **Live capture** always uses device geolocation — a live camera frame has no EXIF to read.
- **Uploaded photo** prefers EXIF GPS (reflects where the photo was actually taken, which
  matters since the user may no longer be at the restaurant); only falls back to the manual
  search step when EXIF GPS is genuinely absent.
- **Manual search** never silently substitutes device location for the restaurant's
  location — device coordinates only bias which search results rank first. The user's tap is
  what actually sets the job's restaurant.
- **Result confidence** comes from one of three outcomes computed server-side
  (`match_method` in the API response, see `docs/api.md`): `menu_matched` (the vision
  guess was cross-checked against the restaurant's real, fetched menu — the primary
  anti-hallucination signal), `vision_only_medium` (a restaurant was found but no menu item
  matched), or `vision_only_low` (no restaurant found at all). The Result screen's confidence
  badge reflects whichever applies.
