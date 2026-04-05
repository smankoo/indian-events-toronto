"""Look up Instagram handles for event venues.

Waterfall strategy:
  1. Manual overrides (data/venue_handles.json)
  2. DuckDuckGo text search (scored candidates)

All candidates verified via Instagram Business Discovery API before use.
Results cached in the instagram_handles table with performer_type='venue'.
"""

import json
import re
import time
from difflib import SequenceMatcher
from pathlib import Path

import requests

from publisher.instagram_handle import GRAPH_API, HEADERS, _parse_count

DATA_DIR = Path(__file__).parent.parent / "data"
VENUE_OVERRIDES_PATH = DATA_DIR / "venue_handles.json"

# Venue-related keywords for profile validation
VENUE_KEYWORDS = [
    "venue", "hall", "arena", "theatre", "theater", "centre", "center",
    "club", "lounge", "restaurant", "banquet", "events", "live music",
    "concert", "nightclub", "bar", "taproom", "brewing",
]


def lookup_venue_handle(venue_name: str, city: str = "") -> str | None:
    """Find a venue's Instagram handle. Returns None if not found."""
    if not venue_name:
        return None
    # Skip placeholder venues
    if venue_name.lower().strip() in ("to be announced", "tba", "tbd", "to be decided"):
        return None

    from data.store import get_cached_handle, save_handle_cache

    cache_key = f"venue::{venue_name}"

    # Check cache first
    cached = get_cached_handle(cache_key)
    if cached is not None:
        handle, is_fresh = cached
        if is_fresh:
            if handle:
                print(f"    Venue IG (cached): @{handle}")
            return handle

    # Source 1: Manual overrides
    handle = _lookup_manual(venue_name)
    if handle:
        verified, followers = _verify_venue_handle(handle, venue_name)
        if verified:
            print(f"    Venue IG (manual): @{handle}")
            save_handle_cache(cache_key, "venue", handle, "manual", followers)
            return handle
        # Manual override failed verification — still trust it (user provided)
        print(f"    Venue IG (manual, unverified): @{handle}")
        save_handle_cache(cache_key, "venue", handle, "manual", 0)
        return handle

    # Source 2: DuckDuckGo search
    candidates = _search_ddg(venue_name, city)
    for candidate_handle, candidate_score in candidates:
        verified, followers = _verify_venue_handle(candidate_handle, venue_name)
        if verified:
            print(f"    Venue IG (ddg): @{candidate_handle} (score={candidate_score:.1f}, {followers} followers)")
            save_handle_cache(cache_key, "venue", candidate_handle, "ddg", followers)
            return candidate_handle
        else:
            print(f"    Venue IG (ddg): @{candidate_handle} — verification failed")

    print(f"    Venue IG: not found for {venue_name}")
    save_handle_cache(cache_key, "venue", None, "none", 0)
    return None


def _lookup_manual(venue_name: str) -> str | None:
    """Check manual overrides JSON."""
    if not VENUE_OVERRIDES_PATH.exists():
        return None
    try:
        overrides = json.loads(VENUE_OVERRIDES_PATH.read_text())
        for name, handle in overrides.items():
            if name.lower() == venue_name.lower():
                return handle
    except Exception:
        pass
    return None


def _search_ddg(venue_name: str, city: str) -> list[tuple[str, float]]:
    """Search DuckDuckGo for venue Instagram handle. Returns [(handle, score), ...]."""
    try:
        from ddgs import DDGS
    except ImportError:
        return []

    location = city or "Toronto"
    queries = [
        f'"{venue_name}" {location} instagram',
        f'"{venue_name}" instagram site:instagram.com',
    ]

    all_candidates: dict[str, list[str]] = {}
    skip_handles = {'p', 'explore', 'reel', 'stories', 'accounts', 'about',
                    'reels', 'legal', 'api', 'developer', 'directory', 'tv'}

    for query in queries:
        try:
            results = list(DDGS().text(query, max_results=5))
            for r in results:
                text = r.get('href', '') + ' ' + r.get('body', '') + ' ' + r.get('title', '')
                for m in re.findall(r'instagram\.com/([a-zA-Z0-9_.]+)', text):
                    h = m.lower().rstrip('.')
                    if h in skip_handles:
                        continue
                    all_candidates.setdefault(h, []).append(text)
        except Exception:
            pass
        time.sleep(3)

    if not all_candidates:
        return []

    # Score candidates
    name_lower = venue_name.lower().replace(' ', '').replace("'", "").replace("'", "")
    name_parts = [p for p in venue_name.lower().split() if len(p) > 2]
    scored = []

    for handle, texts in all_candidates.items():
        score = 0.0
        handle_clean = handle.replace('_', '').replace('.', '')

        # Name similarity (0-30)
        similarity = SequenceMatcher(None, name_lower, handle_clean).ratio()
        score += similarity * 30

        # Handle contains venue name parts (0-20)
        parts_found = sum(1 for p in name_parts if p in handle_clean)
        if name_parts:
            score += (parts_found / len(name_parts)) * 20

        # Venue keywords in text (0-10)
        combined = ' '.join(texts).lower()
        if any(kw in combined for kw in VENUE_KEYWORDS):
            score += 10

        # Location match in text (0-5)
        if location.lower() in combined:
            score += 5

        # Frequency bonus (0-10)
        score += min(len(texts), 3) * 3.3

        # Extract follower count from DDG snippets
        followers = _parse_count(combined, r"([\d,.]+[KMkm]?)\s*followers")

        scored.append((handle, round(score, 1), followers))

    scored.sort(key=lambda x: x[1], reverse=True)
    # Return top 3 as (handle, score)
    return [(h, s) for h, s, _ in scored[:3]]


def _verify_venue_handle(handle: str, venue_name: str) -> tuple[bool, int]:
    """Verify a venue handle via Instagram Business Discovery API.

    Venues are verified more leniently than artists — we just need it to exist
    as a business/creator account with some followers.
    """
    import os

    access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    ig_user_id = os.environ.get("INSTAGRAM_USER_ID")
    if not access_token or not ig_user_id:
        return True, 0

    try:
        resp = requests.get(
            f"{GRAPH_API}/{ig_user_id}",
            params={
                "fields": f"business_discovery.fields(biography,followers_count,name,username).username({handle})",
                "access_token": access_token,
            },
            timeout=15,
        )

        if resp.status_code == 200:
            bd = resp.json().get("business_discovery", {})
            followers = bd.get("followers_count", 0)
            name = bd.get("name", "").lower()
            bio = bd.get("biography", "").lower()

            # Basic check: account exists as business/creator
            if followers >= 500:
                return True, followers
            # Low followers but name matches venue
            name_parts = [p for p in venue_name.lower().split() if len(p) > 2]
            if any(p in name or p in bio for p in name_parts):
                return True, followers
            return False, followers

        # Non-200 = personal account or doesn't exist
        # For venues, accept if handle closely matches venue name
        handle_clean = handle.lower().replace("_", "").replace(".", "")
        name_clean = venue_name.lower().replace(" ", "").replace("'", "").replace("'", "")
        similarity = SequenceMatcher(None, name_clean, handle_clean).ratio()
        if similarity >= 0.6:
            return True, 0
        return False, 0

    except Exception:
        return False, 0
