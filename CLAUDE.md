# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Automated pipeline that discovers Indian cultural events in Toronto/GTA from Sulekha.com and publishes them to Instagram and Facebook. Runs on GitHub Actions with zero manual intervention. All state lives in a git-committed SQLite database.

## Commands

```bash
# Always use uv, never raw pip/python
uv run python main.py --ingest                        # Scrape → classify → profile → enrich → score
uv run python main.py --ingest --classify-limit 5     # Limit classification (saves API cost)
uv run python main.py --profile [--include-past]      # Extract headliners/category/series (LLM + flyer)
uv run python main.py --score [--include-past]        # Popularity signals → headliner/notable/listing tier
uv run python main.py --post --dry-run                # Preview what would be posted (renders images)
uv run python main.py --post --post-limit 2           # Render + publish headliner/notable events to IG/FB
uv run python main.py --roundup --dry-run             # Render the weekend-roundup carousel
uv run python main.py --stories-only                  # Publish countdown stories only
uv run python main.py --reconcile                     # Sync DB with live IG posts
uv run python main.py --backfill-handles              # Look up IG handles for all future events
uv run python scripts/validate.py                     # Offline end-to-end check (stubs all network)
```

## Architecture: Two-Stage Pipeline

Stages communicate **only through SQLite** — they run on independent schedules and must stay decoupled.

### Stage 1: Ingestion (`--ingest`)
1. **Scrape** — `scraper/sulekha.py` fetches JSON-LD structured data + detail pages
2. **Filter** — GTA geography check (`main.py:is_gta_event`), dedup by date+title similarity
3. **Classify** — `classifier/indian_classifier.py` uses Gemini 3.5 Flash Lite via OpenRouter. Lazy evaluation: stops after `classify_limit` Indian events found
4. **Profile** — `classifier/profile.py` sends title, description *and flyer images* to an LLM (`PROFILE_MODEL`) → headliners (and which flyer pictures them), display name, subtitle, category, series, prominence 1-5. The flyer matters: headliners are often only on it.
5. **Enrich** — `publisher/instagram_handle.py` waterfall lookup for headliners' IG handles (manual → Wikidata → DuckDuckGo → LLM → Business Discovery API verification)
6. **Score** — `scoring/` → tier. Score = artist reach 45 (strongest headliner across Instagram, YouTube, Spotify, Wikipedia pageviews, cross-checked so a single unverified match is discounted) + LLM prominence 25 + venue size 15 + price 15. `headliner` ≥ 55, `notable` ≥ 30, else `listing`. Stats cached per artist in `artist_stats` (30 days).

### Stage 2: Posting (`--post`) — what gets posted depends on tier
1. **Select** — `main.py:select_for_posting`: headliners first, then notable; listing-tier events are never posted individually. Repeats of an already-posted show (same series + headliners within 45 days) are skipped and marked `covered_by`.
2. **Render** — `image_generator/poster.py`:
   - headliner → `hero_plate.py` turns a *real* photo of the headliner (from the flyer, else Wikipedia/Wikidata) into a clean, text-free, category-lit portrait via an image model (`IMAGE_MODEL`: Flash in dev, Pro in the post workflow), then `render_headliner` sets the artist name over it. No real photo → no AI; falls back to the card. Never ask the model to invent a person.
   - notable → `render_card`: typographic card, palette by category (`design.py`)
3. **Publish** — `publisher/instagram.py` uploads to freeimage.host, posts via IG Graph API with artist tags
4. **Cross-post** — `publisher/facebook.py` shares same image to Facebook
5. **Stories** — `image_generator/create_story.py` countdown stories, headliner tier only
6. **Link-in-bio** — `publisher/linkinbio.py` regenerates `docs/index.html` with *every* upcoming event (listing-tier events live here + in the roundup)
7. **Admin export** — `publisher/admin_export.py` updates `docs/admin/events.json` (includes tier, score breakdown, profile)

### Stage 3: Stories (`--stories-only`)
Independent daily run. Publishes countdown stories, tracks which event-day combos are already published.

### Stage 4: Weekend roundup (`--roundup`)
Weekly carousel ("This weekend in the GTA"): cover + list slides covering all tiers for the coming Fri–Sun, one entry per show. Tracked in the `roundups` table so a weekend is only posted once. Thumbnails reuse the headliner posters already published (the AI image cache is not committed).

## Key Design Principle: Process Independence

Anything that doesn't need to be tied together should not be tied together. Ingest, post, and stories run as independent GitHub Actions workflows on independent schedules. When adding new functionality, follow this pattern — if a process can run asynchronously from existing ones, make it a separate workflow/command.

## Workflows (`.github/workflows/`)
- `ingest.yml` — 8 AM & 5 PM EDT, runs `--ingest`
- `post.yml` — 9 AM & 6 PM EDT (offset from ingest), runs `--reconcile` then `--post`, updates GitHub Pages
- `stories.yml` — 1 AM EDT daily, runs `--stories-only`
- `roundup.yml` — Thursdays ~6 PM EDT, runs `--roundup`

All workflows auto-refresh the IG access token and commit updated `data/events.db` back to git.

## Classification Rules

The LLM classifier in `classifier/indian_classifier.py` has nuanced inclusion/exclusion rules baked into its system prompt. Key boundaries:
- **Include**: Bollywood, Indian classical, desi parties, garba, Indian comedians, Sufi/Qawwali, "Bollywood x [genre]" crossovers
- **Exclude (hard)**: Afghan events (always), Sri Lankan/Nepali/Bangladeshi-specific, Caribbean unless explicitly Indo-Caribbean, generic club nights
- Manual overrides for specific artists live in `data/instagram_handles.json`

## Image Pipeline

All rendering is Pillow-based. Fonts (OFL) live in `fonts/`: Anton (headlines), Playfair Display (cards), Inter (UI text).
- `design.py` — palettes per category (party rotates through variants so club nights don't all look alike), text fitting helpers
- `hero_plate.py` — AI artist portrait for headliners; cached in `data/image_cache/plates/` (gitignored)
- `poster.py` — headliner poster, typographic card, roundup slides
- Never render text with the image model; all text is set by Pillow.

## Database

SQLite at `data/events.db` with WAL mode, committed to git by the workflows. **Don't commit it from feature branches** — the bots commit it to `main` several times a day and a binary DB can't be merged; schema changes auto-migrate at runtime instead. For local experiments, point `EVENTS_DB` at a copy (`cp data/events.db /tmp/dev.db; EVENTS_DB=/tmp/dev.db uv run python main.py ...`).
- `processed_events` — PK: `(source, source_id)`, tracks classification, profile (`profile_json`), tier/score (`score_json` breakdown), posting/coverage, story status
- `instagram_handles` — PK: `artist_name`, 30-day TTL cache for handle lookups
- `artist_stats` — per-artist popularity signals (30-day TTL)
- `roundups` — weekends already published

Schema auto-migrates in `data/store.py:get_connection()`.

## Environment Variables

Required (GitHub secrets): `OPENROUTER_API_KEY`, `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_USER_ID`, `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_ACCESS_TOKEN`

Optional: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `YOUTUBE_API_KEY` (popularity signals); `IMAGE_MODEL` (hero plates, default `google/gemini-3.1-flash-image`; post workflow uses `google/gemini-3-pro-image`); `PROFILE_MODEL` (default `google/gemini-3.8-flash`)
