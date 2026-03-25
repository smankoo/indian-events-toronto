"""Score events into profile tiers (High / Medium / Low) with reasons.

Signals used:
  - Artist Instagram followers (cached from handle lookups)
  - Ticket price
  - Venue (known major venues in GTA)
  - Event type patterns in title
"""

import re
from dataclasses import dataclass, field

from models import Event

# ── Major GTA venues (capacity 1000+) ──
MAJOR_VENUES = {
    "scotiabank arena", "rogers centre", "budweiser stage", "coca-cola coliseum",
    "meridian hall", "roy thomson hall", "massey hall", "queen elizabeth theatre",
    "metro toronto convention centre", "john bassett theatre", "enercare centre",
    "sony centre", "princess of wales theatre", "royal alexandra theatre",
    "td music hall", "history", "danforth music hall", "rebel", "phoenix concert theatre",
    "harbourfront centre", "hamilton place theatre", "firstontario concert hall",
    "living arts centre", "rose theatre", "flato markham theatre",
    "mississauga celebration square", "brampton performing arts centre",
}

# ── Title patterns suggesting scale ──
TOUR_PATTERNS = re.compile(
    r"\b(tour|north americ|world tour|live in concert|concert)\b", re.IGNORECASE
)
PARTY_PATTERNS = re.compile(
    r"\b(night|party|mixer|singles|speed dating|after dark|moves & grooves|dance)\b",
    re.IGNORECASE,
)


@dataclass
class ProfileScore:
    tier: str  # "High", "Medium", "Low"
    score: int  # 0-100
    reasons: list[str] = field(default_factory=list)


def score_event(event: Event, artist_followers: dict[str, int] | None = None) -> ProfileScore:
    """Score an event's profile. artist_followers maps artist names to IG follower counts."""
    points = 0
    reasons = []
    artist_followers = artist_followers or {}

    # ── Artist followers (0-40 points) ──
    # Use total followers across all artists (multi-artist events get combined reach)
    total_followers = sum(artist_followers.values())

    if total_followers >= 500_000:
        points += 40
        reasons.append(f"Major artist(s) ({_fmt(total_followers)} total IG followers)")
    elif total_followers >= 100_000:
        points += 30
        reasons.append(f"Well-known artist(s) ({_fmt(total_followers)} total IG followers)")
    elif total_followers >= 30_000:
        points += 20
        reasons.append(f"Rising artist(s) ({_fmt(total_followers)} total IG followers)")
    elif total_followers >= 5_000:
        points += 10
        reasons.append(f"Emerging artist(s) ({_fmt(total_followers)} total IG followers)")
    elif total_followers > 0:
        points += 0
        reasons.append(f"Small following ({_fmt(total_followers)} total IG followers)")
    else:
        reasons.append("No artist follower data")

    # ── Ticket price (0-20 points) ──
    price_val = _parse_price(event.price)
    if price_val is not None:
        if price_val >= 100:
            points += 20
            reasons.append(f"Premium ticket price (CA${price_val})")
        elif price_val >= 50:
            points += 15
            reasons.append(f"Mid-range ticket price (CA${price_val})")
        elif price_val >= 25:
            points += 8
            reasons.append(f"Standard ticket price (CA${price_val})")
        else:
            points += 0
            reasons.append(f"Budget ticket price (CA${price_val})")
    else:
        reasons.append("No price info")

    # ── Venue (0-20 points) ──
    venue_lower = (event.venue or "").lower()
    venue_matched = False
    for v in MAJOR_VENUES:
        if v in venue_lower or venue_lower in v:
            points += 20
            reasons.append(f"Major venue ({event.venue})")
            venue_matched = True
            break
    if not venue_matched:
        if any(w in venue_lower for w in ["arena", "centre", "theater", "theatre", "hall", "stadium"]):
            points += 12
            reasons.append(f"Mid-size venue ({event.venue})")
        elif any(w in venue_lower for w in ["lounge", "bar", "pub", "restaurant", "grill"]):
            points += 0
            reasons.append(f"Small venue ({event.venue})")
        else:
            points += 5
            reasons.append(f"Unknown venue type ({event.venue})")

    # ── Event type from title (0-20 points) ──
    title = event.title or ""
    if TOUR_PATTERNS.search(title):
        points += 20
        reasons.append("Tour/concert format")
    elif PARTY_PATTERNS.search(title):
        points += 0
        reasons.append("Party/social event format")
    else:
        points += 10
        reasons.append("Standard event format")

    # ── Determine tier ──
    if points >= 55:
        tier = "High"
    elif points >= 25:
        tier = "Medium"
    else:
        tier = "Low"

    return ProfileScore(tier=tier, score=points, reasons=reasons)


def _fmt(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K"
    return str(n)


def _parse_price(price: str | None) -> float | None:
    if not price:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", price.replace(",", ""))
    return float(m.group(1)) if m else None
