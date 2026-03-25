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
    for c in candidates:
        verified, followers = _verify_handle(
            c.handle, artist_name, performer_type, ddg_signals=c,
        )
        if verified:
            print(f"    IG handle (ddg, score={c.score}, verified): @{c.handle} ({followers} followers)")
            save_handle_cache(artist_name, performer_type, c.handle, "ddg", followers)
            return c.handle
        else:
            print(f"    IG handle (ddg): @{c.handle} — verification failed")

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


class _DdgCandidate:
    """A candidate handle from DuckDuckGo with extracted profile signals."""

    __slots__ = ("handle", "score", "followers", "following", "description", "display_name")

    def __init__(self, handle: str, score: float, followers: int, following: int,
                 description: str, display_name: str):
        self.handle = handle
        self.score = score
        self.followers = followers
        self.following = following
        self.description = description
        self.display_name = display_name


def _lookup_ddg(artist_name: str, performer_type: str) -> list[_DdgCandidate]:
    """Search DuckDuckGo, return scored candidates with extracted profile signals."""
    from ddgs import DDGS

    queries = [
        f'{artist_name} {performer_type} instagram',
        f'{artist_name} instagram',
        f'"{artist_name}" official instagram site:instagram.com',
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

        # Extract profile signals from DDG snippets
        # DDG often shows "51K Followers, 144 Following, 214 Posts" in snippets
        followers = _parse_count(combined, r"([\d,.]+[KMkm]?)\s*followers")
        following = _parse_count(combined, r"([\d,.]+[KMkm]?)\s*following")

        # Extract display name from title like "Name (@handle) - Instagram"
        display_name = ""
        for text in texts:
            title_m = re.search(r'^(.*?)\s*\(@' + re.escape(handle) + r'\)', text)
            if title_m:
                display_name = title_m.group(1).strip().lower()
                break

        scored.append(_DdgCandidate(
            handle=handle,
            score=round(score, 1),
            followers=followers,
            following=following,
            description=combined,
            display_name=display_name,
        ))

    scored.sort(key=lambda x: x.score, reverse=True)
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


FAN_KEYWORDS = ["fan account", "fan page", "fanpage", "unofficial", "parody", "tribute"]


def _parse_count(text: str, pattern: str) -> int:
    """Parse a follower/following count like '51K' or '1,234' into an integer."""
    m = re.search(pattern, text, re.IGNORECASE)
    if not m:
        return 0
    raw = m.group(1).strip().upper().replace(",", "")
    try:
        if raw.endswith("K"):
            return int(float(raw[:-1]) * 1_000)
        elif raw.endswith("M"):
            return int(float(raw[:-1]) * 1_000_000)
        return int(raw)
    except ValueError:
        return 0



def _check_profile_signals(
    followers: int,
    following: int,
    bio: str,
    name: str,
    artist_name: str,
    performer_type: str,
) -> tuple[bool, str]:
    """Evaluate profile signals. Returns (accepted, reason)."""
    # Reject fan / parody accounts
    if any(kw in bio for kw in FAN_KEYWORDS):
        return False, "fan/parody account"

    # Must have reasonable followers
    if followers < 1000:
        return False, f"too few followers ({followers})"

    # Follower/following ratio — real artists typically have high ratio
    ratio = followers / max(following, 1)

    name_parts = artist_name.lower().split()
    type_kws = TYPE_KEYWORDS.get(performer_type, [])

    bio_match = any(k in bio for k in type_kws) if type_kws else False
    name_match = any(p in name for p in name_parts)

    if (bio_match or name_match) and ratio >= 2:
        return True, "name/bio match + good ratio"

    if name_match and followers >= 5_000:
        return True, "name match + decent followers"

    # High follower count + exists = likely correct
    if followers >= 100_000:
        return True, "high follower count"

    if ratio < 1.5 and followers < 50_000:
        return False, f"suspicious ratio ({ratio:.1f}) with low followers"

    return False, "insufficient signals"


def _verify_handle(
    handle: str,
    artist_name: str,
    performer_type: str,
    ddg_signals: "_DdgCandidate | None" = None,
) -> tuple[bool, int]:
    """Verify a handle via Instagram Business Discovery API, with DDG-signal fallback.

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

        if resp.status_code == 200:
            # Business / creator account — use API data
            bd = resp.json().get("business_discovery", {})
            followers = bd.get("followers_count", 0)
            bio = bd.get("biography", "").lower()
            name = bd.get("name", "").lower()
            following = 0  # Business Discovery doesn't expose following_count

            ok, reason = _check_profile_signals(
                followers, following, bio, name, artist_name, performer_type,
            )
            if ok:
                print(f"    IG verify (business): @{handle} ✓ — {reason} ({followers} followers)")
            else:
                print(f"    IG verify (business): @{handle} ✗ — {reason}")
            return ok, followers

        # Non-200 → likely a personal account (not business/creator).
        # Use DDG snippet signals if available (follower count, display name, etc.)
        if ddg_signals and ddg_signals.followers > 0:
            ok, reason = _check_profile_signals(
                ddg_signals.followers,
                ddg_signals.following,
                ddg_signals.description,
                ddg_signals.display_name,
                artist_name,
                performer_type,
            )
            if ok:
                ratio = ddg_signals.followers / max(ddg_signals.following, 1)
                print(
                    f"    IG verify (ddg-signals): @{handle} ✓ — {reason} "
                    f"({ddg_signals.followers} followers, ratio {ratio:.1f})"
                )
            else:
                print(f"    IG verify (ddg-signals): @{handle} ✗ — {reason}")
            return ok, ddg_signals.followers

        # Last resort: accept if handle closely matches artist name
        handle_clean = handle.lower().replace("_", "").replace(".", "")
        name_clean = artist_name.lower().replace(" ", "")
        similarity = SequenceMatcher(None, name_clean, handle_clean).ratio()
        name_parts = artist_name.lower().split()
        parts_in_handle = sum(1 for p in name_parts if p in handle.lower())
        if similarity >= 0.7 and parts_in_handle >= len(name_parts):
            print(f"    IG verify (name-match fallback): @{handle} ✓ — similarity {similarity:.2f}")
            return True, 0
        return False, 0

    except Exception:
        # API error — don't block, assume unverified
        return False, 0
