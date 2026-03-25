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

This is an **automated pipeline** that discovers Indian cultural events in the Toronto/GTA area and publishes them to Instagram and Facebook. It runs unattended on GitHub Actions with two independent stages: **ingestion** and **posting**.

**Ingestion** (scrape + classify + save to DB):
1. **Scrapes** event listings from Sulekha (an Indian community events site)
2. **Filters** to Toronto/GTA area events only
3. **Classifies** each event as "Indian" or not using an LLM (Gemini)

**Posting** (generate images + publish to all output channels):
4. **Enhances** images with AI-powered background replacement and scene generation (Gemini Flash)
5. **Generates** professional Instagram post images (1080x1350) and countdown stories (1080x1920)
6. **Publishes** posts and stories to Instagram, cross-posts to Facebook
7. **Updates** a static link-in-bio page deployed to GitHub Pages

The two stages communicate only through the SQLite database and can run on independent schedules.

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
| 2 | **Visual quality** | AI-enhanced images with clean artist photos; countdown stories for upcoming events |
| 3 | **Reliability** | Pipeline runs unattended; failures don't corrupt state |
| 4 | **Cost efficiency** | Uses cheapest viable LLM (Gemini Flash Lite via OpenRouter) |

---

## 2. Constraints

### Technical Constraints

| Constraint | Rationale |
|------------|-----------|
| Python 3.12 | GitHub Actions runtime; uv for package management |
| SQLite | Single-file database committed to git; no external DB needed |
| Playwright + Chromium | Renders HTML->PNG for crisp text; PIL text rendering is blurry |
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
                                    +-------------------------------------+
                                    |    Indian Events Toronto Pipeline   |
                                    |         (GitHub Actions)            |
                                    +------------------+------------------+
                                                       |
              +----------------------------------------+----------------------------------------+
              |                                        |                                        |
              v                                        v                                        v
    +------------------+                    +-----------------+                      +------------------+
    |   Data Sources   |                    |   AI Services   |                      |  Publishing      |
    |                  |                    |                  |                      |  Destinations    |
    | - Sulekha.com    |                    | - OpenRouter     |                      |                  |
    | - Wikipedia      |                    |   (Gemini Flash  |                      | - Instagram API  |
    | - Wikidata       |                    |    Lite)         |                      |   (Posts+Stories)|
    | - Spotify API    |                    | - OpenRouter     |                      | - Facebook API   |
    | - MusicBrainz    |                    |   (Gemini Flash  |                      | - GitHub Pages   |
    | - DuckDuckGo     |                    |    Image Gen)    |                      | - freeimage.host |
    +------------------+                    +-----------------+                      +------------------+
