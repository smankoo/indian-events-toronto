"""Find high-resolution, text-free artist images via web search."""

import base64
import hashlib
import io
import os
import re
import time
from pathlib import Path

import requests
from ddgs import DDGS
from PIL import Image

MIN_WIDTH = 600
MIN_HEIGHT = 400

CACHE_DIR = Path(__file__).parent.parent / "data" / "image_cache"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}


def cache_key(title: str) -> str:
    """Generate a stable cache key from an event title."""
    normalized = extract_search_query(title).lower().strip()
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def _get_cached(title: str) -> Image.Image | None:
    """Return cached image for this event title, or None."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{cache_key(title)}.jpg"
    if path.exists():
        try:
            return Image.open(path).convert("RGB")
        except Exception:
            path.unlink(missing_ok=True)
    return None


def _save_to_cache(title: str, img: Image.Image) -> None:
    """Save an image to the disk cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{cache_key(title)}.jpg"
    img.save(path, "JPEG", quality=95)


def extract_search_query(title: str) -> str:
    """Extract the artist/event name from a title, stripping filler."""
    cleaned = title
    patterns = [
        r'\s*[-–—]\s*Live\s+In\s+\w+.*$',
        r'\s*Live\s+In\s+\w+.*$',
        r'\s*Stand\s*-?\s*Up\s+Comedy.*$',
        r'\s*Standup\s+Comedy.*$',
        r'\s*[-–—]\s*Toronto.*$',
        r'\s*\|\s*Tickets.*$',
        r'\s*\(.*?\)\s*$',
        r'\s+\d{4}\s*$',
        r'\s*North\s+American\s+Tour.*$',
    ]
    for pat in patterns:
        cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^(?:Toronto|Brampton|Mississauga)\s*[-–—:]\s*', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip() or title


def _extract_name_only(query: str) -> str:
    """Extract just the person/band name, stripping show titles."""
    parts = re.split(r'\s*[-–—]\s*', query)
    return max(parts, key=len).strip() if parts else query


def has_significant_text(img: Image.Image) -> bool:
    """Use OpenRouter vision API to check if an image has event-specific text.

    Returns True if the image has dates, venue names, prices, or other
    event-specific text that would conflict with our overlay.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        return False  # can't check, assume clean

    # Downscale for the API call to save tokens
    thumb = img.copy()
    thumb.thumbnail((512, 512))
    buf = io.BytesIO()
    thumb.save(buf, format="JPEG", quality=70)
    b64 = base64.b64encode(buf.getvalue()).decode()

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "google/gemini-2.0-flash-lite-001",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "Does this image contain any visible text such as "
                                    "event dates, venue names, ticket prices, show titles, "
                                    "tour names, sponsor logos with text, or promotional copy? "
                                    "Small watermarks or photographer credits don't count. "
                                    "Answer ONLY 'YES' or 'NO'."
                                ),
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                        ],
                    }
                ],
                "max_tokens": 5,
            },
            timeout=15,
        )
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip().upper()
        return answer.startswith("YES")
    except Exception as e:
        print(f"    Vision check failed: {e}")
        return False  # assume clean on failure


def is_placeholder(img: Image.Image) -> bool:
    """Detect near-monochrome placeholder images (e.g. grey silhouettes).

    A real photo has high colour variance; a placeholder is nearly uniform.
    """
    import numpy as np
    arr = np.array(img.resize((64, 64))).astype(float)
    return float(arr.std()) < 18.0


def try_download(url: str, min_w: int = MIN_WIDTH, min_h: int = MIN_HEIGHT) -> Image.Image | None:
    """Download an image, verify it meets size requirements and isn't a placeholder."""
    try:
        resp = requests.get(url, timeout=8, headers=HEADERS, stream=True)
        resp.raise_for_status()
        ct = resp.headers.get("content-type", "")
        if not ct.startswith("image/"):
            return None
        data = resp.content
        if len(data) < 5000:
            return None
        img = Image.open(io.BytesIO(data)).convert("RGB")
        if img.width < min_w or img.height < min_h:
            return None
        if is_placeholder(img):
            return None
        return img
    except Exception:
        return None


import json as _json


# Valid performer types — drives the search routing strategy
PERFORMER_TYPES = ("musician", "comedian", "dj", "event", "other")


