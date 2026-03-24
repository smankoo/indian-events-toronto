<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white" alt="Python 3.12">
  <img src="https://img.shields.io/badge/Playwright-Chromium-2EAD33?logo=playwright&logoColor=white" alt="Playwright">
  <img src="https://img.shields.io/badge/AI-Gemini%20Flash-4285F4?logo=google&logoColor=white" alt="Gemini Flash">
  <img src="https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white" alt="GitHub Actions">
  <img src="https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
  <img src="https://img.shields.io/badge/Instagram-Graph%20API-E4405F?logo=instagram&logoColor=white" alt="Instagram">
</p>

# Indian Events Toronto

**Automated pipeline that discovers Indian cultural events in the Toronto/GTA area and publishes them to Instagram and Facebook.** Runs unattended on GitHub Actions twice daily — scraping, classifying, AI-enhancing images, and posting with zero manual intervention.

<p align="center">
  <strong>
    <a href="https://www.instagram.com/indian.events.toronto/">Instagram</a> &bull;
    <a href="docs/architecture/README.md">Architecture Docs</a>
  </strong>
</p>

---

## How It Works

```
  Sulekha.com            Gemini Flash Lite           Gemini Flash Image
  (event source)         (classification)            (AI enhancement)
       |                       |                           |
       v                       v                           v
  +---------+   +----------+   +----------+   +---------+   +----------+
  | Scrape  |-->| Filter & |-->| Classify |-->| Enhance |-->| Generate |
  | Events  |   | Dedup    |   | (Indian?)|   | Images  |   | Posts    |
  +---------+   +----------+   +----------+   +---------+   +----------+
                                                                  |
       +----------------------------------------------------------+
       |                    |                    |
       v                    v                    v
  +-----------+   +------------------+   +---------------+
  | Instagram |   | Facebook         |   | GitHub Pages  |
  | Posts +   |   | Cross-post       |   | Link-in-bio   |
  | Stories   |   |                  |   |               |
  +-----------+   +------------------+   +---------------+
```

The pipeline runs **twice daily** (8 AM and 5 PM EDT) and:

1. **Scrapes** ~250 event listings from [Sulekha](https://events.sulekha.com/toronto-metro-area) via JSON-LD structured data
2. **Filters** to Toronto/GTA area and removes near-duplicates (>70% title similarity on same date)
3. **Classifies** each event as "Indian" or not using Gemini Flash Lite with detailed cultural rules
4. **Enhances** images using AI — replaces backgrounds for artists, generates cinematic scenes for events
5. **Renders** professional 1080x1350 Instagram posts via Playwright (HTML/CSS -> screenshot)
6. **Publishes** countdown stories (1080x1920) for events happening within 5 days
7. **Cross-posts** to Facebook and updates a static [link-in-bio](docs/index.html) page

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
+-- main.py                        # Pipeline orchestrator
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
    +-- post.yml                   # GitHub Actions CI/CD
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
# Scrape, classify, generate images (no publishing)
uv run python main.py --post-limit 2

# Full run — scrape, classify, generate, publish to Instagram + Facebook
uv run python main.py --publish --post-limit 2

# Dry run — full pipeline including artist handle lookup, but skip actual API calls
uv run python main.py --dry-run --post-limit 2

# Publish previously generated but unposted events
uv run python main.py --publish-only --post-limit 1

# Only publish countdown stories for upcoming events
uv run python main.py --stories-only

# Full run but skip stories
uv run python main.py --publish --post-limit 2 --no-stories
```

### CLI Flags

| Flag | Description |
|------|-------------|
| `--limit N` | Max images to generate (0 = all Indian events found) |
| `--publish` | Enable publishing to Instagram + Facebook |
| `--post-limit N` | Max posts per run (default: 2) |
| `--publish-only` | Skip scrape/classify, publish unposted events from DB |
| `--stories-only` | Only publish countdown stories |
| `--no-stories` | Skip countdown story publishing |
| `--dry-run` | Full pipeline with handle lookup but no actual publishing |

---

## GitHub Actions

The pipeline runs automatically via GitHub Actions on a cron schedule.

### Scheduled Runs

- **8:00 AM EDT** and **5:00 PM EDT** daily (UTC: 12:00 and 21:00)
- Publishes up to 2 posts per run + countdown stories for upcoming events

### Manual Dispatch

Trigger a run manually from the Actions tab with options:

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `publish` | boolean | `true` | Publish to Instagram |
| `post_limit` | number | `2` | Max posts per run |
| `publish_only` | boolean | `false` | Skip scrape/classify |
| `stories_only` | boolean | `false` | Only publish stories |
| `dry_run` | boolean | `false` | Full pipeline without actual publishing |

### What Happens Each Run

1. Installs Python 3.12 + dependencies + Playwright
2. Auto-refreshes the Instagram long-lived token (extends 60-day expiry)
3. Runs the pipeline with configured flags
4. Commits updated `events.db` and `docs/` back to the repo
5. Deploys `docs/` to GitHub Pages

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
| Pipeline orchestration | `main.py` |
| Classification rules | `classifier/indian_classifier.py` (SYSTEM_PROMPT) |
| AI enhancement prompts | `image_generator/ai_enhance.py` |
| Post visual design | `image_generator/styles.py` |
| Story visual design | `image_generator/create_story.py` |
| Instagram API | `publisher/instagram.py` |
| Artist handle lookup | `publisher/instagram_handle.py` |
| Handle overrides | `data/instagram_handles.json` |
| Database schema | `data/store.py` |
| CI/CD workflow | `.github/workflows/post.yml` |

---

## License

This project is for personal use. The pipeline and its output are associated with the [@indian.events.toronto](https://www.instagram.com/indian.events.toronto/) Instagram account.