```

### External Interfaces

| System | Direction | Purpose | Auth |
|--------|-----------|---------|------|
| **Sulekha** | Inbound | Scrape event listings + detail pages | None (public HTML) |
| **OpenRouter** (Gemini Flash Lite) | Outbound | LLM classification + vision checks | `OPENROUTER_API_KEY` |
| **OpenRouter** (Gemini Flash Image) | Outbound | AI image enhancement/generation | `OPENROUTER_API_KEY` |
| **Instagram Graph API** | Outbound | Publish photo posts + stories | `INSTAGRAM_ACCESS_TOKEN` + `INSTAGRAM_USER_ID` |
| **Facebook Graph API** | Outbound | Cross-post photos to Page | `FACEBOOK_PAGE_ACCESS_TOKEN` + `FACEBOOK_PAGE_ID` |
| **freeimage.host** | Outbound | Host uploaded images (Instagram requires public URLs) | Hardcoded API key |
| **Wikipedia / Wikidata** | Outbound | Artist photo lookup (identity-verified) | None |
| **Spotify API** | Outbound | Artist photo fallback | `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` |
| **MusicBrainz** | Outbound | Artist identity -> Spotify ID mapping | None |
| **DuckDuckGo Images** | Outbound | Fallback image search | None |
| **GitHub Pages** | Deployment | Static link-in-bio page | Git push |

---

## 4. Solution Strategy

| Decision | Approach | Why |
|----------|----------|-----|
| **Event source** | Scrape Sulekha JSON-LD | Structured data (schema.org), comprehensive GTA coverage |
| **Classification** | LLM with detailed system prompt | Nuanced cultural classification; regex/keyword matching would miss too much or over-include |
| **Image sourcing** | Sulekha-first, then web search waterfall | Best available image from event source; identity-verified fallbacks |
| **Image enhancement** | AI-powered via Gemini Flash Image Gen | Clean backgrounds for artists, cinematic scenes for events; removes text/watermarks |
| **Image rendering** | HTML/CSS -> Playwright screenshot | Crisp text, flexible layouts, CSS-based responsive design |
| **Stories** | Countdown images for events <=5 days away | Drives urgency and engagement; auto-deduplicates by day count |
| **Storage** | SQLite committed to git | Zero infrastructure; portable; full history in git |
| **Deployment** | GitHub Actions cron | Free, reliable, no server maintenance |
| **Image hosting** | freeimage.host | Instagram API requires public URLs; free CDN |

---

## 5. Container View (C4 Level 2)

```
+-----------------------------------------------------------------------+
|                        GitHub Actions Runner                           |
|                                                                        |
|  +----------+   +----------+   +-------------+   +-----------------+  |
|  | Scraper  |-->|Classifier|-->|   Image      |-->|   Publisher     |  |
|  |          |   |          |   |   Generator  |   |                 |  |
|  |sulekha.py|   |indian_   |   |              |   |instagram.py     |  |
|  |          |   |classifier|   |create_post   |   | (posts+stories) |  |
|  |          |   |.py       |   |create_story  |   |facebook.py      |  |
|  +----------+   +----------+   |image_search  |   |linkinbio.py     |  |
|       |              |         |ai_enhance    |   +-----------------+  |
|       |              |         |styles.py     |         |              |
|       |              |         |artist_image  |         |              |
|       v              v         |_sources.py   |         v              |
|  +----------------------------------------------------------------+   |
|  |                    SQLite Database                               |  |
|  |                    data/events.db                                |  |
|  +----------------------------------------------------------------+   |
|                                                                        |
|  +------------+                                                        |
|  | main.py    |  <-- Pipeline orchestrator                            |
|  |            |      Coordinates all steps                             |
|  +------------+                                                        |
+-----------------------------------------------------------------------+
```

### Containers

| Container | Technology | Purpose |
|-----------|------------|---------|
| **main.py** | Python | Pipeline orchestrator — `--ingest` (scrape + classify) and `--post` (generate + publish) entry points |
| **scraper/** | BeautifulSoup, requests | Fetches + parses Sulekha event listings |
| **classifier/** | OpenAI client -> OpenRouter | LLM-based event classification + title cleanup |
| **image_generator/** | Playwright, Pillow, ddgs, OpenRouter | Finds images, AI-enhances them, renders posts + stories |
| **publisher/** | requests (Graph APIs) | Publishes posts + stories to Instagram, Facebook, generates link-in-bio |
| **data/** | SQLite | Persistent event storage, dedup tracking, post + story status |
| **docs/** | Static HTML | Generated link-in-bio page (GitHub Pages) |

---

## 6. Component View (C4 Level 3)

### 6.1 Scraper (`scraper/sulekha.py`)

```
scrape_events()
    |
    +-- scrape_listing_page()     -- GET listing page, parse JSON-LD
    |                                  Returns: list of raw event dicts
    |
    +-- parse_listing_event()     -- Extract title, date, venue, price from JSON-LD
    |
    +-- scrape_detail_page()      -- GET each event's detail page
                                     Extract: hi-res image URLs (multiple),
                                     description, categories, languages, organizer
```

**Key details:**
- Source URL: `https://events.sulekha.com/toronto-metro-area`
- Parses `<script type="application/ld+json">` blocks (schema.org Event type)
- Collects **multiple image URLs** per event (stored in `Event.image_urls`)
- Image priority: `header2` (1280x500) -> `root` -> `header` -> `thumbnail`
- Rate-limited: 0.5s delay between detail page requests
- Retry logic: 3 attempts with exponential backoff on listing page

### 6.2 Classifier (`classifier/indian_classifier.py`)

```
classify_event(title, description, categories, languages, organizer)
    |
    +-- OpenRouter API call (Gemini 2.5 Flash Lite)
        |
        +-- System prompt defines inclusion/exclusion rules
        +-- Returns JSON: {is_indian, reason, cleaned_title}
        +-- Fallback: regex-based parsing if JSON decode fails
```

**Classification rules (hardcoded in system prompt):**
- **Include:** Bollywood, Bhangra, Indian classical, Indian comedians, Diwali/Holi/Navratri, Garba, mehndi/sangeet, desi parties, Sufi/Qawwali, Pakistani artists for South Asian audience
- **Hard exclude:** Afghan events (always), Sri Lankan/Nepali/Bangladeshi community events, Caribbean/Caribana, generic parties, "appeals to South Asian diaspora" rationalization
- **Also cleans titles:** Removes redundant venue/city/date info, fixes spacing/typos/capitalization

