"""Artist popularity signals, cross-checked across platforms.

Each platform lookup returns raw numbers plus how confident we are that we found the
right person. Results are cached per artist in the `artist_stats` table (30-day TTL).

  instagram  — followers, from the existing IG handle cache (publisher/instagram_handle.py)
  youtube    — channel subscribers + total views         (needs YOUTUBE_API_KEY)
  spotify    — artist followers + popularity (0-100)     (needs SPOTIFY_CLIENT_ID/SECRET)
  wikipedia  — English article + pageviews, last 60 days (no key)

A platform being unavailable (no key, rate-limited) is recorded as "unavailable", not as
"no presence", so the score can tell missing data apart from a genuinely small artist.
"""

import math
import os
import re
import time
import unicodedata
from datetime import date, timedelta
from urllib.parse import quote

import requests

from data.store import get_artist_stats, save_artist_stats, get_cached_instagram

UA = {"User-Agent": "indian-events-toronto/1.0 (https://github.com/smankoo/indian-events-toronto; bot)"}

# Words in a Wikidata short description that mark a performer (a person or act, not a
# film/song/series that happens to share the name — "Shaadi" is also a 1962 film).
ENTERTAINER_WORDS = re.compile(
    r"singer|actor|actress|comedian|musician|rapper|composer|\bdj\b|disc jockey|poet|\bband\b|"
    r"dancer|model|vocalist|producer|songwriter|lyricist|entertainer|personality|influencer|"
    r"youtuber|guru|qawwal|presenter|\bhost\b|duo|group|orchestra|storyteller|artist",
    re.IGNORECASE,
)

SOUTH_ASIAN = re.compile(
    r"india|pakistan|bollywood|punjab|gujarat|tamil|telugu|malayal|hindi|urdu|bengal|bangla|"
    r"marath|kannad|sindh|nepal|sufi|qawwal|desi|south asian|canad", re.IGNORECASE)
OTHER_NATIONALITY = re.compile(
    r"korean|japanese|chinese|italian|american|british|french|german|spanish|mexican|brazil|"
    r"australian|nigerian|russian|turkish|irish|swedish|dutch|filipin|argentin|colombian|"
    r"jamaican|ghanaian|puerto ric|polish|greek|portuguese", re.IGNORECASE)
# Profile role → words a matching Wikidata description should contain (one-word names only)
ROLE_WORDS = {
    "singer": r"singer|vocalist|musician|composer|band|qawwal",
    "band": r"band|group|musician|singer",
    "musician": r"musician|singer|composer|instrument|band|player",
    "comedian": r"comedian|comic|stand-up|standup",
    "dj": r"\bdj\b|disc jockey|producer",
    "actor": r"actor|actress",
    "dancer": r"dancer|choreograph|actress|actor",
    "poet": r"poet|writer|lyricist|storyteller",
}


def accept_description(desc: str, artist: str, role: str = "") -> bool:
    """Is this Wikidata entity plausibly the artist performing in the GTA Indian scene?

    The name alone isn't enough: "Exo" (a Toronto DJ) also names a K-pop band with 68
    Wikipedias. The entity must be a performer and not explicitly another nationality.
    One-word names (stage names, common first names) must also be South Asian or Canadian
    and match the role the event bills them in.
    """
    desc = desc or ""
    if not ENTERTAINER_WORDS.search(desc):
        return False
    south_asian = bool(SOUTH_ASIAN.search(desc))
    if OTHER_NATIONALITY.search(desc) and not south_asian:
        return False
    if len(norm(artist).split()) == 1:
        if not south_asian:
            return False
        words = ROLE_WORDS.get(role)
        if words and not re.search(words, desc, re.IGNORECASE):
            return False
    return True


# log-scale ranges: (value that scores 0, value that scores 1)
RANGES = {
    "instagram": (1_000, 5_000_000),
    "youtube": (1_000, 10_000_000),
    "spotify": (1_000, 5_000_000),
    "wikipedia": (300, 300_000),   # pageviews over 60 days
    "sitelinks": (1, 40),          # number of language Wikipedias with an article
}


def norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\(.*?\)", " ", s)
    s = re.sub(r"\b(dj|the|official|music|live|band)\b", " ", s)
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", s).split())


def names_match(candidate: str, artist: str) -> bool:
    """True if every token of the artist's name appears in the candidate (or squashed together)."""
    a, c = norm(artist), norm(candidate)
    if not a or not c:
        return False
    if a == c or a.replace(" ", "") == c.replace(" ", ""):
        return True
    tokens, ctoks = a.split(), c.split()
    if len(tokens) == 1:
        return False  # one-word names (stage names, bands) must match exactly
    # every token present, allowing one extra (a middle name or "Singh"-style addition)
    return all(t in ctoks for t in tokens) and len(ctoks) <= len(tokens) + 1


