"""Score events into profile tiers (High / Medium / Low) with reasons.

Signals used:
  - Artist Instagram followers (cached from handle lookups)
  - Ticket price
  - Venue (known major venues in GTA)
  - Event type patterns in title
"""

import math
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

    # ── Artist followers (0-40 points, log-proportional) ──
    # Use total followers across all artists (multi-artist events get combined reach)
    total_followers = sum(artist_followers.values())
    follower_max_pts = 40
    follower_floor = 1_000
    follower_ceil = 5_000_000

    if total_followers >= follower_ceil:
        f_pts = follower_max_pts
    elif total_followers > follower_floor:
        log_floor = math.log10(follower_floor)
        log_ceil = math.log10(follower_ceil)
        log_val = math.log10(total_followers)
        f_pts = round(((log_val - log_floor) / (log_ceil - log_floor)) * follower_max_pts)
    else:
        f_pts = 0
    points += f_pts

    if total_followers > 0:
        reasons.append(f"{_fmt(total_followers)} total IG followers → {f_pts}/{follower_max_pts} pts")
    else:
        reasons.append("No artist follower data")

    # ── Ticket price (0-20 points, log-proportional) ──
    price_max_pts = 20
    price_floor = 10
    price_ceil = 200
    price_val = _parse_price(event.price)
    if price_val is not None and price_val > price_floor:
        if price_val >= price_ceil:
            p_pts = price_max_pts
        else:
            log_floor = math.log10(price_floor)
            log_ceil = math.log10(price_ceil)
            log_val = math.log10(price_val)
            p_pts = round(((log_val - log_floor) / (log_ceil - log_floor)) * price_max_pts)
        points += p_pts
        reasons.append(f"CA${price_val:.0f} ticket → {p_pts}/{price_max_pts} pts")
    elif price_val is not None:
        reasons.append(f"CA${price_val:.0f} ticket → 0/{price_max_pts} pts")
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

    # ── Event type (0-20 points): performance vs social ──
    # If we identified artists, it's a performance; otherwise social/party
    format_max_pts = 20
    if total_followers > 0:
        points += format_max_pts
        reasons.append(f"Performance (artists identified) → {format_max_pts}/{format_max_pts} pts")
    else:
        reasons.append(f"Social/party (no artists) → 0/{format_max_pts} pts")

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