### 6.3 Image Generator

#### `image_generator/create_post.py` — Orchestrate image sourcing + rendering

```
create_post_image(event, style="B")
    |
    +-- classify_event()           -- Determine performer type (musician/comedian/dj/event/other)
    |
    +-- [Sulekha-first strategy]
    |   +-- Download all event.image_urls
    |   +-- Pick image closest to square aspect ratio (best_score = abs(ratio - 1.0))
    |   +-- Reject placeholders (is_placeholder)
    |
    +-- enhance_image()            -- AI enhancement (see ai_enhance.py below)
    |   |
    |   +-- [If artist + has source] -> Replace background, keep face
    |   +-- [If event + has source]  -> Enhance atmosphere or generate fresh
    |   +-- [If no source]           -> Generate mood scene from scratch
    |
    +-- [Fallback chain]
    |   +-- AI success? -> Use AI image (cover fit)
    |   +-- AI failed + Sulekha clean? -> Use Sulekha directly (contain fit)
    |   +-- All failed? -> Web search via search_event_image()
    |
    +-- _build_html()              -- Generate HTML from template (styles.py)
    +-- Playwright render          -- Chromium screenshot -> 1080x1350 PNG
```

#### `image_generator/ai_enhance.py` — AI-powered image enhancement

```
enhance_image(source_img, title, description, performer_type, artist_name, cache_key)
    |
    +-- Check AI cache (data/image_cache/<key>_ai.jpg)
    |
    +-- [Artist mode] enhance_artist_image()
    |   Prompt: keep exact face, replace background with themed lighting
    |   Styles: comedian -> stage/spotlight, musician -> concert, dj -> club neon
    |
    +-- [Event mode] enhance_event_image()
    |   With source: enhance crowd/atmosphere, remove text overlays
    |   Without source: generate fresh scene (Bollywood, Bhangra, Sufi, etc.)
    |
    +-- [Scene mode] generate_scene_image()
        Generate aesthetic mood (dating, festival, food, wellness, etc.)
```

**AI model:** Gemini 2.5 Flash Image Gen via OpenRouter (`google/gemini-2.5-flash-image`)
- Output: 5:4 aspect ratio, 2K resolution
- Autocrop: trims near-black borders that AI sometimes adds
- Caching: per-event `<key>_ai.jpg` to avoid re-running expensive generation

#### `image_generator/image_search.py` — Web-based image search (fallback)

```
search_event_image(title, description)
    |
    +-- Check disk cache (data/image_cache/<sha256>.jpg)
    |
    +-- _classify_event()          -- LLM determines: musician/comedian/dj/event/other
    |                                 + generates 3 tailored search queries
    |
    +-- [If person] Identity-verified sources:
    |   +-- fetch_wikipedia()      -- OpenSearch -> article image (with profession check)
    |   +-- fetch_wikidata()       -- Entity search -> P18 claim -> Commons image
    |   +-- fetch_musicbrainz_spotify()  -- MusicBrainz artist -> Spotify ID -> photo
    |   +-- fetch_spotify()        -- Direct Spotify artist search
    |
    +-- [Fallback] DuckDuckGo image search
        +-- Large images first, then any size
        +-- Each result checked: size >= 600x400, not placeholder, no text overlay
```

**Image rejection criteria:**
- `is_placeholder()` — color variance < 18.0 (numpy std on 64x64 thumbnail)
- `has_significant_text()` — Gemini vision API checks for dates/venues/prices in image
- Size < 600x400 pixels

#### `image_generator/create_story.py` — Instagram Stories countdown images

```
create_story_image(event, days_left, style="C")
    |
    +-- _download_and_crop_posted_image()  -- Download posted image, crop rows 5-905 (image box)
    +-- Build HTML from style template (A/B/C/D — each is unique)
    +-- Playwright render -> 1080x1920 PNG
```

**Story styles (all 4 are distinct, unlike post styles):**
- **Style A** — Giant saffron circle badge with countdown number
- **Style B** — Cinematic gradient, countdown at bottom-left
- **Style C** — Neon double-frame with "COMING SOON" ticker (default)
- **Style D** — Split screen: full original post on top + countdown banner below

**Common elements:** Dark gradient CTA backdrop, outlined saffron pill ("GET TICKETS"), @handle branding

#### `image_generator/styles.py` — Post HTML/CSS templates

Only **Style B** is used for posts (A/C/D are aliases). Layout:

