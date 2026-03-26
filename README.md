<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/Playwright-Chromium-2EAD33?logo=playwright&logoColor=white" alt="Playwright">
  <img src="https://img.shields.io/badge/AI-Gemini%20Flash-4285F4?logo=google&logoColor=white" alt="Gemini Flash">
  <img src="https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white" alt="GitHub Actions">
  <img src="https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/Instagram-Graph%20API-E4405F?logo=instagram&logoColor=white" alt="Instagram">
</p>

# Indian Events Toronto

**Automated pipeline that discovers Indian cultural events in the Toronto/GTA area and publishes them to Instagram and Facebook.** Runs unattended on GitHub Actions — ingesting events and publishing posts independently with zero manual intervention.

<p align="center">
  <strong>
    <a href="https://www.instagram.com/indian.events.toronto/">Instagram</a> &bull;
    <a href="docs/architecture/README.md">Architecture Docs</a>
  </strong>
</p>

---

## How It Works

```
                    INGEST (runs independently)
  +---------+   +----------+   +----------+
  | Scrape  |-->| Filter & |-->| Classify |------> SQLite DB
  | Events  |   | Dedup    |   | (Indian?)|
  +---------+   +----------+   +----------+

                    POST (runs independently)
                                +---------+   +----------+
  SQLite DB -----> Read ------->| Enhance |-->| Generate |
                  unposted      | Images  |   | Posts    |
                                +---------+   +----------+
                                                    |
       +--------------------------------------------+
       |                    |                    |
       v                    v                    v
  +-----------+   +------------------+   +---------------+
  | Instagram |   | Facebook         |   | GitHub Pages  |
  | Posts +   |   | Cross-post       |   | Link-in-bio   |
  | Stories   |   |                  |   |               |
  +-----------+   +------------------+   +---------------+
```

The pipeline has two independent stages:

