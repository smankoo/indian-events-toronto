"""Score events into tiers that decide how each event is published.

  headliner — own feed post with an AI-integrated artist poster + countdown stories
  notable   — own feed post with a typographic card
  listing   — weekly roundup + link-in-bio only

Score (0-100) = artist reach (45) + LLM prominence (25) + venue size (15) + ticket price (15).

  reach       strongest headliner's cross-platform popularity (scoring/popularity.py)
  prominence  the profile LLM's 1-5 judgment of how big a draw the event is (classifier/profile.py)
  venue       known large GTA venues > halls/theatres/centres > bars/lounges
  price       log scale, $10 -> 0, $100+ -> full marks
"""

import math
import re

from models import Event

WEIGHTS = {"reach": 45, "prominence": 25, "venue": 15, "price": 15}
TIER_THRESHOLDS = {"headliner": 55, "notable": 30}

# Venues that hold 1,000+ people, including the convention centres and banquet complexes
# the Indian events scene uses for its biggest nights.
MAJOR_VENUES = {
    "scotiabank arena", "rogers centre", "budweiser stage", "coca-cola coliseum",
    "meridian hall", "roy thomson hall", "massey hall", "queen elizabeth theatre",
    "metro toronto convention centre", "john bassett theatre", "enercare centre",
    "sony centre", "princess of wales theatre", "royal alexandra theatre",
    "td music hall", "history", "danforth music hall", "rebel", "phoenix concert theatre",
    "harbourfront centre", "hamilton place theatre", "firstontario concert hall",
    "living arts centre", "rose theatre", "flato markham theatre",
    "mississauga celebration square", "celebration square", "brampton performing arts centre",
    "nathan phillips square", "international centre", "pearson convention centre",
    "toronto congress centre", "mississauga convention centre", "paradise banquet",
    "chinguacousy park", "ontario place", "exhibition place",
}
MID_WORDS = ("arena", "centre", "center", "theater", "theatre", "hall", "stadium",
             "auditorium", "square", "park", "banquet", "convention", "school")
SMALL_WORDS = ("lounge", "bar", "pub", "restaurant", "grill", "cafe", "café", "club",
               "rooftop", "studio", "kitchen", "chai", "brewery", "meeting place")


def venue_class(venue: str) -> tuple[str, float]:
    v = (venue or "").lower()
    if not v or "announced" in v:
        return "unknown", 0.25
    for name in MAJOR_VENUES:
        if name in v:
            return "major", 1.0
    if any(w in v for w in SMALL_WORDS):
        return "small", 0.0
    if any(w in v for w in MID_WORDS):
        return "mid", 0.5
    return "unknown", 0.25


def parse_price(price: str | None) -> float | None:
    if not price:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", price.replace(",", ""))
    return float(m.group(1)) if m else None


def price_factor(price: float | None) -> float:
    if not price or price <= 10:
        return 0.0
    return min(1.0, math.log10(price / 10))


def tier_for(score: int) -> str:
    if score >= TIER_THRESHOLDS["headliner"]:
        return "headliner"
    if score >= TIER_THRESHOLDS["notable"]:
        return "notable"
    return "listing"


def score_event(event: Event, refresh_stats: bool = False) -> tuple[str, int, dict]:
    """Return (tier, score, breakdown). Requires event.profile (classifier/profile.py)."""
    from scoring.popularity import artist_stats, reach

    profile = event.profile or {}
    artists = []
    for h in (profile.get("headliners") or [])[:4]:
        stats = artist_stats(h["name"], refresh=refresh_stats)
        artists.append({"name": h["name"], **reach(stats)})
    top = max(artists, key=lambda a: a["reach"], default=None)
    reach_v = top["reach"] if top else 0.0

    prominence = int(profile.get("prominence") or 2)
    prom_v = (prominence - 1) / 4
    vclass, venue_v = venue_class(event.venue)
    price = parse_price(event.price)
    price_v = price_factor(price)

    parts = {
        "reach": round(WEIGHTS["reach"] * reach_v, 1),
        "prominence": round(WEIGHTS["prominence"] * prom_v, 1),
        "venue": round(WEIGHTS["venue"] * venue_v, 1),
        "price": round(WEIGHTS["price"] * price_v, 1),
    }
    score = round(sum(parts.values()))
    tier = tier_for(score)
    breakdown = {
        "points": parts,
        "artists": artists,
        "prominence": prominence,
        "prominence_reason": profile.get("prominence_reason", ""),
        "venue_class": vclass,
        "price": price,
    }
    return tier, score, breakdown