```
+--------------------------------+
| ██████ 5px saffron top bar ████|
|                                |
|                                |
|         IMAGE BOX              |  900px
|   (contain + blur ambient)     |
|                                |
|                                |
+--------------------------------+
|  EVENT TITLE          52px     |
|  SATURDAY, MARCH 22   30px    |  ~391px
|  Venue  ·  City       26px    |
|  +-------------+      28px    |
|  | From CA$25  |              |
|  +-------------+              |
+--------------------------------+
|       @indian.events.toronto   |  50px
| ██████ 4px saffron bottom bar █|
+--------------------------------+
```

Colors: saffron accent `#FF9933`, dark background `#0f0f12` / `#0a0a0e`, venue text `#9090b0`

### 6.4 Publisher

#### `publisher/instagram.py`

```
publish_post(image_path, caption)
    |
    +-- upload_image()           -- Base64 encode -> POST to freeimage.host -> public URL
    +-- Create media container   -- POST to Instagram Graph API v21.0
    +-- Poll until ready         -- GET status every 2s, up to 60s
    +-- Publish                  -- POST media_publish -> returns media_id

publish_story(image_path)
    |
    +-- upload_image()           -- Same freeimage.host upload
    +-- Create story container   -- POST with media_type="STORIES"
    +-- Poll until ready         -- Same polling logic
    +-- Publish                  -- POST media_publish -> returns media_id
```

#### `publisher/instagram_handle.py` — Artist handle lookup with disambiguation

```
lookup_instagram_handle(artist_name, performer_type) -> str | None
    |
    +-- Check manual overrides     -- data/instagram_handles.json (highest confidence)
    +-- Check SQLite cache         -- 30-day TTL for found, 7-day for failed
    +-- Wikidata P2003             -- Community-verified Instagram usernames
    |   +-- Entity search with performer_type disambiguation
    |   +-- Skips wrong professions (comedian vs actor, etc.)
    +-- DuckDuckGo text search     -- Multi-candidate scored lookup
    |   +-- 3 query strategies (simple, with type, with site: filter)
    |   +-- Scores by: name similarity, brevity, "official" mentions, frequency
    |   +-- Returns top 3 candidates for verification
    +-- LLM suggestion             -- Gemini Flash Lite as last resort
    |
    +-- Verification (all sources except manual overrides):
        +-- Instagram Business Discovery API
        +-- Checks: account exists, public, 1000+ followers
        +-- Bio/name matches performer type or artist name
        +-- Falls through to next candidate on failure
```

Handles are cached in the `instagram_handles` table (keyed by artist name, not event). The `user_tags` parameter on the Instagram media container tags the artist in the post image, and `@handle` is added to both Instagram and Facebook captions.

#### `publisher/facebook.py`

```
publish_to_facebook(image_url, caption)
    |
    +-- POST to Facebook Graph API v25.0 /{page_id}/photos
        (reuses the same freeimage.host URL — no re-upload)
```

#### `publisher/linkinbio.py`

```
generate_linkinbio()
    |
    +-- get_posted_events()      -- Query DB for posted Indian events
    +-- Filter upcoming only     -- date >= today
    +-- Generate docs/index.html -- Dark theme, mobile-responsive, event cards with ticket links
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
| `image_url` | TEXT | Primary source image URL |
| `image_urls` | TEXT | All source image URLs (comma-separated, for Sulekha-first strategy) |
| `event_url` | TEXT | Link to event listing |
| `categories` | TEXT | Comma-separated |
| `languages` | TEXT | Comma-separated |
| `organizer` | TEXT | Organizer name |
| `is_indian` | INTEGER | 0 or 1 (classification result) |
| `classification_reason` | TEXT | LLM explanation |
| `posted` | INTEGER | 0 or 1 (published to Instagram) |
| `posted_image_url` | TEXT | freeimage.host URL of published post |
| `story_posted_at` | TEXT | ISO timestamp of last story publish |
| `story_days_posted` | TEXT | Comma-separated day counts already posted (e.g. "5,3,1") |
| `processed_at` | TEXT | ISO timestamp |

**Key functions:**
- `is_new(event)` — Check if (source, source_id) exists
- `save_event(event, is_indian, reason)` — INSERT OR REPLACE
- `mark_posted(source, source_id, posted_image_url)` — Set posted=1
- `get_posted_events()` — All posted Indian events (for link-in-bio)
- `get_unposted_events()` — Indian events not yet published
- `get_story_candidates(max_days)` — Posted events 1-N days away, excluding already-storied day counts
- `mark_story_posted(source, source_id, days_left)` — Append day count to `story_days_posted`
- `get_cached_handle(artist_name)` — Return cached Instagram handle with freshness check
- `save_handle_cache(artist_name, performer_type, handle, source, followers)` — Cache handle lookup result

**Second table: `instagram_handles`** — caches artist handle lookups (keyed by artist, not event)

| Column | Type | Purpose |
|--------|------|---------|
| `artist_name` | TEXT | Artist name (PK) |
| `performer_type` | TEXT | comedian/musician/dj |
| `instagram_handle` | TEXT | Handle or NULL if lookup failed |
| `source` | TEXT | How it was found (manual/wikidata/ddg/llm) |
| `followers_count` | INTEGER | Follower count at lookup time |
| `looked_up_at` | TEXT | ISO timestamp (TTL: 30d found, 7d failed) |

### 6.6 Data Model (`models.py`)

```python
@dataclass
class Event:
    source: str              # e.g. "sulekha"
    source_id: str           # unique ID from the source
    title: str               # cleaned event title
    date: datetime           # event date/time
    time_str: str            # human-readable time
    venue: str               # venue name
    address: str             # full address
    city: str                # city name
    price: str               # price string
    description: str         # event description
    image_url: str           # primary image URL
    event_url: str           # link to event listing
    categories: list[str]    # e.g. ["Music", "Concert"]
    languages: list[str]     # e.g. ["Hindi", "Punjabi"]
    organizer: str           # organizer name
    posted_image_url: str    # freeimage.host URL after posting
    image_urls: list[str]    # all image URLs from source (for Sulekha-first strategy)
