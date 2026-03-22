"""Reliable artist image sources, tried in order of trustworthiness.

Chain:
  1. Wikipedia  — direct article lookup (identity verified by Wikipedia editors)
  2. Wikidata   — P18 image property → Wikimedia Commons (same trust level)
  3. Spotify    — high-quality artist photos (needs SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET env vars)
  4. (caller falls back to DuckDuckGo if all return None)
"""

import io
import os
import time
import urllib.parse

import requests
from PIL import Image

HEADERS = {"User-Agent": "indian.events.toronto/1.0 (instagram: @indian.events.toronto)"}
MIN_W, MIN_H = 400, 400


def _download(url: str) -> Image.Image | None:
    try:
        r = requests.get(url, timeout=10, headers=HEADERS)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        if img.width >= MIN_W and img.height >= MIN_H:
            return img
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────
# 1. WIKIPEDIA
# ─────────────────────────────────────────────────────────────

def _wikipedia_article_extract(article_title: str) -> str:
    """Fetch the first paragraph of a Wikipedia article for profession checking."""
    url = (
        "https://en.wikipedia.org/w/api.php"
        f"?action=query&titles={urllib.parse.quote(article_title)}"
        "&prop=extracts&exintro=1&explaintext=1&format=json"
    )
    try:
        r = requests.get(url, timeout=10, headers=HEADERS)
        pages = r.json().get("query", {}).get("pages", {})
        for page in pages.values():
            return page.get("extract", "")
    except Exception:
        pass
    return ""


def _wikipedia_article_image(article_title: str) -> Image.Image | None:
    """Fetch the main image for a specific Wikipedia article title."""
    url = (
        "https://en.wikipedia.org/w/api.php"
        f"?action=query&titles={urllib.parse.quote(article_title)}"
        "&prop=pageimages&pithumbsize=1200&format=json"
    )
    try:
        r = requests.get(url, timeout=10, headers=HEADERS)
        data = r.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            thumb = page.get("thumbnail", {})
            img_url = thumb.get("source")
            original = page.get("original", {}).get("source")
            src = original or img_url
            if src:
                img = _download(src)
                if img:
                    return img
    except Exception:
        pass
    return None


TYPE_KEYWORDS = {
    "comedian": ["comedian", "stand-up", "standup", "comic", "comedy"],
    "musician": ["singer", "musician", "playback", "band", "vocalist", "composer"],
    "dj": ["dj", "disc jockey", "music producer", "electronic"],
    "other": [],
}


def fetch_wikipedia(artist_name: str, performer_type: str = "") -> Image.Image | None:
    """Find an artist's Wikipedia article by name and return their photo.

    Uses performer_type to disambiguate (e.g. 'Amit Tandon comedian' vs actor).
    """
    # Try type-specific search first, then fallback to plain name
    search_terms = []
    if performer_type and performer_type in TYPE_KEYWORDS:
        for kw in TYPE_KEYWORDS[performer_type][:2]:
            search_terms.append(f"{artist_name} {kw}")
    search_terms.append(artist_name)

    type_kws = TYPE_KEYWORDS.get(performer_type, [])

    for search_term in search_terms:
        url = (
            "https://en.wikipedia.org/w/api.php"
            f"?action=opensearch&search={urllib.parse.quote(search_term)}&limit=5&format=json"
        )
        try:
            r = requests.get(url, timeout=10, headers=HEADERS)
            results = r.json()
            titles = results[1] if len(results) > 1 else []
            descriptions = results[2] if len(results) > 2 else []

            for title, desc in zip(titles, descriptions):
                if "disambiguation" in title.lower():
                    continue
                name_words = artist_name.lower().split()
                if not all(w in title.lower() for w in name_words):
                    continue

                # If we have a performer type, reject articles about the WRONG profession
                # Use article extract if OpenSearch description is empty
                check_text = desc.lower()
                if type_kws and not check_text:
                    check_text = _wikipedia_article_extract(title).lower()[:500]

                if type_kws and check_text:
                    wrong_professions = {
                        "comedian": ["actor", "actress", "film actor", "television actor"],
                        "musician": ["actor", "actress", "comedian"],
                        "dj": ["actor", "actress", "comedian"],
                    }
                    wrong_kws = wrong_professions.get(performer_type, [])
                    has_right = any(k in check_text for k in type_kws)
                    has_wrong = any(k in check_text for k in wrong_kws)
                    if has_wrong and not has_right:
                        print(f"    Wikipedia: skipping '{title}' (wrong profession)")
                        continue

                print(f"    Wikipedia: trying article '{title}'")
                img = _wikipedia_article_image(title)
                if img:
                    print(f"    Wikipedia: found image {img.width}x{img.height}")
                    return img
        except Exception as e:
            print(f"    Wikipedia search failed: {e}")
    return None