def classify_event(title: str, description: str) -> dict:
    """Ask the LLM to classify the event and generate tailored search queries.

    Returns a dict with:
      type         — one of PERFORMER_TYPES
      artist_name  — cleaned name of the main performer (empty string for type=event)
      artist_names — list of all individual performer names (for multi-artist events)
      queries      — list of 3 DuckDuckGo image search queries
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    name = _extract_name_only(extract_search_query(title))

    # Fallback if no API key
    def _fallback(t: str = "other") -> dict:
        names = [name] if name else []
        if t == "musician":
            return {"type": t, "artist_name": name, "artist_names": names,
                    "queries": [f"{name} portrait photo", f"{name} performing live", f"{name} Indian musician"]}
        if t == "comedian":
            return {"type": t, "artist_name": name, "artist_names": names,
                    "queries": [f"{name} stand-up comedian portrait", f"{name} performing", f"{name} headshot"]}
        if t == "dj":
            return {"type": t, "artist_name": name, "artist_names": names,
                    "queries": [f"{name} DJ performing", f"{name} DJ set", f"{name} Indian DJ"]}
        if t == "event":
            return {"type": t, "artist_name": "", "artist_names": [],
                    "queries": ["bollywood dance night crowd", "indian music festival atmosphere", "desi party night"]}
        return {"type": "other", "artist_name": name, "artist_names": names,
                "queries": [f"{name} portrait photo", f"{name} performing", f"{name} Indian artist"]}

    if not api_key:
        return _fallback()

    prompt = f"""Analyse this Indian event and respond with a JSON object — nothing else.

Event title: {title}
Description: {description}

JSON fields:
- "type": one of "musician", "comedian", "dj", "event", "other"
  • "musician" = singer, band, classical artist, qawwali, sufi, bhangra performer
  • "comedian" = stand-up comic, comedy show
  • "dj"       = DJ set, club night with a named DJ
  • "event"    = no single clear artist (Bollywood night, dance party, cultural show, mela)
  • "other"    = anything else with a named performer that doesn't fit above
- "artist_name": the clean searchable name of the main performer (empty string if type is "event")
- "artist_names": a list of ALL individual performer names from the title. Split collaborations
  like "A x B", "A ft. B", "A & B", "A and B" into separate entries. Each entry must be one
  real searchable person/band name — never combine multiple names into one entry.
  Empty list if type is "event".
  Examples: "Afusic X Jani Ft. Ali Soomro" → ["Afusic", "Jani", "Ali Soomro"]
            "Amit Tandon" → ["Amit Tandon"]
            "Bollywood Night" → []
- "queries": exactly 3 image search queries. Goal: find a high-quality PHOTO of the person or atmosphere
  — NOT an event poster or flyer. The image must have no text overlaid (no dates, no venue, no ticket info).

  Think: what would a photo editor search to find a usable press photo or performance shot?

  BAD (these find posters/flyers, avoid these patterns):
    "Abhishek Upmanyu tour"        ← finds tour announcement images with text
    "Sanam concert Toronto"        ← finds event flyers
    "Farhan Sabri live show"       ← finds promotional posters with dates/venues

  GOOD examples by type:
    comedian → "Abhishek Upmanyu standup photo", "Abhishek Upmanyu comedy stage", "Abhishek Upmanyu headshot"
    musician → "Farhan Sabri qawwali singer portrait", "Sanam band press photo", "Sanam performing"
    dj       → "DJ Suketu booth photo", "DJ Suketu festival stage", "DJ Suketu performing"
    event    → "bollywood dance party crowd", "indian festival celebration lights", "desi night dancing"
    other    → "<name> portrait", "<name> performance photo"

  NEVER include: tickets, tour dates, buy, book, live in [city], show poster, promo, Toronto, Canada.

