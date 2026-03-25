"""Export event data with profile scores to JSON for the admin dashboard."""

import json
from datetime import datetime
from pathlib import Path

from data.store import get_connection
from publisher.event_profile import score_event
from models import Event

ADMIN_DIR = Path(__file__).parent.parent / "docs" / "admin"


def export_admin_json():
    """Export all future Indian events with profile scoring to admin/events.json."""
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
        event = Event(
            source=r[0], source_id=r[1], title=r[2],
            date=datetime.fromisoformat(r[3]), time_str=r[4],
            venue=r[5], address=r[6], city=r[7], price=r[8],
            description=r[9], image_url=r[10], event_url=r[11],
            categories=r[12].split(",") if r[12] else [],
            languages=r[13].split(",") if r[13] else [],
            organizer=r[14] or "",
            posted_image_url=r[15] or "",
        )

        # Find artists for this event — match cached handle names against the title.
        # On CI the LLM classification is more accurate, but this works offline too.
        artists = []
        title_lower = event.title.lower()
        for name in follower_cache:
            if name in title_lower:
                artists.append(name.title())
        # Deduplicate
        seen = set()
        artists = [a for a in artists if not (a.lower() in seen or seen.add(a.lower()))]

        artist_followers = {}
        artist_handles = {}
        for a in artists:
            f = follower_cache.get(a.lower(), 0)
            h = handle_cache.get(a.lower())
            if f > 0:
                artist_followers[a] = f
            if h:
                artist_handles[a] = h

        profile = score_event(event, artist_followers)

        events_out.append({
            "source": r[0],
            "source_id": r[1],
            "title": event.title,
            "date": r[3],
            "time": event.time_str or "",
            "venue": event.venue,
            "city": event.city or "",
            "price": event.price or "",
            "event_url": event.event_url or "",
            "posted": bool(r[16]),
            "posted_image_url": r[15] or "",
            "story_days_posted": r[17] or "",
            "artists": [
                {
                    "name": a,
                    "handle": artist_handles.get(a),
                    "followers": artist_followers.get(a, 0),
                }
                for a in artists
            ],
            "profile": {
                "tier": profile.tier,
                "score": profile.score,
                "reasons": profile.reasons,
            },
        })

    ADMIN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ADMIN_DIR / "events.json"
    out_path.write_text(json.dumps(events_out, indent=2, default=str))
    print(f"  Admin export: {len(events_out)} events -> {out_path}")