# ─────────────────────────────────────────────────────────────
# 2. WIKIDATA
# ─────────────────────────────────────────────────────────────

def fetch_wikidata(artist_name: str, performer_type: str = "") -> Image.Image | None:
    """Search Wikidata for the artist and return their P18 image if available.

    Uses performer_type to prefer the right entity when names are ambiguous.
    """
    url = (
        "https://www.wikidata.org/w/api.php"
        f"?action=wbsearchentities&search={urllib.parse.quote(artist_name)}"
        "&language=en&limit=5&format=json"
    )
    try:
        r = requests.get(url, timeout=10, headers=HEADERS)
        results = r.json().get("search", [])

        type_kws = TYPE_KEYWORDS.get(performer_type, [])
        wrong_professions = {
            "comedian": ["actor", "actress", "film director"],
            "musician": ["actor", "actress", "comedian"],
            "dj": ["actor", "actress", "comedian"],
        }
        wrong_kws = wrong_professions.get(performer_type, [])

        # Sort: entities matching performer_type first
        def _score(entity):
            desc = entity.get("description", "").lower()
            if type_kws and any(k in desc for k in type_kws):
                return 0  # best match
            if wrong_kws and any(k in desc for k in wrong_kws):
                return 2  # wrong profession
            return 1  # neutral

        results.sort(key=_score)

        for entity in results:
            qid = entity.get("id")
            label = entity.get("label", "")
            description = entity.get("description", "").lower()

            if not qid:
                continue

            # Skip entities about the wrong profession
            if wrong_kws and any(k in description for k in wrong_kws):
                has_right = type_kws and any(k in description for k in type_kws)
                if not has_right:
                    print(f"    Wikidata: skipping {label} (wrong profession: {description[:60]})")
                    continue

            if not any(w in description for w in [
                "singer", "musician", "comedian", "actor", "actress",
                "performer", "artist", "composer", "rapper", "band",
                "indian", "bollywood", "playback", "stand-up", "standup",
            ]):
                if label.lower() != artist_name.lower():
                    continue

            # Step 2: Fetch P18 (image) claim
            entity_url = (
                f"https://www.wikidata.org/w/api.php"
                f"?action=wbgetentities&ids={qid}&props=claims&format=json"
            )
            er = requests.get(entity_url, timeout=10, headers=HEADERS)
            claims = er.json().get("entities", {}).get(qid, {}).get("claims", {})

            p18 = claims.get("P18", [])
            if not p18:
                continue

            filename = p18[0]["mainsnak"]["datavalue"]["value"]
            # Wikimedia Commons Special:FilePath redirects to the actual image
            commons_url = f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(filename)}"
            print(f"    Wikidata: found image for {label} ({qid}): {filename[:60]}")
            img = _download(commons_url)
            if img:
                print(f"    Wikidata: fetched {img.width}x{img.height}")
                return img

    except Exception as e:
        print(f"    Wikidata search failed: {e}")
    return None


# ─────────────────────────────────────────────────────────────
# 3. SPOTIFY  (optional — needs env vars)
# ─────────────────────────────────────────────────────────────

_spotify_token: str | None = None
_spotify_token_expiry: float = 0.0


def _get_spotify_token() -> str | None:
    global _spotify_token, _spotify_token_expiry
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        return None

    if _spotify_token and time.time() < _spotify_token_expiry - 60:
        return _spotify_token

    try:
        r = requests.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
        _spotify_token = data["access_token"]
        _spotify_token_expiry = time.time() + data.get("expires_in", 3600)
        return _spotify_token
    except Exception as e:
        print(f"    Spotify auth failed: {e}")
        return None


