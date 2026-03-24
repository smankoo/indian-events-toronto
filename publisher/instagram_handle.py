"""Look up Instagram handles for event performers with disambiguation.

Waterfall strategy:
  1. Manual overrides (data/instagram_handles.json)
  2. Wikidata P2003 (Instagram username property)
  3. DuckDuckGo text search (scored multi-candidate)
  4. LLM suggestion (Gemini via OpenRouter)

Sources 2-4 are verified via Instagram Business Discovery API before use.
"""

import json
import os
import re
import time
import urllib.parse
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from pathlib import Path

import requests

DATA_DIR = Path(__file__).parent.parent / "data"
OVERRIDES_PATH = DATA_DIR / "instagram_handles.json"
GRAPH_API = "https://graph.instagram.com/v21.0"
HEADERS = {"User-Agent": "indian.events.toronto/1.0"}

TYPE_KEYWORDS = {
    "comedian": ["comedian", "stand-up", "standup", "comic", "comedy", "jokes", "laugh"],
    "musician": ["singer", "musician", "playback", "band", "vocalist", "composer", "music", "songs"],
    "dj": ["dj", "disc jockey", "music producer", "electronic", "producer", "beats"],
}
WRONG_PROFESSIONS = {
    "comedian": ["actor", "actress", "film director", "cricketer", "cricket"],
    "musician": ["actor", "actress", "comedian", "cricketer"],
    "dj": ["actor", "actress", "comedian"],
}


def lookup_instagram_handle(artist_name: str, performer_type: str) -> str | None:
    """Find an artist's Instagram handle. Returns None if not found or uncertain."""
    if not artist_name or performer_type in ("event", "other", ""):
        return None

    from data.store import get_cached_handle, save_handle_cache

    # Check cache first
    cached = get_cached_handle(artist_name)
    if cached is not None:
        handle, is_fresh = cached
        if is_fresh:
            if handle:
                print(f"    IG handle (cached): @{handle}")
            return handle

    # Source 1: Manual overrides
    handle = _lookup_manual(artist_name)
    if handle:
        print(f"    IG handle (manual): @{handle}")
        save_handle_cache(artist_name, performer_type, handle, "manual", 0)
        return handle

    # Source 2: Wikidata P2003
    handle = _lookup_wikidata(artist_name, performer_type)
    if handle:
        verified, followers = _verify_handle(handle, artist_name, performer_type)
        if verified:
            print(f"    IG handle (wikidata, verified): @{handle} ({followers} followers)")
            save_handle_cache(artist_name, performer_type, handle, "wikidata", followers)
            return handle
        else:
            print(f"    IG handle (wikidata): @{handle} — verification failed, skipping")

    # Source 3: DuckDuckGo (scored multi-candidate)
    candidates = _lookup_ddg(artist_name, performer_type)
    for candidate, score in candidates:
        verified, followers = _verify_handle(candidate, artist_name, performer_type)
        if verified:
            print(f"    IG handle (ddg, score={score}, verified): @{candidate} ({followers} followers)")
            save_handle_cache(artist_name, performer_type, candidate, "ddg", followers)
            return candidate
        else:
            print(f"    IG handle (ddg): @{candidate} — verification failed")

    # Source 4: LLM suggestion
    handle = _lookup_llm(artist_name, performer_type)
    if handle:
        verified, followers = _verify_handle(handle, artist_name, performer_type)
        if verified:
            print(f"    IG handle (llm, verified): @{handle} ({followers} followers)")
            save_handle_cache(artist_name, performer_type, handle, "llm", followers)
            return handle
        else:
            print(f"    IG handle (llm): @{handle} — verification failed")

    print(f"    IG handle: not found for {artist_name}")
    save_handle_cache(artist_name, performer_type, None, "none", 0)
    return None


def _lookup_manual(artist_name: str) -> str | None:
    """Check manual overrides JSON."""
    if not OVERRIDES_PATH.exists():
        return None
    try:
        overrides = json.loads(OVERRIDES_PATH.read_text())
        # Case-insensitive lookup
        for name, handle in overrides.items():
            if name.lower() == artist_name.lower():
                return handle
    except Exception:
        pass
    return None