Respond with a single JSON object (not an array). Use the field name "type" (not "category").
No markdown, no explanation."""

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "google/gemini-2.0-flash-lite-001",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
                "response_format": {"type": "json_object"},
            },
            timeout=15,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"]
        parsed = _json.loads(raw)
        # Model sometimes wraps in an array — unwrap it
        data = parsed[0] if isinstance(parsed, list) else parsed
        performer_type = data.get("type") or data.get("category", "other")
        if performer_type not in PERFORMER_TYPES:
            performer_type = "other"
        artist_name = str(data.get("artist_name", name)).strip()
        artist_names = [str(n).strip() for n in data.get("artist_names", []) if str(n).strip()]
        if not artist_names and artist_name:
            artist_names = [artist_name]
        queries = [q.strip().strip('"\'').lstrip("0123456789.-) ")
                   for q in data.get("queries", []) if str(q).strip()][:3]
        if not queries:
            return _fallback(performer_type)
        result = {"type": performer_type, "artist_name": artist_name, "artist_names": artist_names, "queries": queries}
        print(f"    Event classified: type={performer_type}, artists={artist_names}")
        print(f"    Queries: {queries}")
        return result
    except Exception as e:
        print(f"    Event classification failed: {e}")
        return _fallback()


def search_event_image(title: str, description: str = "", max_results: int = 15, event_info: dict | None = None) -> Image.Image | None:
    """Search for a high-quality, text-free image appropriate for the event.

    Routes differently based on performer type:
      musician → Wikipedia/Wikidata/MusicBrainz→Spotify → DuckDuckGo
      comedian → Wikipedia/Wikidata → DuckDuckGo
      dj       → Wikipedia → DuckDuckGo
      event    → DuckDuckGo with atmosphere queries (skip artist lookup)
      other    → DuckDuckGo with portrait queries

    If event_info is provided, skips the classify_event() call.
    """
    # Check disk cache first
    cached = _get_cached(title)
    if cached is not None:
        print(f"    Using cached image: {cached.width}x{cached.height}")
        return cached

    info = event_info or classify_event(title, description)
    performer_type = info["type"]
    artist_name    = info["artist_name"]
    queries        = info["queries"]

    # ── Reliable identity-verified sources (skip for event/atmosphere type) ──
    if performer_type != "event" and artist_name:
        from image_generator.artist_image_sources import (
            fetch_wikipedia, fetch_wikidata,
            fetch_musicbrainz_spotify, fetch_spotify,
        )

        # All types: try Wikipedia + Wikidata (pass performer_type for disambiguation)
        for fn, label in [(fetch_wikipedia, "Wikipedia"), (fetch_wikidata, "Wikidata")]:
            print(f"    Trying {label}...")
            img = fn(artist_name, performer_type=performer_type)
            if img:
                _save_to_cache(title, img)
                return img

        # Musicians only: try streaming-platform sources
        if performer_type == "musician":
            for fn, label in [
                (fetch_musicbrainz_spotify, "MusicBrainz→Spotify"),
                (fetch_spotify,             "Spotify direct"),
            ]:
                print(f"    Trying {label}...")
                img = fn(artist_name)
                if img:
                    _save_to_cache(title, img)
                    return img

    # ── DuckDuckGo fallback with type-appropriate queries ──
    for search_query in queries:
        print(f"    DDG (large): '{search_query}'")
        results = _search_with_retry(search_query, max_results, size="Large")
        if results:
            img = _pick_clean(results)
            if img:
                _save_to_cache(title, img)
                return img

    for search_query in queries:
        print(f"    DDG (any): '{search_query}'")
        results = _search_with_retry(search_query, max_results, size=None)
        if results:
            img = _pick_clean(results, min_w=400, min_h=300)
            if img:
                _save_to_cache(title, img)
                return img

    print(f"    Could not find an image for '{title}'")
    return None


def _pick_clean(results: list, min_w: int = MIN_WIDTH, min_h: int = MIN_HEIGHT) -> Image.Image | None:
    """Try each search result until we find one that's clean (no text, not a placeholder)."""
    for r in results:
        url = r.get("image", "")
        if not url:
            continue
        img = try_download(url, min_w=min_w, min_h=min_h)
        if img is None:
            continue
        if has_significant_text(img):
            print(f"    Skipping (has text): {url[:70]}...")
            continue
        print(f"    Found clean image: {img.width}x{img.height}")
        return img
    return None


def _search_with_retry(search_query: str, max_results: int, size: str | None = "Large") -> list | None:
    """Run a DuckDuckGo image search with retry on rate limit."""
    for attempt in range(3):
        delay = 4 + attempt * 6
        time.sleep(delay)
        try:
            kwargs = dict(query=search_query, max_results=max_results)
            if size:
                kwargs["size"] = size
            return list(DDGS().images(**kwargs))
        except Exception as e:
            if "Ratelimit" in str(e) and attempt < 2:
                print(f"    Rate limited, retrying in {delay + 8}s...")
                time.sleep(8)
                continue
            print(f"    Search failed: {e}")
            return None
    return None