**Ingestion** (twice daily, 8 AM and 5 PM EDT):
1. **Scrapes** ~250 event listings from [Sulekha](https://events.sulekha.com/toronto-metro-area) via JSON-LD structured data
2. **Filters** to Toronto/GTA area and removes near-duplicates (>70% title similarity on same date)
3. **Classifies** each event as "Indian" or not using Gemini Flash Lite with detailed cultural rules

**Posting** (twice daily, 9 AM and 6 PM EDT):
4. **Reconciles** DB with live Instagram posts via alt_text event keys
5. **Enhances** images using AI — replaces backgrounds for artists, generates cinematic scenes for events
6. **Renders** professional 1080x1350 Instagram posts with Pillow (saffron/dark theme)
7. **Publishes** to Instagram (with alt_text tracking), cross-posts to Facebook, and updates a static [link-in-bio](docs/index.html) page
8. **Publishes** countdown stories (1080x1920) for events happening within 5 days

---

## Features

### AI-Powered Image Pipeline

Images go through a sophisticated sourcing and enhancement chain:

- **Sulekha-first** — downloads all images from the event page, picks the best aspect ratio
- **AI enhancement** — Gemini Flash Image Gen replaces cluttered backgrounds with cinematic lighting while preserving faces
- **Web search fallback** — identity-verified sources (Wikipedia, Wikidata, Spotify) before broad search (DuckDuckGo)
- **Smart rejection** — rejects placeholders (low color variance) and images with text overlays (vision API check)

### Intelligent Classification

The LLM classifier handles nuanced cultural rules:

- **Includes:** Bollywood, Bhangra, Indian classical, comedians, Diwali/Holi/Navratri, Garba, Sufi/Qawwali, desi parties
- **Hard excludes:** Afghan events (always), Sri Lankan/Nepali/Bangladeshi community events, generic club nights
- **Title cleaning:** strips redundant venue/city/date info, fixes spacing and capitalization
- **Lazy evaluation:** stops classifying once enough Indian events are found, saving ~90% of API costs

### Countdown Stories

For events happening within 5 days, the pipeline auto-generates Instagram Stories with countdown timers. Multiple visual styles available (neon frame, cinematic gradient, split screen), with a dark gradient CTA bar linking to tickets. Story deduplication ensures each event-day combination is only posted once.

### Artist Auto-Tagging

Performers are automatically tagged in Instagram posts using a waterfall handle lookup:

1. **Manual overrides** — curated JSON file for known ambiguous artists
2. **Wikidata P2003** — community-verified Instagram usernames with performer-type disambiguation
3. **DuckDuckGo search** — multi-candidate scoring (name similarity, brevity, frequency, context clues)
4. **LLM suggestion** — Gemini as a last resort

All candidates are verified via Instagram's **Business Discovery API** (account exists, 1000+ followers, bio matches performer type). Handles are cached in SQLite with 30-day TTL. Disambiguation handles tricky cases like "Amit Tandon" (comedian vs actor) and "Gaurav Kapoor" (comedian vs cricketer).

### Multi-Platform Publishing

- **Instagram** — professional post images + countdown stories + artist tagging via Graph API v21.0
- **Facebook** — automatic cross-posting to a Page (reuses uploaded image URL)
- **Link-in-bio** — auto-generated static HTML page deployed to GitHub Pages

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.12 with [uv](https://github.com/astral-sh/uv) package manager |
| Database | SQLite (WAL mode, committed to git) |
| Scraping | BeautifulSoup4 + requests |
| Classification | Gemini 2.5 Flash Lite via [OpenRouter](https://openrouter.ai) |
| Image Enhancement | Gemini 2.5 Flash Image Gen via OpenRouter |
| Image Rendering | Playwright + Chromium (HTML/CSS -> PNG) |
| Image Search | Wikipedia, Wikidata, Spotify, MusicBrainz, DuckDuckGo |
| Publishing | Instagram Graph API, Facebook Graph API |
| Image Hosting | [freeimage.host](https://freeimage.host) (free CDN) |
| CI/CD | GitHub Actions (cron + manual dispatch) |
| Hosting | GitHub Pages (link-in-bio) |

---

## Project Structure

```
.
+-- main.py                        # Pipeline orchestrator (--ingest / --post)
+-- models.py                      # Event dataclass
+-- requirements.txt               # Python dependencies
|
+-- scraper/
|   +-- sulekha.py                 # Sulekha event scraper (JSON-LD)
|
+-- classifier/
|   +-- indian_classifier.py       # LLM classification + title cleanup
|
+-- image_generator/
|   +-- create_post.py             # Image sourcing + Playwright post renderer
|   +-- create_story.py            # Instagram Stories countdown images
|   +-- ai_enhance.py              # Gemini-powered image enhancement
|   +-- image_search.py            # Multi-source web image search
|   +-- artist_image_sources.py    # Wikipedia/Wikidata/Spotify/MusicBrainz
|   +-- styles.py                  # HTML/CSS post templates
|
+-- publisher/
|   +-- instagram.py               # Instagram Graph API (posts + stories)
|   +-- instagram_handle.py        # Artist handle lookup + verification
|   +-- facebook.py                # Facebook Graph API cross-posting
|   +-- linkinbio.py               # Static link-in-bio page generator
|
+-- data/
|   +-- store.py                   # SQLite CRUD + story tracking + handle cache
|   +-- events.db                  # SQLite database
|   +-- instagram_handles.json     # Manual artist handle overrides
|   +-- image_cache/               # Cached images (gitignored)
|
+-- docs/
|   +-- index.html                 # Generated link-in-bio page
|   +-- architecture/              # arc42 + C4 architecture docs
|
+-- .github/workflows/
    +-- ingest.yml                 # Ingestion: scrape + classify + save to DB
    +-- post.yml                   # Posting: generate images + publish + link-in-bio
    +-- stories.yml                # Countdown stories for upcoming events
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv) package manager

### Installation

```bash
git clone https://github.com/your-username/indian.events.toronto.git
cd indian.events.toronto

uv venv
uv pip install -r requirements.txt
.venv/bin/playwright install chromium --with-deps
```

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `OPENROUTER_API_KEY` | Yes | LLM classification + vision + image generation |
| `INSTAGRAM_ACCESS_TOKEN` | For publishing | Instagram Graph API |
| `INSTAGRAM_USER_ID` | For publishing | Instagram business account ID |
| `FACEBOOK_PAGE_ID` | For Facebook | Facebook Page ID |
| `FACEBOOK_PAGE_ACCESS_TOKEN` | For Facebook | Facebook Page API token |
| `SPOTIFY_CLIENT_ID` | Optional | Artist image lookup |
| `SPOTIFY_CLIENT_SECRET` | Optional | Artist image lookup |

### Usage

```bash
# Ingest: scrape, filter, classify, save to DB
uv run python main.py --ingest

# Ingest with a classification limit (cap LLM API calls)
uv run python main.py --ingest --classify-limit 5

# Post: generate images + publish unposted events to IG + FB + link-in-bio
uv run python main.py --post --post-limit 2

# Dry run — generate images and show captions, but skip actual publishing
uv run python main.py --post --dry-run --post-limit 2

# Only publish countdown stories for upcoming events
uv run python main.py --stories-only

# Post but skip stories
uv run python main.py --post --post-limit 2 --no-stories
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--ingest` | Scrape sources, filter, classify, and save to DB |
| `--post` | Generate images and publish unposted events |
| `--post-limit N` | Max posts per run (default: 2) |
| `--classify-limit N` | Max events to classify per ingest (default: 10) |
| `--stories-only` | Only publish countdown stories |
| `--no-stories` | Skip countdown story publishing |
| `--reconcile` | Sync DB posted status with live Instagram posts (via alt_text keys) |
| `--dry-run` | Generate images and show captions but skip actual publishing |

---

## GitHub Actions

The pipeline runs automatically via three independent GitHub Actions workflows.

### Workflows

| Workflow | Schedule | Purpose |
|----------|----------|---------|
| **Ingest Events** (`ingest.yml`) | 8 AM + 5 PM EDT | Scrape, filter, classify, save to DB |
| **Post to IG + FB** (`post.yml`) | 9 AM + 6 PM EDT | Generate images, publish, update link-in-bio |
| **Countdown Stories** (`stories.yml`) | 3x daily | Publish countdown stories for upcoming events |

Ingestion and posting are fully decoupled — they communicate only through the SQLite database. The post workflow runs 1 hour after ingestion to let it finish first.

### Manual Dispatch

All three workflows support manual triggers from the Actions tab:

**Ingest Events:**

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `classify_limit` | number | `10` | Max events to classify (LLM calls) |

**Post to IG + FB:**

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `post_limit` | number | `2` | Max posts per run |
| `dry_run` | boolean | `false` | Show what would be posted without publishing |

---

## Architecture

Full arc42 + C4 documentation is available in [`docs/architecture/README.md`](docs/architecture/README.md), covering:

- System context, container, and component diagrams (C4 Levels 1-3)
- Runtime views for all pipeline modes
- Deployment architecture
- Architecture decisions and rationale
- Quality requirements and risk analysis
- Developer guide with "I want to..." recipes

### Key Design Decisions

| Decision | Why |
|----------|-----|
| **Sulekha-first images** | Source images are most relevant; selects best aspect ratio |
| **AI enhancement** (Gemini) | Removes text/watermarks, creates cinematic backgrounds |
| **Lazy classification** | Saves ~90% of LLM costs by stopping once enough events found |
| **SQLite in git** | Zero infrastructure; database travels with code |
| **Playwright rendering** | Crisp text; PIL produces blurry output |
| **Multi-source image waterfall** | Wikipedia/Wikidata identity-verified before broad search |
| **Artist handle waterfall** | Manual → Wikidata → DDG → LLM, all verified via Business Discovery |

---

## Contributing

### Making Changes

The [Developer Guide](docs/architecture/README.md#14-developer-guide--where-to-make-changes) has specific recipes for common changes:

- Adding new event sources
- Modifying classification rules
- Changing post/story visual design
- Adjusting AI enhancement prompts
- Adding new publishing destinations
- Changing posting frequency

### Key Files

| What | Where |
|------|-------|
| Pipeline orchestration | `main.py` (`--ingest` and `--post` entry points) |
| Classification rules | `classifier/indian_classifier.py` (SYSTEM_PROMPT) |
| AI enhancement prompts | `image_generator/ai_enhance.py` |
| Post visual design | `image_generator/styles.py` |
| Story visual design | `image_generator/create_story.py` |
| Instagram API | `publisher/instagram.py` |
| Artist handle lookup | `publisher/instagram_handle.py` |
| Handle overrides | `data/instagram_handles.json` |
| Database schema | `data/store.py` |
| Ingestion workflow | `.github/workflows/ingest.yml` |
| Posting workflow | `.github/workflows/post.yml` |

---

## License

This project is for personal use. The pipeline and its output are associated with the [@indian.events.toronto](https://www.instagram.com/indian.events.toronto/) Instagram account.