def fetch_spotify(artist_name: str) -> Image.Image | None:
    """Search Spotify for the artist and return their highest-res photo."""
    token = _get_spotify_token()
    if not token:
        return None

    try:
        r = requests.get(
            "https://api.spotify.com/v1/search",
            params={"q": artist_name, "type": "artist", "limit": 3},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        r.raise_for_status()
        artists = r.json().get("artists", {}).get("items", [])

        for artist in artists:
            name = artist.get("name", "")
            # Loose name match
            if artist_name.lower() not in name.lower() and name.lower() not in artist_name.lower():
                continue

            images = sorted(artist.get("images", []), key=lambda x: x.get("width", 0), reverse=True)
            for img_data in images:
                url = img_data.get("url")
                w = img_data.get("width", 0)
                h = img_data.get("height", 0)
                if w >= MIN_W and h >= MIN_H and url:
                    print(f"    Spotify: found artist '{name}' image {w}x{h}")
                    img = _download(url)
                    if img:
                        return img
    except Exception as e:
        print(f"    Spotify search failed: {e}")
    return None


# ─────────────────────────────────────────────────────────────
# 4. MUSICBRAINZ → SPOTIFY
# MusicBrainz identifies the correct artist (community-verified,
# country data), extracts their Spotify ID, then fetches the
# high-quality Spotify artist photo.
# ─────────────────────────────────────────────────────────────

def fetch_musicbrainz_spotify(artist_name: str) -> Image.Image | None:
    """Look up artist via MusicBrainz, get their Spotify ID, fetch photo."""
    if not (os.environ.get("SPOTIFY_CLIENT_ID") and os.environ.get("SPOTIFY_CLIENT_SECRET")):
        return None  # Spotify creds required

    # Step 1: MusicBrainz artist search
    url = (
        "https://musicbrainz.org/ws/2/artist"
        f"?query={urllib.parse.quote(artist_name)}&fmt=json"
    )
    try:
        r = requests.get(url, timeout=10, headers=HEADERS)
        artists = r.json().get("artists", [])

        for artist in artists:
            score = int(artist.get("score", 0))
            if score < 85:
                break  # results are score-sorted, no point continuing

            mbid = artist.get("id")
            if not mbid:
                continue

            # Step 2: Fetch URL relations to find Spotify link
            time.sleep(1.1)  # MusicBrainz rate limit: 1 req/sec
            rel_url = f"https://musicbrainz.org/ws/2/artist/{mbid}?inc=url-rels&fmt=json"
            rr = requests.get(rel_url, timeout=10, headers=HEADERS)
            relations = rr.json().get("relations", [])

            spotify_id = None
            for rel in relations:
                resource = rel.get("url", {}).get("resource", "")
                if "open.spotify.com/artist/" in resource:
                    spotify_id = resource.split("/artist/")[-1].split("?")[0]
                    break

            if not spotify_id:
                continue

            print(f"    MusicBrainz→Spotify: found Spotify ID {spotify_id} for '{artist.get('name')}'")

            # Step 3: Fetch Spotify artist image directly by ID
            token = _get_spotify_token()
            if not token:
                return None

            sr = requests.get(
                f"https://api.spotify.com/v1/artists/{spotify_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )
            sr.raise_for_status()
            images = sorted(sr.json().get("images", []),
                            key=lambda x: x.get("width", 0), reverse=True)
            for img_data in images:
                img_url = img_data.get("url")
                w, h = img_data.get("width", 0), img_data.get("height", 0)
                if w >= MIN_W and h >= MIN_H and img_url:
                    img = _download(img_url)
                    if img:
                        print(f"    MusicBrainz→Spotify: fetched {img.width}x{img.height}")
                        return img
    except Exception as e:
        print(f"    MusicBrainz→Spotify failed: {e}")
    return None


# ─────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────

def fetch_artist_image(artist_name: str) -> Image.Image | None:
    """Try all reliable sources in order. Returns the first good image found."""
    for source_fn, label in [
        (fetch_wikipedia,           "Wikipedia"),
        (fetch_wikidata,            "Wikidata"),
        (fetch_musicbrainz_spotify, "MusicBrainz→Spotify"),
        (fetch_spotify,             "Spotify direct"),
    ]:
        print(f"    Trying {label} for '{artist_name}'...")
        img = source_fn(artist_name)
        if img:
            return img
    return None