def log_scale(value: float, kind: str) -> float:
    lo, hi = RANGES[kind]
    if not value or value <= lo:
        return 0.0
    return min(1.0, math.log10(value / lo) / math.log10(hi / lo))


# Hosts that answered 429 repeatedly this run; skipped until the process ends so one
# rate-limited service can't stall a whole ingest. Their results are recorded as
# "unavailable" and retried on the next run.
_tripped: set[str] = set()
_last_call: dict[str, float] = {}
MIN_INTERVAL = 0.5  # seconds between requests to the same host (be polite to Wikimedia)


def _get(url: str, params: dict | None = None, headers: dict | None = None, tries: int = 2):
    """GET with a short Retry-After wait and a per-host circuit breaker. Returns Response or None."""
    host = url.split("/")[2]
    if host in _tripped:
        return None
    for attempt in range(tries):
        wait = _last_call.get(host, 0) + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[host] = time.monotonic()
        try:
            r = requests.get(url, params=params, headers={**UA, **(headers or {})}, timeout=15)
        except requests.RequestException as e:
            print(f"      {host}: {e}")
            return None
        if r.status_code != 429:
            return r
        if attempt < tries - 1:
            time.sleep(min(int(r.headers.get("retry-after", "5") or 5), 10) + 1)
    print(f"      {host}: rate-limited, skipping it for the rest of this run")
    _tripped.add(host)
    return None


# ── Wikipedia / Wikidata ───────────────────────────────────────────────────

def _pageviews(enwiki_title: str) -> int | None:
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=59)
    r = _get(
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/"
        f"all-access/user/{quote(enwiki_title.replace(' ', '_'), safe='')}/daily/"
        f"{start:%Y%m%d}/{end:%Y%m%d}"
    )
    if r is None:
        return None
    if r.status_code == 404:
        return 0
    if r.status_code != 200:
        return None
    return sum(i.get("views", 0) for i in r.json().get("items", []))


def wikipedia_stats(artist: str, role: str = "") -> dict:
    """Encyclopedic notability via Wikidata: is there an entertainer entity with this name,
    in how many language Wikipedias, and (when Wikimedia allows) its English pageviews."""
    r = _get("https://www.wikidata.org/w/api.php", params={
        "action": "wbsearchentities", "search": artist, "language": "en", "type": "item",
        "limit": 7, "format": "json",
    })
    if r is None or r.status_code != 200:
        return {"status": "unavailable", "reason": f"wikidata HTTP {getattr(r, 'status_code', 'error')}"}
    ids = [c["id"] for c in r.json().get("search", [])
           if names_match(c.get("label", ""), artist)
           and accept_description(c.get("description", ""), artist, role)]
    if not ids:
        return {"status": "none"}
    r = _get("https://www.wikidata.org/w/api.php", params={
        "action": "wbgetentities", "ids": "|".join(ids[:5]), "props": "sitelinks|descriptions",
        "languages": "en", "format": "json",
    })
    if r is None or r.status_code != 200:
        return {"status": "unavailable", "reason": "wikidata entity lookup failed"}
    best = None
    for qid, ent in r.json().get("entities", {}).items():
        links = ent.get("sitelinks", {})
        n = sum(1 for k in links if k.endswith("wiki") and k not in ("commonswiki", "specieswiki"))
        if not best or n > best["sitelinks"]:
            best = {"qid": qid, "sitelinks": n,
                    "description": ent.get("descriptions", {}).get("en", {}).get("value", ""),
                    "enwiki": links.get("enwiki", {}).get("title")}
    out = {"status": "ok", **best, "confidence": "high"}
    if best["enwiki"]:
        views = _pageviews(best["enwiki"])
        if views is not None:
            out["pageviews_60d"] = views
    return out


# ── YouTube ────────────────────────────────────────────────────────────────

def youtube_stats(artist: str) -> dict:
    key = os.environ.get("YOUTUBE_API_KEY", "")
    if not key:
        return {"status": "unavailable", "reason": "no YOUTUBE_API_KEY"}
    hdr = {"x-goog-api-key": key}
    r = _get("https://www.googleapis.com/youtube/v3/search", headers=hdr, params={
        "part": "snippet", "type": "channel", "q": artist, "maxResults": 5,
    })
    if r is None or r.status_code != 200:
        return {"status": "unavailable", "reason": f"search HTTP {getattr(r, 'status_code', 'error')}"}
    ids = [i["id"]["channelId"] for i in r.json().get("items", [])
           if names_match(i["snippet"].get("channelTitle", ""), artist)]
    if not ids:
        return {"status": "none"}
    r = _get("https://www.googleapis.com/youtube/v3/channels", headers=hdr, params={
        "part": "statistics,snippet", "id": ",".join(ids),
    })
    if r is None or r.status_code != 200:
        return {"status": "unavailable", "reason": "channels lookup failed"}
    best = None
    for ch in r.json().get("items", []):
        st = ch.get("statistics", {})
        subs = 0 if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0))
        cand = {"channel_id": ch["id"], "title": ch["snippet"]["title"], "subscribers": subs,
                "views": int(st.get("viewCount", 0))}
        if not best or cand["subscribers"] > best["subscribers"]:
            best = cand
    return {"status": "ok", **best, "confidence": "medium"}