```

---

## 7. Runtime View

### 7.1 Ingestion (`--ingest`)

```
main.py ingest(classify_limit=10)
|
+-- STEP 1: Scrape
|   +-- scrape_events() -> ~250 raw events
|
+-- STEP 2: Filter
|   +-- is_new(event) -> skip already-processed
|   +-- is_gta_event(event) -> skip non-Toronto/GTA
|   +-- dedup_events() -> remove same-date similar titles (>70% SequenceMatcher)
|   Result: ~100 new unique GTA events
|
+-- STEP 3: Classify (up to classify_limit)
    +-- For each event: classify_event() -> (is_indian, reason, cleaned_title)
    +-- save_event() -> persist to DB regardless of classification
    +-- Stop after classify_limit events classified (default: 10)
    Result: N Indian events saved to DB
```

No image generation, no publishing, no link-in-bio updates. Pure data ingestion.

### 7.2 Posting (`--post`)

```
main.py post(post_limit=2, dry_run=False)
|
+-- Read unposted events from DB
|   +-- get_unposted_events() -> Indian events not yet published
|   +-- Filter out events with a similar already-posted event
|
+-- For each event (up to post_limit):
|   +-- Generate image
|   |   +-- Download best Sulekha image from stored image_urls
|   |   +-- enhance_image() -> AI enhancement (background replace / scene gen)
|   |   +-- Fallback: Sulekha direct or web search if AI fails
|   |   +-- create_post_image() -> render 1080x1350 PNG
|   |
|   +-- Publish
|       +-- publish_post() -> upload to freeimage + Instagram
|       +-- mark_posted() -> update DB
|       +-- publish_to_facebook() -> cross-post
|
+-- Publish countdown stories
|   +-- get_story_candidates(max_days=5) -> events 1-5 days away
|   +-- For each candidate:
|       +-- create_story_image() -> render 1080x1920 PNG
|       +-- publish_story() -> upload + publish as Instagram Story
|       +-- mark_story_posted() -> record day count to prevent re-posting
|
+-- Update link-in-bio
    +-- generate_linkinbio() -> regenerate docs/index.html
```

### 7.3 Stories-Only Mode

When `--stories-only` is passed, the pipeline skips everything except publishing countdown stories for already-posted events that are 1-5 days away.

### 7.4 Lazy Classification

The classifier stops after `classify_limit` events (default: 10) to cap API costs. Unclassified events will be processed on the next ingestion run if they're still new.

### 7.5 Image Sourcing Strategy

The pipeline uses a **Sulekha-first** approach with AI enhancement:

1. **Download all Sulekha images** for the event (multiple URLs from detail page)
2. **Pick the best** — closest to square/portrait aspect ratio, reject placeholders
3. **AI enhance** the best image via Gemini:
   - Artists: keep face, replace background with themed lighting
   - Events: enhance atmosphere or generate fresh scene
4. **Fallback chain** if AI fails:
   - Use Sulekha image directly (if no text overlays)
   - Web search waterfall (Wikipedia -> Wikidata -> Spotify -> DuckDuckGo)

---

## 8. Deployment View

### GitHub Actions Workflows

```
+-------------------------------------------------------------+
|              Ingest Workflow (ingest.yml)                     |
|                                                              |
|  Triggers: Cron 8am + 5pm EDT, manual dispatch              |
|  Secrets: OPENROUTER_API_KEY                                 |
|  Concurrency: ingest-events                                  |
|                                                              |
|  1. Checkout code                                            |
|  2. Install uv -> Python 3.12 -> deps                       |
|  3. python main.py --ingest --classify-limit N               |
|  4. WAL checkpoint -> commit events.db -> push               |
+-------------------------------------------------------------+

