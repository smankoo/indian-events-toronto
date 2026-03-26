# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Automated pipeline that discovers Indian cultural events in Toronto/GTA from Sulekha.com and publishes them to Instagram and Facebook. Runs on GitHub Actions with zero manual intervention. All state lives in a git-committed SQLite database.

## Commands

```bash
# Always use uv, never raw pip/python
uv run python main.py --ingest                        # Scrape + classify + enrich
uv run python main.py --ingest --classify-limit 5     # Limit classification (saves API cost)
uv run python main.py --post --dry-run                # Preview what would be posted
uv run python main.py --post --post-limit 2           # Generate images + publish to IG/FB
uv run python main.py --stories-only                  # Publish countdown stories only
uv run python main.py --reconcile                     # Sync DB with live IG posts
uv run python main.py --backfill-handles              # Look up IG handles for all future events
uv run python test_ai_enhance.py                      # Test image generation
```

## Architecture: Two-Stage Pipeline

Stages communicate **only through SQLite** — they run on independent schedules and must stay decoupled.

### Stage 1: Ingestion (`--ingest`)
1. **Scrape** — `scraper/sulekha.py` fetches JSON-LD structured data + detail pages
2. **Filter** — GTA geography check (`main.py:is_gta_event`), dedup by date+title similarity
3. **Classify** — `classifier/indian_classifier.py` uses Gemini 2.5 Flash Lite via OpenRouter. Lazy evaluation: stops after `classify_limit` Indian events found
4. **Enrich** — `publisher/instagram_handle.py` waterfall lookup for artist IG handles (manual → Wikidata → DuckDuckGo → LLM → Business Discovery API verification)

### Stage 2: Posting (`--post`)
1. **Generate** — `image_generator/create_post.py` renders 1080x1350 images with Pillow (saffron/dark theme)
2. **Publish** — `publisher/instagram.py` uploads to freeimage.host, posts via IG Graph API with artist tags
3. **Cross-post** — `publisher/facebook.py` shares same image to Facebook
4. **Stories** — `image_generator/create_story.py` renders 1080x1920 countdown stories for events within 5 days
5. **Link-in-bio** — `publisher/linkinbio.py` regenerates static page at `docs/index.html`
6. **Admin export** — `publisher/admin_export.py` updates `docs/admin/events.json`

### Stage 3: Stories (`--stories-only`)
Independent daily run. Publishes countdown stories, tracks which event-day combos are already published.

## Key Design Principle: Process Independence

Anything that doesn't need to be tied together should not be tied together. Ingest, post, and stories run as independent GitHub Actions workflows on independent schedules. When adding new functionality, follow this pattern — if a process can run asynchronously from existing ones, make it a separate workflow/command.

## Workflows (`.github/workflows/`)
- `ingest.yml` — 8 AM & 5 PM EDT, runs `--ingest`
- `post.yml` — 9 AM & 6 PM EDT (offset from ingest), runs `--reconcile` then `--post`, updates GitHub Pages
- `stories.yml` — 1 AM EDT daily, runs `--stories-only`

All workflows auto-refresh the IG access token and commit updated `data/events.db` back to git.

## Classification Rules

The LLM classifier in `classifier/indian_classifier.py` has nuanced inclusion/exclusion rules baked into its system prompt. Key boundaries:
- **Include**: Bollywood, Indian classical, desi parties, garba, Indian comedians, Sufi/Qawwali, "Bollywood x [genre]" crossovers
- **Exclude (hard)**: Afghan events (always), Sri Lankan/Nepali/Bangladeshi-specific, Caribbean unless explicitly Indo-Caribbean, generic club nights
- Manual overrides for specific artists live in `data/instagram_handles.json`

## Image Pipeline

Three strategies based on event type (determined by `image_generator/image_search.py:classify_event`):
1. **Solo artist** — Source artist photo from Sulekha/Wikipedia/Wikidata/Spotify, enhance with Gemini
2. **Group/party** — Enhance crowd image or generate scene
3. **Non-performance** — Generate mood scene from scratch

All rendering is Pillow-based (not Playwright). Images cached by title hash in `data/image_cache/`.

## Database

SQLite at `data/events.db` with WAL mode, committed to git. Two tables:
- `processed_events` — PK: `(source, source_id)`, tracks classification, posting status, story status, `has_alt_text` flag
- `instagram_handles` — PK: `artist_name`, 30-day TTL cache for handle lookups

Schema auto-migrates in `data/store.py:get_connection()`.

## Reconciliation (`--reconcile`)

Runs before `--post` in the posting workflow. Matches DB events to live IG posts via alt_text keys (`iet::source::source_id`). Only acts on events with `has_alt_text=1` — legacy posts (pre-alt_text) are left alone because caption-based matching is too brittle (titles can be cleaned after posting).

## Environment Variables

Required (GitHub secrets): `OPENROUTER_API_KEY`, `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_USER_ID`, `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_ACCESS_TOKEN`

Optional: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`