# ── Spotify ────────────────────────────────────────────────────────────────

def spotify_stats(artist: str) -> dict:
    from image_generator.artist_image_sources import _get_spotify_token
    token = _get_spotify_token()
    if not token:
        return {"status": "unavailable", "reason": "no Spotify credentials"}
    r = _get("https://api.spotify.com/v1/search", headers={"Authorization": f"Bearer {token}"},
             params={"q": artist, "type": "artist", "limit": 5})
    if r is None or r.status_code != 200:
        return {"status": "unavailable", "reason": f"search HTTP {getattr(r, 'status_code', 'error')}"}
    best = None
    for a in r.json().get("artists", {}).get("items", []):
        if norm(a["name"]) != norm(artist):
            continue
        followers = (a.get("followers") or {}).get("total", 0)
        if not best or followers > best["followers"]:
            best = {"id": a["id"], "name": a["name"], "followers": followers,
                    "popularity": a.get("popularity", 0)}
    if not best:
        return {"status": "none"}
    return {"status": "ok", **best, "confidence": "medium"}


# ── Instagram (from cache) ─────────────────────────────────────────────────

def instagram_stats(artist: str) -> dict:
    handle, followers, source = get_cached_instagram(artist)
    if handle is None and not source:
        return {"status": "unavailable", "reason": "not looked up yet"}
    if not handle:
        return {"status": "none"}
    if not followers:
        return {"status": "unavailable", "reason": "handle known, followers unknown", "handle": handle}
    conf = "high" if source in ("manual", "wikidata") else "medium"
    return {"status": "ok", "handle": handle, "followers": followers, "source": source,
            "confidence": conf}


# ── Combine ────────────────────────────────────────────────────────────────

PLATFORMS = {
    "instagram": (instagram_stats, lambda s: log_scale(s.get("followers", 0), "instagram")),
    "youtube": (youtube_stats, lambda s: log_scale(s.get("subscribers", 0), "youtube")),
    "spotify": (spotify_stats, lambda s: log_scale(s.get("followers", 0), "spotify")),
    "wikipedia": (wikipedia_stats, lambda s: max(0.15, log_scale(s.get("sitelinks", 0), "sitelinks"),
                                                 log_scale(s.get("pageviews_60d", 0), "wikipedia"))),
}


def artist_stats(artist: str, refresh: bool = False, role: str = "") -> dict:
    """Return {platform: stats} for an artist, using the cache when fresh.

    Platforms that were unavailable last time are retried, since a key may have been added.
    """
    cached = None if refresh else get_artist_stats(artist)
    stats = dict(cached or {})
    changed = False
    for name, (fn, _) in PLATFORMS.items():
        prev = stats.get(name)
        # Instagram comes from the handle cache (cheap, updated by ingest) — always re-read it.
        if name != "instagram" and prev and prev.get("status") != "unavailable":
            continue
        stats[name] = fn(artist, role) if name == "wikipedia" else fn(artist)
        changed = changed or stats[name] != prev
    # Re-check a cached Wikidata match against the current acceptance rule.
    wiki = stats.get("wikipedia") or {}
    if wiki.get("status") == "ok" and not accept_description(wiki.get("description", ""), artist, role):
        stats["wikipedia"] = {"status": "none", "reason": f"rejected match: {wiki.get('description', '')}"}
        changed = True
    if changed or cached is None:
        save_artist_stats(artist, stats)
    return stats


def reach(stats: dict) -> dict:
    """Collapse per-platform stats into a 0-1 reach score with an explanation.

    reach = strongest platform, discounted when it is the only evidence and its identity
    match is not high-confidence (e.g. an Instagram handle found via web search).
    """
    per = {}
    for name, (_, scorer) in PLATFORMS.items():
        s = stats.get(name) or {}
        if s.get("status") == "ok":
            per[name] = round(scorer(s), 3)
    if not per:
        return {"reach": 0.0, "platforms": {}, "evidence": "none",
                "available": [n for n, s in stats.items() if (s or {}).get("status") != "unavailable"]}
    top_name = max(per, key=per.get)
    top = per[top_name]
    corroborated = sum(1 for v in per.values() if v >= 0.15) >= 2
    high_conf = (stats[top_name].get("confidence") == "high")
    value = top if (corroborated or high_conf) else top * 0.6
    return {
        "reach": round(value, 3),
        "platforms": per,
        "evidence": "corroborated" if corroborated else ("single-high" if high_conf else "single-unverified"),
        "available": [n for n, s in stats.items() if (s or {}).get("status") != "unavailable"],
    }