+-------------------------------------------------------------+
|              Post Workflow (post.yml)                         |
|                                                              |
|  Triggers: Cron 9am + 6pm EDT (1hr after ingest), manual     |
|  Secrets: OPENROUTER, IG, FB, Spotify keys                   |
|  Concurrency: instagram-posts                                |
|                                                              |
|  1. Checkout code                                            |
|  2. Install uv -> Python 3.12 -> deps -> Playwright          |
|  3. Refresh Instagram token (auto-extend long-lived)         |
|  4. python main.py --post --post-limit N                     |
|  5. WAL checkpoint -> commit events.db + docs/ -> push       |
|  6. Upload docs/ as Pages artifact                           |
|  +----------------------------------------------------------+|
|  | Job: deploy-pages (needs: post)                          ||
|  |   Deploy docs/ to GitHub Pages                           ||
|  +----------------------------------------------------------+|
+-------------------------------------------------------------+

+-------------------------------------------------------------+
|              Stories Workflow (stories.yml)                   |
|                                                              |
|  Triggers: Cron 3x daily, manual dispatch                    |
|  Concurrency: instagram-stories                              |
|                                                              |
|  1. python main.py --stories-only                            |
+-------------------------------------------------------------+
```

### Environment Variables (GitHub Secrets)

| Secret | Required | Purpose |
|--------|----------|---------|
| `OPENROUTER_API_KEY` | Yes | LLM API for classification + vision + image generation |
| `INSTAGRAM_ACCESS_TOKEN` | Yes | Instagram Graph API publishing (posts + stories) |
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
| Generated post images | `output/*.png` | No (gitignored) |
| Generated story images | `output/story_*.png` | No (gitignored) |
| Image cache | `data/image_cache/` | No (gitignored) |
| AI-enhanced image cache | `data/image_cache/*_ai.jpg` | No (gitignored) |
| Link-in-bio page | `docs/index.html` | Yes |

---

## 9. Crosscutting Concerns

### Error Handling

- **Scraper:** Retry 3x with backoff on listing page; individual detail page failures are logged and skipped
- **Classifier:** JSON decode fallback (regex parse); returns `(False, raw_text, original_title)` on total failure
- **AI enhancement:** Returns None on any failure; caller falls back to Sulekha image or web search
- **Image search:** Graceful degradation through source waterfall; pipeline continues with no image
- **Publishing:** Individual post failures don't stop the pipeline; Facebook failure doesn't block Instagram
- **Stories:** Individual story failures don't stop the pipeline; errors are logged and skipped
- **Database:** WAL mode for concurrent safety; `INSERT OR REPLACE` prevents duplicate key errors; schema migrations add columns if missing

### Caching

- **Image cache:** `data/image_cache/<sha256>.jpg` — keyed by normalized event title, checked before any web search
- **AI image cache:** `data/image_cache/<key>_ai.jpg` — keyed by event, checked before running expensive AI generation
- **Spotify token:** In-memory cache with expiry tracking (avoids re-auth per request)

### Rate Limiting

| Service | Limit | Implementation |
|---------|-------|----------------|
| Sulekha | Polite | 0.5s delay between detail page requests |
| DuckDuckGo | Reactive | 4-16s delay + retry on 429 |
| MusicBrainz | Strict | 1.1s delay between requests (API requires 1 req/sec) |
| Instagram | 2 posts/run | `--post-limit` flag (default: 2) |
| OpenRouter (Image Gen) | Per-event | One AI generation attempt per event (cached) |

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
| 8 | **Single post style (B)** | Multiple visual themes | Styles A/C/D were aliased to B after iteration; one good design beats inconsistency |
| 9 | **Sulekha-first image strategy** | Always search web | Source images are the most relevant; picks best aspect ratio from all available URLs |
| 10 | **AI image enhancement** (Gemini Flash) | Manual curation, raw source images | Removes text/watermarks, creates cinematic backgrounds, generates scenes when no photo exists |
| 11 | **Countdown stories** | No stories, manual posting | Drives engagement for upcoming events; auto-deduplicates by day count so each countdown is posted once |
| 12 | **Decoupled ingestion and posting** | Single monolithic pipeline | Independent schedules, faster feedback, cleaner failure isolation; DB is the only integration point; "ingest" abstraction allows future non-scraping sources (APIs, feeds) |

---

## 11. Quality Requirements

### Quality Scenarios

| Scenario | Stimulus | Response | Measure |
|----------|----------|----------|---------|
| Wrong classification | Afghan event marked as Indian | Classifier hard-excludes Afghan events | Zero Afghan events posted |
| Text-overlaid image | Event poster with dates/venue | Vision API rejects image; AI enhancement removes text; fallback to next source | No images with conflicting text overlay |
| Sulekha down | Listing page returns error | Retry 3x with backoff; pipeline exits cleanly | No corrupt data; next run retries |
| Instagram token expired | API returns 401 | Workflow auto-refreshes token before pipeline runs | Transparent recovery |
| Duplicate event | Same event scraped twice | DB primary key (source, source_id) prevents duplicates | Zero duplicate posts |
| Near-duplicate events | Same concert at 3pm and 7pm | Fuzzy dedup (>70% title similarity on same date) | One post per event |
| Duplicate story | Same countdown already posted | `story_days_posted` tracks which day-counts are done | One story per event per day-count |
| AI enhancement fails | OpenRouter returns error | Falls back to Sulekha image or web search | Pipeline continues without AI images |

---

## 12. Risks and Technical Debt

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Sulekha HTML structure changes** | Scraper breaks silently | Monitor for zero-event scrapes; JSON-LD is more stable than DOM parsing |
| **Single event source** | Misses events not on Sulekha | Architecture supports multiple scrapers (add to `scraper/` module) |
| **freeimage.host goes down** | Can't publish (Instagram needs public URLs) | Replace with any image host; publishing module is isolated |
| **Instagram token refresh fails** | Posts fail for that run | Workflow logs warning; current token still works for ~60 days |
| **LLM model deprecated** | Classification breaks | Model name is a single constant in `classifier/indian_classifier.py:11` |
| **AI image model deprecated** | Enhancement breaks | Model name is a single constant in `image_generator/ai_enhance.py:18`; falls back gracefully |
| **DuckDuckGo rate limits** | Image search fails | Retry with backoff; pipeline continues without image |
| **SQLite in git** | DB grows over time | Only one table; old events could be pruned periodically |
| **OpenRouter outage** | AI enhancement + classification fail | Enhancement falls back gracefully; classification returns safe default |

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
| **Countdown story** | An Instagram Story image showing "N DAYS TO GO" for upcoming events |
| **AI enhancement** | Using Gemini Flash Image Gen to improve or generate event images |
| **Sulekha-first** | Image strategy: prefer the best image from the event source before searching the web |

---

## 14. Developer Guide — Where to Make Changes

### "I want to..."

#### Add a new event source (e.g. Eventbrite, BookMyShow)

1. Create `scraper/new_source.py` with a `scrape_events() -> list[Event]` function
2. Import and call it in the `ingest()` function in `main.py` alongside `scrape_events()`
3. Use a unique `source` field (e.g. `"eventbrite"`) — the DB deduplicates by `(source, source_id)`

#### Change what counts as "Indian"

Edit the `SYSTEM_PROMPT` in `classifier/indian_classifier.py` (line 13). The include/exclude rules are plain English in the prompt. The LLM model is set on line 11.

#### Change the post visual design

Edit `image_generator/styles.py`. The `build_html_B()` function generates the HTML/CSS template. Key constants are in `create_post.py`:
- `CANVAS_W/H` — image dimensions (1080x1350)
- `IMAGE_BOX_H` — how much space the photo gets (900px)
- `ACCENT_HEX` — saffron color

#### Change the story visual design

Edit `image_generator/create_story.py`. Four distinct styles are defined:
- `_style_a_html()` — Giant saffron circle badge
- `_style_b_html()` — Cinematic gradient, countdown at bottom
- `_style_c_html()` — Neon double-frame (current default)
- `_style_d_html()` — Split screen with original post

The default style is set in `main.py:103` (`style="C"`).

#### Change the AI enhancement behavior

Edit `image_generator/ai_enhance.py`:
- AI model: `MODEL` constant (line 18)
- Artist prompt: `_ARTIST_PROMPT` (line 126)
- Background styles per type: `_BACKGROUND_STYLES` (line 149)
- Event style inference: `_get_event_style()` (line 204)
- Scene guidance: `_get_scene_guidance()` (line 220)
- Strategy dispatch: `enhance_image()` (line 282)

#### Change posting frequency or limits

- **Ingest schedule:** Edit cron expressions in `.github/workflows/ingest.yml`
- **Post schedule:** Edit cron expressions in `.github/workflows/post.yml`
- **Posts per run:** Change `default: 2` in `post.yml`, or pass `--post-limit N`
- **Classification limit:** Change `default: 10` in `ingest.yml`, or pass `--classify-limit N`
- **Story max days:** Change `max_days=5` in `main.py`

#### Fix a scraping issue

All scraping logic is in `scraper/sulekha.py`:
- Listing page parsing: `scrape_listing_page()` (line 27)
- JSON-LD extraction: `parse_listing_event()` (line 145)
- Detail page scraping: `scrape_detail_page()` (line 76)
- Image URL priority: lines 92-110

#### Change the image search strategy

`image_generator/image_search.py` controls the web search waterfall:
- Performer type classification: `_classify_event()` (line 173)
- Source ordering: `search_event_image()` (line 273) — Wikipedia -> Wikidata -> Spotify -> DuckDuckGo
- Individual sources: `image_generator/artist_image_sources.py`
- Text overlay detection: `has_significant_text()` (line 76)
- Placeholder detection: `is_placeholder()` (line 135)

#### Change the Instagram caption format

Edit `build_caption()` in `publisher/instagram.py` (line 159). Facebook caption: `build_fb_caption()` in `publisher/facebook.py` (line 17).

#### Change the link-in-bio page

Edit `publisher/linkinbio.py`. The HTML template is in `_build_page()` (line 29) and event cards in `_event_card()` (line 184). Output: `docs/index.html`.

#### Add a new publishing destination (e.g. Twitter/X, Threads)

1. Create `publisher/new_platform.py` with a `publish(image_url, caption)` function
2. Call it in the `post()` function in `main.py` alongside the Instagram and Facebook publishing
3. Add any new secrets to `.github/workflows/post.yml`

#### Run the pipeline locally

```bash
# Set environment variables
export OPENROUTER_API_KEY="..."
export INSTAGRAM_ACCESS_TOKEN="..."
export INSTAGRAM_USER_ID="..."
# ... etc

# Ingest: scrape, classify, save to DB
uv run python main.py --ingest

# Post: generate images + publish unposted events
uv run python main.py --post --post-limit 2

# Dry run (generate images, show captions, skip actual publishing)
uv run python main.py --post --dry-run --post-limit 2

# Publish countdown stories only
uv run python main.py --stories-only

# Post but skip stories
uv run python main.py --post --post-limit 2 --no-stories
```

### File Map

```
.
+-- main.py                              <- Pipeline orchestrator (--ingest / --post), GTA filter, dedup
+-- models.py                            <- Event dataclass (shared data model)
+-- requirements.txt                     <- Python dependencies
|
+-- scraper/
|   +-- sulekha.py                       <- Sulekha scraper (listing + detail pages)
|
+-- classifier/
|   +-- indian_classifier.py             <- LLM classification + title cleanup
|
+-- image_generator/
|   +-- create_post.py                   <- Sulekha-first image sourcing + Playwright render
|   +-- create_story.py                  <- Instagram Stories countdown images (1080x1920)
|   +-- ai_enhance.py                    <- Gemini-powered image enhancement/generation
|   +-- image_search.py                  <- Multi-source web image search + validation
|   +-- artist_image_sources.py          <- Wikipedia/Wikidata/Spotify/MusicBrainz
|   +-- styles.py                        <- HTML/CSS post templates
|
+-- publisher/
|   +-- instagram.py                     <- Instagram Graph API (posts + stories) + freeimage.host
|   +-- facebook.py                      <- Facebook Graph API
|   +-- linkinbio.py                     <- Static HTML page generator
|
+-- data/
|   +-- store.py                         <- SQLite operations (CRUD + story tracking)
|   +-- events.db                        <- SQLite database (committed to git)
|   +-- image_cache/                     <- Cached artist + AI-enhanced images (gitignored)
|
+-- fonts/
|   +-- Montserrat.ttf                   <- Primary font
|   +-- Montserrat-Italic.ttf
|
+-- output/                              <- Generated post + story PNGs (gitignored)
+-- docs/
|   +-- index.html                       <- Generated link-in-bio page
|   +-- architecture/                    <- This documentation
|
+-- .github/workflows/
    +-- ingest.yml                       <- Ingestion: scrape + classify + save to DB
    +-- post.yml                         <- Posting: generate images + publish + link-in-bio
    +-- stories.yml                      <- Countdown stories for upcoming events
```
