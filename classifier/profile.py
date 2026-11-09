"""Extract a structured profile for an event: who's headlining, what kind of event it is,
whether it belongs to a recurring series, and how big the LLM thinks it is.

The flyer images are sent along with the text, because the headliner is often only on the
flyer (e.g. "Diwali Festival Of Lights" is really a Malaika Arora appearance).

The profile drives scoring (scoring/), poster design (category -> palette, display_name),
and AI hero images (which flyer image the headliner is pictured in).
"""

import base64
import io
import json
import os
import re

import requests
from PIL import Image

from models import Event

MODEL = os.environ.get("PROFILE_MODEL", "google/gemini-3.8-flash")

CATEGORIES = (
    "garba",      # garba, dandiya, raas, Navratri nights
    "comedy",     # stand-up, comedy shows
    "concert",    # Bollywood/Punjabi/indie music concerts and singers
    "classical",  # Hindustani/Carnatic classical, classical dance recitals
    "qawwali",    # qawwali, sufi, ghazal, mehfil
    "festival",   # Diwali/Holi/melas, multi-act cultural festivals, fairs
    "party",      # Bollywood/desi club nights, DJ parties, boat parties
    "theatre",    # plays, poetry, storytelling, spoken word, film screenings
    "community",  # workshops, singles/networking mixers, fashion, talks, religious gatherings
)

PROMPT = """You are profiling an event for @indian.events.toronto, an Instagram account that curates Indian events in the Toronto area.

Event title: {title}
Organizer: {organizer}
Venue: {venue}, {city}
Price: {price}
Description:
{description}

{image_note}

Return ONE JSON object with these fields:

"headliners": the people or acts the event is built around, in billing order. Read the flyer images carefully:
  headliners often appear only on the flyer (a celebrity guest at a festival, the singer at a garba night).
  Each item: {{"name": "<clean full name as commonly written>", "role": "<singer|band|comedian|dj|actor|dancer|poet|musician|speaker|host|other>",
  "pictured_in_image": <index of the flyer image where this person's photo appears, or null if not pictured>}}.
  Exclude organizers, sponsors, venues and generic descriptions ("DJs", "live band"). Empty list if nobody is billed.

"display_name": the short text for the poster headline (max 28 characters). If there are headliners,
  use the main headliner's name (or "A & B" for a true co-billing). Otherwise a cleaned-up event name
  without years, cities or venue ("Bombay Nights", "Diwali Dhamaka").

"subtitle": a short line under the headline (max 34 characters) that says what the event is,
  e.g. "Dandiya Dhoom 2026", "Live in Toronto", "Diwali Festival of Lights", "Bollywood & Indo House".
  Do not repeat the display_name. No dates, prices or venue.

"category": exactly one of {categories}.

"series": the name of the recurring brand or festival series this is part of, if any
  (e.g. "Navrang Navratri Festival Canada", "Bombay Nights", "Velvet Vibe"), else null.
  A one-off show by a touring artist is not a series.

"prominence": integer 1-5, how big a draw this is for the Indian community in the GTA:
  5 = household-name star (Bollywood celebrity, top playback singer, the biggest comedians) or a landmark event
  4 = well-known touring artist with a large national following, or a major annual festival
  3 = established artist with a solid following, or a large well-known recurring event
  2 = local or emerging act, regular club night, mid-size community event
  1 = small meetup, workshop, or niche community gathering
"prominence_reason": one short sentence.

Respond with the JSON object only."""


def _image_b64(url: str) -> str | None:
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"    Profile: could not load flyer {url[:60]}: {e}")
        return None


def flyer_urls(event: Event) -> list[str]:
    urls = [u for u in (event.image_urls or []) if u]
    if not urls and event.image_url:
        urls = [event.image_url]
    return urls[:2]


def _clean(profile: dict, event: Event) -> dict:
    heads = []
    for h in profile.get("headliners") or []:
        if isinstance(h, str):
            h = {"name": h}
        name = re.sub(r"\s+", " ", str(h.get("name", ""))).strip()
        if not name:
            continue
        pic = h.get("pictured_in_image")
        heads.append({
            "name": name,
            "role": str(h.get("role") or "other").lower(),
            "pictured_in_image": pic if isinstance(pic, int) else None,
        })
    category = str(profile.get("category") or "").lower()
    if category not in CATEGORIES:
        category = "community"
    try:
        prominence = max(1, min(5, int(profile.get("prominence") or 2)))
    except (TypeError, ValueError):
        prominence = 2
    display = str(profile.get("display_name") or "").strip() or (heads[0]["name"] if heads else event.title)
    series = profile.get("series")
    return {
        "headliners": heads,
        "display_name": display[:40],
        "subtitle": str(profile.get("subtitle") or "").strip()[:48],
        "category": category,
        "series": str(series).strip() if series else None,
        "prominence": prominence,
        "prominence_reason": str(profile.get("prominence_reason") or "").strip(),
        "model": MODEL,
    }


def profile_event(event: Event) -> dict | None:
    """Call the LLM and return a cleaned profile dict, or None on failure."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("    Profile: no OPENROUTER_API_KEY, skipping")
        return None

    images = [b for b in (_image_b64(u) for u in flyer_urls(event)) if b]
    image_note = (
        f"{len(images)} flyer image(s) are attached, indexed from 0 in the order given."
        if images else "No flyer images are available."
    )
    prompt = PROMPT.format(
        title=event.title, organizer=event.organizer or "unknown",
        venue=event.venue or "unknown", city=event.city or "",
        price=event.price or "unknown",
        description=(event.description or "")[:2500],
        image_note=image_note, categories=", ".join(CATEGORIES),
    )
    content = [{"type": "image_url", "image_url": {"url": b}} for b in images]
    content.append({"type": "text", "text": prompt})

    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": content}],
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
            },
            timeout=90,
        )
        r.raise_for_status()
        raw = r.json()["choices"][0]["message"]["content"]
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip()).strip()
        data = json.loads(raw)
        if isinstance(data, list):
            data = data[0]
        return _clean(data, event)
    except Exception as e:
        print(f"    Profile failed for {event.title[:50]!r}: {e}")
        return None
