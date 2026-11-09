"""Classify an event's performer type and artist names from its title (LLM).

Used as a fallback for events that don't have a profile yet (classifier/profile.py),
e.g. by Instagram handle enrichment.
"""

import os
import re

import requests

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
