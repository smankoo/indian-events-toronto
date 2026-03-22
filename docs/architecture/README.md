# Indian Events Toronto — Architecture Documentation

> arc42 + C4 documentation for the automated Indian event discovery and social media publishing pipeline.
>
> **Last updated:** March 2026

---

## Table of Contents

1. [Introduction and Goals](#1-introduction-and-goals)
2. [Constraints](#2-constraints)
3. [Context and Scope (C4 Level 1)](#3-context-and-scope-c4-level-1)
4. [Solution Strategy](#4-solution-strategy)
5. [Container View (C4 Level 2)](#5-container-view-c4-level-2)
6. [Component View (C4 Level 3)](#6-component-view-c4-level-3)
7. [Runtime View](#7-runtime-view)
8. [Deployment View](#8-deployment-view)
9. [Crosscutting Concerns](#9-crosscutting-concerns)
10. [Architecture Decisions](#10-architecture-decisions)
11. [Quality Requirements](#11-quality-requirements)
12. [Risks and Technical Debt](#12-risks-and-technical-debt)
13. [Glossary](#13-glossary)
14. [Developer Guide — Where to Make Changes](#14-developer-guide--where-to-make-changes)

---

## 1. Introduction and Goals

### What This App Does

This is an **automated pipeline** that discovers Indian cultural events in the Toronto/GTA area and publishes them to Instagram and Facebook. It runs unattended on GitHub Actions twice daily.

The pipeline:
1. **Scrapes** event listings from Sulekha (an Indian community events site)
2. **Filters** to Toronto/GTA area events only
3. **Classifies** each event as "Indian" or not using an LLM (Gemini)
4. **Generates** professional Instagram post images (1080×1350) using Playwright
5. **Publishes** to Instagram and Facebook via their Graph APIs
6. **Updates** a static link-in-bio page deployed to GitHub Pages

### Stakeholders

| Role | Concern |
|------|---------|
| Account owner | Content quality, posting frequency, audience growth |
| Developers | Where to make changes, how the pipeline works |
| GitHub Actions | Reliable automated execution twice daily |

### Quality Goals

| Priority | Goal | Measure |
|----------|------|---------|
| 1 | **Relevance** | Only genuinely Indian events get posted (no Afghan, Sri Lankan, generic club nights) |
| 2 | **Visual quality** | Generated images look professional, use real artist photos (not event posters with text overlays) |
| 3 | **Reliability** | Pipeline runs unattended; failures don't corrupt state |
| 4 | **Cost efficiency** | Uses cheapest viable LLM (Gemini Flash Lite via OpenRouter) |

---

## 2. Constraints

### Technical Constraints

| Constraint | Rationale |
|------------|-----------|
| Python 3.12 | GitHub Actions runtime; uv for package management |
| SQLite | Single-file database committed to git; no external DB needed |
| Playwright + Chromium | Renders HTML→PNG for crisp text; PIL text rendering is blurry |
| GitHub Actions | Free CI/CD; no server to maintain |
| Instagram Graph API | Requires public image URL (can't upload directly); uses freeimage.host as CDN |
| 2 posts per run | Rate-limited to avoid spamming followers |

### Organizational Constraints

| Constraint | Detail |
|------------|--------|
| Single data source | Currently only scrapes Sulekha (adding more sources is straightforward) |
| Instagram token refresh | Long-lived tokens expire ~60 days; workflow auto-refreshes them |
| No backend server | Everything is static files + GitHub Actions; link-in-bio is a generated HTML page |

---

## 3. Context and Scope (C4 Level 1)

### System Context Diagram

```
                                    ┌─────────────────────────────────────┐
                                    │    Indian Events Toronto Pipeline   │
                                    │         (GitHub Actions)            │
                                    └──────────┬──────────────────────────┘
                                               │
              ┌────────────────────────────────┼────────────────────────────────┐
              │                                │                                │
              ▼                                ▼                                ▼
    ┌──────────────────┐            ┌─────────────────┐              ┌──────────────────┐
    │   Data Sources   │            │   AI Services   │              │  Publishing      │
    │                  │            │                  │              │  Destinations    │
    │ • Sulekha.com    │            │ • OpenRouter     │              │                  │
    │ • Wikipedia      │            │   (Gemini Flash) │              │ • Instagram API  │
    │ • Wikidata       │            │                  │              │ • Facebook API   │
    │ • Spotify API    │            │                  │              │ • GitHub Pages   │
    │ • MusicBrainz    │            │                  │              │ • freeimage.host │
    │ • DuckDuckGo     │            │                  │              │                  │
    └──────────────────┘            └─────────────────┘              └──────────────────┘
```

### External Interfaces

| System | Direction | Purpose | Auth |
|--------|-----------|---------|------|
| **Sulekha** | Inbound | Scrape event listings + detail pages | None (public HTML) |
| **OpenRouter** | Outbound | LLM classification (Gemini 2.5 Flash Lite) + vision checks | `OPENROUTER_API_KEY` |
| **Instagram Graph API** | Outbound | Publish photo posts | `INSTAGRAM_ACCESS_TOKEN` + `INSTAGRAM_USER_ID` |
| **Facebook Graph API** | Outbound | Cross-post photos to Page | `FACEBOOK_PAGE_ACCESS_TOKEN` + `FACEBOOK_PAGE_ID` |
| **freeimage.host** | Outbound | Host uploaded images (Instagram requires public URLs) | Hardcoded API key |
| **Wikipedia / Wikidata** | Outbound | Artist photo lookup (identity-verified) | None |
| **Spotify API** | Outbound | Artist photo fallback | `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` |
| **MusicBrainz** | Outbound | Artist identity → Spotify ID mapping | None |
| **DuckDuckGo Images** | Outbound | Fallback image search | None |
| **GitHub Pages** | Deployment | Static link-in-bio page | Git push |

---

## 4. Solution Strategy

| Decision | Approach | Why |
|----------|----------|-----|
| **Event source** | Scrape Sulekha JSON-LD | Structured data (schema.org), comprehensive GTA coverage |
| **Classification** | LLM with detailed system prompt | Nuanced cultural classification; regex/keyword matching would miss too much or over-include |
| **Image generation** | HTML/CSS → Playwright screenshot | Crisp text, flexible layouts, CSS-based responsive design |
| **Image sourcing** | Multi-source waterfall (Wikipedia → Wikidata → Spotify → DuckDuckGo) | Identity-verified sources first, then broad search with text-overlay rejection |
| **Storage** | SQLite committed to git | Zero infrastructure; portable; full history in git |
| **Deployment** | GitHub Actions cron | Free, reliable, no server maintenance |
| **Image hosting** | freeimage.host | Instagram API requires public URLs; free CDN |

---

## 5. Container View (C4 Level 2)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        GitHub Actions Runner                        │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌───────────┐   ┌───────────────┐  │
│  │ Scraper  │──▶│Classifier│──▶│  Image     │──▶│  Publisher    │  │
│  │          │   │          │   │  Generator │   │               │  │
│  │sulekha.py│   │indian_   │   │            │   │instagram.py   │  │
│  │          │   │classifier│   │create_post │   │facebook.py    │  │
│  │          │   │.py       │   │image_search│   │linkinbio.py   │  │
│  └──────────┘   └──────────┘   │styles.py   │   └───────────────┘  │
│       │              │         │artist_image│         │             │
│       │              │         │_sources.py │         │             │
│       ▼              ▼         └───────────┘         ▼             │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    SQLite Database                            │  │
│  │                    data/events.db                             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌────────────┐                                                     │
│  │ main.py    │  ◀── Pipeline orchestrator                         │
│  │            │      Coordinates all steps                          │
│  └────────────┘                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Containers

| Container | Technology | Purpose |
|-----------|------------|---------|
| **main.py** | Python | Pipeline orchestrator — runs steps in sequence |
| **scraper/** | BeautifulSoup, requests | Fetches + parses Sulekha event listings |
| **classifier/** | OpenAI client → OpenRouter | LLM-based event classification + title cleanup |
| **image_generator/** | Playwright, Pillow, ddgs | Finds artist images + renders Instagram post PNGs |
| **publisher/** | requests (Graph APIs) | Publishes to Instagram, Facebook, and generates link-in-bio |
| **data/** | SQLite | Persistent event storage, dedup tracking, post status |
| **docs/** | Static HTML | Generated link-in-bio page (GitHub Pages) |

---

## 6. Component View (C4 Level 3)

### 6.1 Scraper (`scraper/sulekha.py`)

```
scrape_events()
    │
    ├── scrape_listing_page()     ── GET listing page, parse JSON-LD
    │                                  Returns: list of raw event dicts
    │
    ├── parse_listing_event()     ── Extract title, date, venue, price from JSON-LD
    │
    └── scrape_detail_page()      ── GET each event's detail page
                                     Extract: hi-res image URL, description,
                                     categories, languages, organizer
```

**Key details:**
- Source URL: `https://events.sulekha.com/toronto-metro-area`
- Parses `<script type="application/ld+json">` blocks (schema.org Event type)
- Image priority: `header2` (1280×500) → `root` → `header` → `thumbnail`
- Rate-limited: 0.5s delay between detail page requests
- Retry logic: 3 attempts with exponential backoff on listing page

### 6.2 Classifier (`classifier/indian_classifier.py`)

```
classify_event(title, description, categories, languages, organizer)
    │
    └── OpenRouter API call (Gemini 2.5 Flash Lite)
        │
        ├── System prompt defines inclusion/exclusion rules
        ├── Returns JSON: {is_indian, reason, cleaned_title}
        └── Fallback: regex-based parsing if JSON decode fails
```

**Classification rules (hardcoded in system prompt):**
- **Include:** Bollywood, Bhangra, Indian classical, Indian comedians, Diwali/Holi/Navratri, Garba, mehndi/sangeet, desi parties, Sufi/Qawwali, Pakistani artists for South Asian audience
- **Hard exclude:** Afghan events (always), Sri Lankan/Nepali/Bangladeshi community events, Caribbean/Caribana, generic parties, "appeals to South Asian diaspora" rationalization
- **Also cleans titles:** Removes redundant venue/city/date info, fixes spacing/typos/capitalization

### 6.3 Image Generator

#### `image_generator/image_search.py` — Find a clean artist photo

```
search_event_image(title, description)
    │
    ├── Check disk cache (data/image_cache/<sha256>.jpg)
    │
    ├── _classify_event()          ── LLM determines: musician/comedian/dj/event/other
    │                                 + generates 3 tailored search queries
    │
    ├── [If person] Identity-verified sources:
    │   ├── fetch_wikipedia()      ── OpenSearch → article image (with profession check)
    │   ├── fetch_wikidata()       ── Entity search → P18 claim → Commons image
    │   ├── fetch_musicbrainz_spotify()  ── MusicBrainz artist → Spotify ID → photo
    │   └── fetch_spotify()        ── Direct Spotify artist search
    │
    └── [Fallback] DuckDuckGo image search
        ├── Large images first, then any size
        └── Each result checked: size ≥ 600×400, not placeholder, no text overlay
```

**Image rejection criteria:**
- `is_placeholder()` — color variance < 18.0 (numpy std on 64×64 thumbnail)
- `has_significant_text()` — Gemini vision API checks for dates/venues/prices in image
- Size < 600×400 pixels

#### `image_generator/create_post.py` — Render the Instagram image

```
create_post_image(event, style="B")
    │
    ├── search_event_image()       ── Get background photo
    ├── _build_html()              ── Generate HTML from template (styles.py)
    └── Playwright render           ── Chromium screenshot → 1080×1350 PNG
```

#### `image_generator/styles.py` — HTML/CSS templates

Only **Style B** exists (A/C/D are aliases). Layout:

```
┌────────────────────────────────┐
│ ██████ 5px saffron top bar ████│
│                                │
│                                │
│         IMAGE BOX              │  900px
│   (contain + blur ambient)     │
│                                │
│                                │
├────────────────────────────────┤
│  EVENT TITLE          52px     │
│  SATURDAY, MARCH 22   30px    │  ~391px
│  Venue  ·  City       26px    │
│  ┌─────────────┐      28px    │
│  │ From CA$25  │              │
│  └─────────────┘              │
├────────────────────────────────┤
│       @indian.events.toronto   │  50px
│ ██████ 4px saffron bottom bar █│
└────────────────────────────────┘
```

Colors: saffron accent `#FF9933`, dark background `#0f0f12` / `#0a0a0e`, venue text `#9090b0`

### 6.4 Publisher

#### `publisher/instagram.py`

```
publish_post(image_path, caption)
    │
    ├── upload_image()           ── Base64 encode → POST to freeimage.host → public URL
    ├── Create media container   ── POST to Instagram Graph API v21.0
    ├── Poll until ready         ── GET status every 2s, up to 60s
    └── Publish                  ── POST media_publish → returns media_id
```

#### `publisher/facebook.py`

```
publish_to_facebook(image_url, caption)
    │
    └── POST to Facebook Graph API v25.0 /{page_id}/photos
        (reuses the same freeimage.host URL — no re-upload)
```

#### `publisher/linkinbio.py`

```
generate_linkinbio()
    │
    ├── get_posted_events()      ── Query DB for posted Indian events
    ├── Filter upcoming only     ── date >= today
    └── Generate docs/index.html ── Dark theme, mobile-responsive, event cards with ticket links
```

### 6.5 Data Store (`data/store.py`)

**Single table: `processed_events`**

| Column | Type | Purpose |
|--------|------|---------|
| `source` | TEXT | Always "sulekha" (PK part 1) |
| `source_id` | TEXT | Sulekha event ID (PK part 2) |
| `title` | TEXT | Cleaned event title |
| `date` | TEXT | ISO datetime |
| `time_str` | TEXT | Human-readable time (e.g. "7:30 PM") |
| `venue` | TEXT | Venue name |
| `address` | TEXT | Full address string |
| `city` | TEXT | City name |
| `price` | TEXT | Price string (e.g. "CAD 25-50") |
| `description` | TEXT | Event description |
| `image_url` | TEXT | Original source image URL |
| `event_url` | TEXT | Link to event listing |
| `categories` | TEXT | Comma-separated |
| `languages` | TEXT | Comma-separated |
| `organizer` | TEXT | Organizer name |
| `is_indian` | INTEGER | 0 or 1 (classification result) |
| `classification_reason` | TEXT | LLM explanation |
| `posted` | INTEGER | 0 or 1 (published to Instagram) |
| `posted_image_url` | TEXT | freeimage.host URL of published post |
| `processed_at` | TEXT | ISO timestamp |

**Key functions:**
- `is_new(event)` — Check if (source, source_id) exists
- `save_event(event, is_indian, reason)` — INSERT OR REPLACE
- `mark_posted(source, source_id, posted_image_url)` — Set posted=1
- `get_posted_events()` — All posted Indian events (for link-in-bio)
- `get_unposted_events()` — Indian events not yet published

---

## 7. Runtime View

### 7.1 Normal Pipeline Run (twice daily)

```
main.py run(publish=True, post_limit=2)
│
├── STEP 1: Scrape
│   └── scrape_events() → ~250 raw events
│
├── STEP 2: Filter
│   ├── is_new(event) → skip already-processed
│   ├── is_gta_event(event) → skip non-Toronto/GTA
│   └── dedup_events() → remove same-date similar titles (>70% SequenceMatcher)
│   Result: ~100 new unique GTA events
│
├── STEP 3: Classify (lazy — stops early)
│   ├── For each event: classify_event() → (is_indian, reason, cleaned_title)
│   ├── save_event() → persist to DB regardless of classification
│   └── Stop when target Indian events found (default: 2)
│   Result: 2 Indian events
│
├── STEP 4: Generate images
│   └── For each Indian event:
│       ├── search_event_image() → find clean artist photo
│       └── create_post_image() → render 1080×1350 PNG
│
├── STEP 5: Publish
│   └── For each generated image:
│       ├── publish_post() → upload to freeimage + Instagram
│       ├── mark_posted() → update DB
│       └── publish_to_facebook() → cross-post
│
└── STEP 6: Update link-in-bio
    └── generate_linkinbio() → regenerate docs/index.html
```

### 7.2 Publish-Only Mode

When `--publish-only` is passed, the pipeline skips scraping/classifying and only publishes previously classified but unposted events from the database.

### 7.3 Lazy Classification

The classifier **stops early** once it finds enough Indian events (default: 2). This saves API costs — most events on Sulekha are not Indian, so classifying all ~250 would be wasteful. Unclassified events will be processed on the next run if they're still new.

---

## 8. Deployment View

### GitHub Actions Workflow (`.github/workflows/post.yml`)

```
┌─────────────────────────────────────────────────────────────┐
│                    GitHub Actions                            │
│                                                             │
│  Triggers:                                                   │
│    • Cron: 8am + 5pm EDT daily                              │
│    • Manual dispatch (with publish/post_limit/publish_only)  │
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Job: post                                               ││
│  │   concurrency: instagram-pipeline (no cancel)           ││
│  │                                                         ││
│  │ 1. Checkout code                                        ││
│  │ 2. Install uv → Python 3.12 → deps → Playwright        ││
│  │ 3. Refresh Instagram token (auto-extend long-lived)     ││
│  │ 4. Run pipeline: python main.py [flags]                 ││
│  │ 5. WAL checkpoint → commit events.db + docs/ → push     ││
│  │ 6. Upload docs/ as Pages artifact                       ││
│  └─────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ Job: deploy-pages (needs: post)                         ││
│  │   Deploy docs/ to GitHub Pages                          ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### Environment Variables (GitHub Secrets)

| Secret | Required | Purpose |
|--------|----------|---------|
| `OPENROUTER_API_KEY` | Yes | LLM API for classification + vision |
| `INSTAGRAM_ACCESS_TOKEN` | Yes | Instagram Graph API publishing |
| `INSTAGRAM_USER_ID` | Yes | Instagram business account ID |
| `FACEBOOK_PAGE_ID` | Yes | Facebook Page to post to |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | Yes | Facebook Page API token |
| `GH_PAT` | Yes | GitHub PAT for updating secrets (token refresh) |
| `SPOTIFY_CLIENT_ID` | Optional | Artist image lookup via Spotify |
| `SPOTIFY_CLIENT_SECRET` | Optional | Artist image lookup via Spotify |

### Artifacts

| Artifact | Location | Committed to Git? |
|----------|----------|-------------------|
| SQLite database | `data/events.db` | Yes |
| Generated images | `output/*.png` | No (gitignored) |
| Image cache | `data/image_cache/` | No (gitignored) |
| Link-in-bio page | `docs/index.html` | Yes |

---

## 9. Crosscutting Concerns

### Error Handling

- **Scraper:** Retry 3× with backoff on listing page; individual detail page failures are logged and skipped
- **Classifier:** JSON decode fallback (regex parse); returns `(False, raw_text, original_title)` on total failure
- **Image search:** Graceful degradation through source waterfall; pipeline continues with no image (warm gradient background)
- **Publishing:** Individual post failures don't stop the pipeline; Facebook failure doesn't block Instagram
- **Database:** WAL mode for concurrent safety; `INSERT OR REPLACE` prevents duplicate key errors

### Caching

- **Image cache:** `data/image_cache/<sha256>.jpg` — keyed by normalized event title, checked before any web search
- **Spotify token:** In-memory cache with expiry tracking (avoids re-auth per request)

### Rate Limiting

| Service | Limit | Implementation |
|---------|-------|----------------|
| Sulekha | Polite | 0.5s delay between detail page requests |
| DuckDuckGo | Reactive | 4-16s delay + retry on 429 |
| MusicBrainz | Strict | 1.1s delay between requests (API requires 1 req/sec) |
| Instagram | 2 posts/run | `--post-limit` flag (default: 2) |

### Security

- All API keys stored as GitHub Secrets (never in code)
- Instagram token auto-refreshed each run and secret updated via `gh secret set`
- freeimage.host API key is hardcoded (it's a free public service, not sensitive)

---

## 10. Architecture Decisions

| # | Decision | Alternatives Considered | Rationale |
|---|----------|------------------------|-----------|
| 1 | **Gemini Flash Lite** for classification | Claude Sonnet, GPT-4o-mini | Cheapest per-token; sufficient accuracy for binary classification |
| 2 | **Playwright** for image rendering | Pillow/PIL text rendering | PIL produces blurry text; Playwright renders HTML/CSS natively via Chromium |
| 3 | **freeimage.host** for image CDN | S3, Cloudinary, Imgur | Free, no auth required for upload, no expiration, Instagram accepts the URLs |
| 4 | **SQLite committed to git** | PostgreSQL, JSON files | Zero infrastructure; database travels with the code; WAL mode handles concurrent access |
| 5 | **Multi-source image waterfall** | DuckDuckGo only | Wikipedia/Wikidata photos are identity-verified (avoids wrong-person photos) |
| 6 | **Lazy classification** (stop after N) | Classify all events | Saves ~90% of LLM API costs per run |
| 7 | **Static HTML link-in-bio** | Linktree, custom backend | No dependencies, free hosting on GitHub Pages, full design control |
| 8 | **Single style (B)** | Multiple visual themes | Styles A/C/D were aliased to B after iteration; one good design beats inconsistency |

---

## 11. Quality Requirements

### Quality Scenarios

| Scenario | Stimulus | Response | Measure |
|----------|----------|----------|---------|
| Wrong classification | Afghan event marked as Indian | Classifier hard-excludes Afghan events | Zero Afghan events posted |
| Text-overlaid image | Event poster with dates/venue | Vision API rejects image; fallback to next source | No images with conflicting text overlay |
| Sulekha down | Listing page returns error | Retry 3× with backoff; pipeline exits cleanly | No corrupt data; next run retries |
| Instagram token expired | API returns 401 | Workflow auto-refreshes token before pipeline runs | Transparent recovery |
| Duplicate event | Same event scraped twice | DB primary key (source, source_id) prevents duplicates | Zero duplicate posts |
| Near-duplicate events | Same concert at 3pm and 7pm | Fuzzy dedup (>70% title similarity on same date) | One post per event |

---

## 12. Risks and Technical Debt

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Sulekha HTML structure changes** | Scraper breaks silently | Monitor for zero-event scrapes; JSON-LD is more stable than DOM parsing |
| **Single event source** | Misses events not on Sulekha | Architecture supports multiple scrapers (add to `scraper/` module) |
| **freeimage.host goes down** | Can't publish (Instagram needs public URLs) | Replace with any image host; publishing module is isolated |
| **Instagram token refresh fails** | Posts fail for that run | Workflow logs warning; current token still works for ~60 days |
| **LLM model deprecated** | Classification breaks | Model name is a single constant in `classifier/indian_classifier.py:11` |
| **DuckDuckGo rate limits** | Image search fails | Retry with backoff; pipeline continues without image (gradient background) |
| **SQLite in git** | DB grows over time | Only one table; old events could be pruned periodically |

### Technical Debt

- `styles.py` has 4 builder functions (A/B/C/D) but A/C/D are aliases to B — should be cleaned up
- `data/store.py` opens a new connection per function call instead of using a shared connection
- No automated tests
- `create_post.py` has a redundant `clean_title()` function (classifier now cleans titles)

---

## 13. Glossary

| Term | Definition |
|------|------------|
| **GTA** | Greater Toronto Area — Toronto and surrounding cities |
| **Sulekha** | Indian community platform (events.sulekha.com) — the primary event source |
| **OpenRouter** | LLM API aggregator — routes requests to various models (Gemini, Claude, etc.) |
| **Graph API** | Meta's API for Instagram and Facebook programmatic access |
| **freeimage.host** | Free image hosting service used as CDN for Instagram uploads |
| **Link-in-bio** | A landing page linked from the Instagram profile, listing events with ticket links |
| **WAL mode** | SQLite Write-Ahead Logging — allows concurrent reads during writes |
| **P18** | Wikidata property for "image" — used to find artist photos |
| **JSON-LD** | JSON for Linked Data — structured data format embedded in web pages (schema.org) |
| **Saffron** | The orange accent color (`#FF9933`) used throughout the brand — matches the Indian flag |

---

## 14. Developer Guide — Where to Make Changes

### "I want to..."

#### Add a new event source (e.g. Eventbrite, BookMyShow)

1. Create `scraper/new_source.py` with a `scrape_events() -> list[Event]` function
2. Import and call it in `main.py` alongside `scrape_events()`
3. Use a unique `source` field (e.g. `"eventbrite"`) — the DB deduplicates by `(source, source_id)`

#### Change what counts as "Indian"

Edit the `SYSTEM_PROMPT` in `classifier/indian_classifier.py` (line 13). The include/exclude rules are plain English in the prompt. The LLM model is set on line 11.

#### Change the post visual design

Edit `image_generator/styles.py`. The `build_html_B()` function generates the HTML/CSS template. Key constants at the top:
- `CANVAS_W/H` — image dimensions (1080×1350)
- `IMAGE_BOX_H` — how much space the photo gets (900px)
- `ACCENT_HEX` — saffron color
- `MIN_FONT_*` — minimum font sizes

Preview locally: run `python -c "from image_generator.create_post import create_post_image; ..."` with a test event.

#### Change posting frequency or limits

- **Schedule:** Edit cron expressions in `.github/workflows/post.yml` (lines 5-7)
- **Posts per run:** Change `default: 2` on line 17, or pass `--post-limit N` on line 80-85
- **Classification target:** The pipeline stops classifying after finding `post_limit` Indian events (see `main.py:119`)

#### Fix a scraping issue

All scraping logic is in `scraper/sulekha.py`:
- Listing page parsing: `scrape_listing_page()` (line 27)
- JSON-LD extraction: `parse_listing_event()` (line 145)
- Detail page scraping: `scrape_detail_page()` (line 76)
- Image URL priority: lines 92-110

#### Change the image search strategy

`image_generator/image_search.py` controls the waterfall:
- Performer type classification: `_classify_event()` (line 173)
- Source ordering: `search_event_image()` (line 273) — Wikipedia → Wikidata → Spotify → DuckDuckGo
- Individual sources: `image_generator/artist_image_sources.py`
- Text overlay detection: `has_significant_text()` (line 76)
- Placeholder detection: `is_placeholder()` (line 135)

#### Change the Instagram caption format

Edit `build_caption()` in `publisher/instagram.py` (line 98). Facebook caption: `build_fb_caption()` in `publisher/facebook.py` (line 17).

#### Change the link-in-bio page

Edit `publisher/linkinbio.py`. The HTML template is in `_build_page()` (line 29) and event cards in `_event_card()` (line 184). Output: `docs/index.html`.

#### Add a new publishing destination (e.g. Twitter/X, Threads)

1. Create `publisher/new_platform.py` with a `publish(image_url, caption)` function
2. Call it in `main.py` in the Step 5 publishing loop (around line 177)
3. Add any new secrets to `.github/workflows/post.yml`

#### Run the pipeline locally

```bash
# Set environment variables
export OPENROUTER_API_KEY="..."
export INSTAGRAM_ACCESS_TOKEN="..."
export INSTAGRAM_USER_ID="..."
# ... etc

# Dry run (no publishing)
uv run python main.py --post-limit 2

# With publishing
uv run python main.py --publish --post-limit 1

# Publish previously generated events only
uv run python main.py --publish-only --post-limit 1
```

### File Map

```
.
├── main.py                              ← Pipeline orchestrator, GTA filter, dedup
├── models.py                            ← Event dataclass (shared data model)
├── requirements.txt                     ← Python dependencies
│
├── scraper/
│   └── sulekha.py                       ← Sulekha scraper (listing + detail pages)
│
├── classifier/
│   └── indian_classifier.py             ← LLM classification + title cleanup
│
├── image_generator/
│   ├── create_post.py                   ← Playwright HTML→PNG renderer
│   ├── image_search.py                  ← Multi-source image search + validation
│   ├── artist_image_sources.py          ← Wikipedia/Wikidata/Spotify/MusicBrainz
│   └── styles.py                        ← HTML/CSS post templates
│
├── publisher/
│   ├── instagram.py                     ← Instagram Graph API + freeimage.host
│   ├── facebook.py                      ← Facebook Graph API
│   └── linkinbio.py                     ← Static HTML page generator
│
├── data/
│   ├── store.py                         ← SQLite operations (CRUD)
│   ├── events.db                        ← SQLite database (committed to git)
│   └── image_cache/                     ← Cached artist images (gitignored)
│
├── fonts/
│   ├── Montserrat.ttf                   ← Primary font
│   └── Montserrat-Italic.ttf
│
├── output/                              ← Generated Instagram PNGs (gitignored)
├── docs/
│   ├── index.html                       ← Generated link-in-bio page
│   └── architecture/                    ← This documentation
│
└── .github/workflows/
    └── post.yml                         ← GitHub Actions CI/CD
```
