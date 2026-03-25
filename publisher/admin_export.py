"""Export event data with raw signals to JSON for the admin dashboard.

Scoring is done client-side in the admin page so the user can
tweak weights and thresholds interactively.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from data.store import get_connection
from publisher.event_profile import MAJOR_VENUES, TOUR_PATTERNS, PARTY_PATTERNS
from models import Event

ADMIN_DIR = Path(__file__).parent.parent / "docs" / "admin"


def _parse_price(price: str | None) -> float | None:
    if not price:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", price.replace(",", ""))
    return float(m.group(1)) if m else None


def _classify_venue(venue: str) -> str:
    """Classify venue into major / mid / small / unknown."""
    v = venue.lower()
    for name in MAJOR_VENUES:
        if name in v or v in name:
            return "major"
    if any(w in v for w in ["arena", "centre", "center", "theater", "theatre", "hall", "stadium"]):
        return "mid"
    if any(w in v for w in ["lounge", "bar", "pub", "restaurant", "grill"]):
        return "small"
    return "unknown"


def _classify_format(title: str) -> str:
    """Classify event format from title."""
    if TOUR_PATTERNS.search(title):
        return "tour"
    if PARTY_PATTERNS.search(title):
        return "party"
    return "standard"


def export_admin_json():
    """Export all future Indian events with raw signals to admin/events.json."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT source, source_id, title, date, time_str, venue, address, city,
                  price, description, image_url, event_url, categories, languages,
                  organizer, posted_image_url, posted, story_days_posted
           FROM processed_events
           WHERE is_indian = 1 AND date >= date('now')
           ORDER BY date ASC"""
    ).fetchall()

    # Load cached follower counts
    handle_rows = conn.execute(
        "SELECT artist_name, instagram_handle, followers_count FROM instagram_handles"
    ).fetchall()
    conn.close()

    follower_cache = {}
    handle_cache = {}
    for name, handle, followers in handle_rows:
        follower_cache[name.lower()] = followers
        handle_cache[name.lower()] = handle

    events_out = []
    for r in rows:
        title = r[2]
        venue = r[5] or ""
        price = r[8]

        # Match cached artist names against title
        artists = []
        title_lower = title.lower()
        for name in follower_cache:
            if name in title_lower:
                artists.append(name.title())
        seen = set()
        artists = [a for a in artists if not (a.lower() in seen or seen.add(a.lower()))]

        artist_data = []
        max_followers = 0
        total_followers = 0
        for a in artists:
            f = follower_cache.get(a.lower(), 0)
            h = handle_cache.get(a.lower())
            artist_data.append({"name": a, "handle": h, "followers": f})
            total_followers += f
            if f > max_followers:
                max_followers = f

        parsed_price = _parse_price(price)
        venue_class = _classify_venue(venue)
        event_format = _classify_format(title)

        events_out.append({
            "title": title,
            "date": r[3],
            "time": r[4] or "",
            "venue": venue,
            "city": r[7] or "",
            "price": price or "",
            "price_val": parsed_price,
            "event_url": r[11] or "",
            "posted": bool(r[16]),
            "posted_image_url": r[15] or "",
            "story_days_posted": r[17] or "",
            "artists": artist_data,
            "signals": {
                "max_followers": max_followers,
                "total_followers": total_followers,
                "venue_class": venue_class,
                "event_format": event_format,
            },
        })

    ADMIN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ADMIN_DIR / "events.json"
    out_path.write_text(json.dumps(events_out, indent=2, default=str))
    print(f"  Admin export: {len(events_out)} events -> {out_path}")