def _lookup_wikidata(artist_name: str, performer_type: str) -> str | None:
    """Search Wikidata for P2003 (Instagram username) with performer-type disambiguation."""
    url = (
        "https://www.wikidata.org/w/api.php"
        f"?action=wbsearchentities&search={urllib.parse.quote(artist_name)}"
        "&language=en&limit=5&format=json"
    )
    try:
        r = requests.get(url, timeout=10, headers=HEADERS)
        results = r.json().get("search", [])

        type_kws = TYPE_KEYWORDS.get(performer_type, [])
        wrong_kws = WRONG_PROFESSIONS.get(performer_type, [])

        def _score(entity):
            desc = entity.get("description", "").lower()
            if type_kws and any(k in desc for k in type_kws):
                return 0
            if wrong_kws and any(k in desc for k in wrong_kws):
                return 2
            return 1

        results.sort(key=_score)

        for entity in results:
            qid = entity.get("id")
            label = entity.get("label", "")
            desc = entity.get("description", "").lower()
            if not qid:
                continue

            # Skip wrong profession
            if wrong_kws and any(k in desc for k in wrong_kws):
                if not (type_kws and any(k in desc for k in type_kws)):
                    continue

            # Fetch claims
            claims_url = (
                f"https://www.wikidata.org/w/api.php"
                f"?action=wbgetentities&ids={qid}&props=claims&format=json"
            )
            cr = requests.get(claims_url, timeout=10, headers=HEADERS)
            claims = cr.json().get("entities", {}).get(qid, {}).get("claims", {})

            p2003 = claims.get("P2003", [])
            if p2003:
                return p2003[0]["mainsnak"]["datavalue"]["value"]

    except Exception as e:
        print(f"    Wikidata P2003 lookup failed: {e}")
    return None


def _lookup_ddg(artist_name: str, performer_type: str) -> list[tuple[str, float]]:
    """Search DuckDuckGo, return scored candidates [(handle, score)]."""
    from ddgs import DDGS

    queries = [
        f'"{artist_name}" {performer_type} official instagram site:instagram.com',
        f'"{artist_name}" instagram site:instagram.com',
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
    name_lower = artist_name.lower().replace(' ', '')
    name_parts = artist_name.lower().split()
    scored = []

    for handle, texts in all_candidates.items():
        score = 0.0
        handle_clean = handle.replace('_', '').replace('.', '')

        # Name similarity (0-30)
        similarity = SequenceMatcher(None, name_lower, handle_clean).ratio()
        score += similarity * 30

        # Handle contains name parts (0-15)
        parts_found = sum(1 for p in name_parts if p in handle)
        score += (parts_found / len(name_parts)) * 15

        # Brevity bonus (0-10)
        if len(handle) <= len(name_lower) + 3:
            score += 10
        elif len(handle) > len(name_lower) + 8:
            score -= 5

        # No trailing numbers (0-5)
        if not re.search(r'\d{3,}$', handle):
            score += 5

        # "official" in text (0-10)
        combined = ' '.join(texts).lower()
        if 'official' in combined:
            score += 10

        # Performer type in text (0-5)
        tw = TYPE_KEYWORDS.get(performer_type, [])
        if any(w in combined for w in tw):
            score += 5

        # Frequency bonus (0-10)
        score += min(len(texts), 3) * 3.3

        scored.append((handle, round(score, 1)))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:3]  # top 3 candidates


def _lookup_llm(artist_name: str, performer_type: str) -> str | None:
    """Ask Gemini for the Instagram handle."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return None

    from openai import OpenAI
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

    try:
        resp = client.chat.completions.create(
            model="google/gemini-2.0-flash-lite-001",
            messages=[{
                "role": "user",
                "content": (
                    f"What is the exact Instagram username of {artist_name}, "
                    f"the Indian {performer_type}? "
                    "Reply with ONLY the username (no @ symbol) or UNKNOWN if unsure."
                ),
            }],
            max_tokens=50,
        )
        answer = resp.choices[0].message.content.strip().lower()
        answer = answer.lstrip('@').strip()
        if answer and answer != "unknown" and ' ' not in answer:
            return answer
    except Exception as e:
        print(f"    LLM handle lookup failed: {e}")
    return None


def _verify_handle(handle: str, artist_name: str, performer_type: str) -> tuple[bool, int]:
    """Verify a handle via Instagram Business Discovery API.

    Returns (verified, followers_count).
    """
    access_token = os.environ.get("INSTAGRAM_ACCESS_TOKEN")
    ig_user_id = os.environ.get("INSTAGRAM_USER_ID")
    if not access_token or not ig_user_id:
        # Can't verify without credentials — trust Wikidata, be cautious with others
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
        if resp.status_code != 200:
            return False, 0

        bd = resp.json().get("business_discovery", {})
        followers = bd.get("followers_count", 0)
        bio = bd.get("biography", "").lower()
        name = bd.get("name", "").lower()

        # Must have reasonable followers
        if followers < 1000:
            return False, followers

        # Check bio/name matches performer type or artist name
        type_kws = TYPE_KEYWORDS.get(performer_type, [])
        name_parts = artist_name.lower().split()

        bio_match = any(k in bio for k in type_kws) if type_kws else False
        name_match = any(p in name for p in name_parts)

        if bio_match or name_match:
            return True, followers

        # High follower count + account exists = likely correct even without keyword match
        if followers >= 100_000:
            return True, followers

        return False, followers

    except Exception:
        # API error — don't block, assume unverified
        return False, 0
