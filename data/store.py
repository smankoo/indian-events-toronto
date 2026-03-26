import re
import sqlite3
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from models import Event

DB_PATH = Path(__file__).parent / "events.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS processed_events (
            source TEXT NOT NULL,
            source_id TEXT NOT NULL,
            title TEXT,
            date TEXT,
            time_str TEXT,
            venue TEXT,
            address TEXT,
            city TEXT,
            price TEXT,
            description TEXT,
            image_url TEXT,
            event_url TEXT,
            categories TEXT,
            languages TEXT,
            organizer TEXT,
            is_indian INTEGER,
            classification_reason TEXT,
            posted INTEGER DEFAULT 0,
            posted_image_url TEXT DEFAULT '',
            processed_at TEXT,
            PRIMARY KEY (source, source_id)
        )
    """)
    # Migrations: add columns if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(processed_events)").fetchall()]
    if "posted_image_url" not in cols:
        conn.execute("ALTER TABLE processed_events ADD COLUMN posted_image_url TEXT DEFAULT ''")
    if "story_posted_at" not in cols:
        conn.execute("ALTER TABLE processed_events ADD COLUMN story_posted_at TEXT DEFAULT ''")
    if "story_days_posted" not in cols:
        conn.execute("ALTER TABLE processed_events ADD COLUMN story_days_posted TEXT DEFAULT ''")
    if "image_urls" not in cols:
        conn.execute("ALTER TABLE processed_events ADD COLUMN image_urls TEXT DEFAULT ''")
    if "has_alt_text" not in cols:
        conn.execute("ALTER TABLE processed_events ADD COLUMN has_alt_text INTEGER DEFAULT 0")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS instagram_handles (
            artist_name TEXT PRIMARY KEY,
            performer_type TEXT,
            instagram_handle TEXT,
            source TEXT,
            followers_count INTEGER DEFAULT 0,
            looked_up_at TEXT
        )
    """)
    conn.commit()
    return conn


def is_new(event: Event) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT 1 FROM processed_events WHERE source = ? AND source_id = ?",
        (event.source, event.source_id),
    ).fetchone()
    conn.close()
    return row is None


def _normalize_title(title: str) -> str:
    """Normalize a title for fuzzy comparison — strip times, years, filler."""
    t = title.lower()
    t = re.sub(r'\(?\d{1,2}:\d{2}\s*(?:am|pm)\)?', '', t)
    t = re.sub(r'\b20\d{2}\b', '', t)
    for filler in ['live in toronto', 'live in brampton', 'live in mississauga',
                   'toronto', 'brampton', 'mississauga', 'live', 'in', 'on']:
        t = re.sub(rf'\b{filler}\b', '', t)
    t = re.sub(r'[^a-z0-9 ]', '', t)
    return ' '.join(t.split())


def find_similar_event(event: Event) -> dict | None:
    """Check if a similar event (same date, similar title) already exists in the DB.

    Returns a dict with 'source_id', 'posted', 'title' if found, else None.
    """
    conn = get_connection()
    date_str = event.date.strftime("%Y-%m-%d")
    rows = conn.execute(
        """SELECT source_id, title, posted FROM processed_events
           WHERE source = ? AND date LIKE ? || '%'""",
        (event.source, date_str),
    ).fetchall()
    conn.close()

    norm = _normalize_title(event.title)
    for source_id, title, posted in rows:
        if source_id == event.source_id:
            continue  # exact same event, not a "similar" match
        similarity = SequenceMatcher(None, norm, _normalize_title(title)).ratio()
        if similarity > 0.7:
            return {"source_id": source_id, "title": title, "posted": bool(posted)}
    return None


def save_event(event: Event, is_indian: bool, classification_reason: str = ""):
    conn = get_connection()
    image_urls = ",".join(getattr(event, "image_urls", []) or [])
    conn.execute(
        """INSERT INTO processed_events
           (source, source_id, title, date, time_str, venue, address, city, price,
            description, image_url, image_urls, event_url, categories, languages, organizer,
            is_indian, classification_reason, processed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(source, source_id) DO UPDATE SET
            title=excluded.title, date=excluded.date, time_str=excluded.time_str,
            venue=excluded.venue, address=excluded.address, city=excluded.city,
            price=excluded.price, description=excluded.description,
            image_url=excluded.image_url, image_urls=excluded.image_urls,
            event_url=excluded.event_url,
            categories=excluded.categories, languages=excluded.languages,
            organizer=excluded.organizer, is_indian=excluded.is_indian,
            classification_reason=excluded.classification_reason,
            processed_at=excluded.processed_at""",
        (
            event.source,
            event.source_id,
            event.title,
            event.date.isoformat(),
            event.time_str,
            event.venue,
            event.address,
            event.city,
            event.price,
            event.description,
            event.image_url,
            image_urls,
            event.event_url,
            ",".join(event.categories),
            ",".join(event.languages),
            event.organizer,
            1 if is_indian else 0,
            classification_reason,
            datetime.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()


def mark_posted(source: str, source_id: str, posted_image_url: str = ""):
    conn = get_connection()
    conn.execute(
        "UPDATE processed_events SET posted = 1, posted_image_url = ?, has_alt_text = 1 WHERE source = ? AND source_id = ?",
        (posted_image_url, source, source_id),
    )
    conn.commit()
    conn.close()


def get_posted_events() -> list[Event]:
    """Return Indian events that have been posted, ordered by date (upcoming first)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT source, source_id, title, date, time_str, venue, address, city,
                  price, description, image_url, event_url, categories, languages,
                  organizer, posted_image_url
           FROM processed_events
           WHERE is_indian = 1 AND posted = 1
           ORDER BY date ASC"""
    ).fetchall()
    conn.close()

    events = []
    for r in rows:
        events.append(Event(
            source=r[0], source_id=r[1], title=r[2],
            date=datetime.fromisoformat(r[3]), time_str=r[4],
            venue=r[5], address=r[6], city=r[7], price=r[8],
            description=r[9], image_url=r[10], event_url=r[11],
            categories=r[12].split(",") if r[12] else [],
            languages=r[13].split(",") if r[13] else [],
            organizer=r[14] or "",
            posted_image_url=r[15] or "",
        ))
    return events


def get_story_candidates(max_days: int = 4) -> list[tuple[Event, int]]:
    """Return posted events that are 1-N days away and haven't had a story for that day count.

    Returns list of (event, days_left) tuples, sorted by days_left ascending.
    """
    from datetime import date as date_type

    conn = get_connection()
    rows = conn.execute(
        """SELECT source, source_id, title, date, time_str, venue, address, city,
                  price, description, image_url, event_url, categories, languages,
                  organizer, posted_image_url, story_days_posted
           FROM processed_events
           WHERE is_indian = 1 AND posted = 1
           ORDER BY date ASC"""
    ).fetchall()
    conn.close()

    today = date_type.today()
    candidates = []
    for r in rows:
        event_date = datetime.fromisoformat(r[3]).date()
        days_left = (event_date - today).days
        if days_left < 1 or days_left > max_days:
            continue

        already_posted = set(r[16].split(",")) if r[16] else set()
        if str(days_left) in already_posted:
            continue

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
        candidates.append((event, days_left))

    candidates.sort(key=lambda x: x[1])
    return candidates


def mark_story_posted(source: str, source_id: str, days_left: int):
    """Record that a story was posted for a specific day count."""
    conn = get_connection()
    row = conn.execute(
        "SELECT story_days_posted FROM processed_events WHERE source = ? AND source_id = ?",
        (source, source_id),
    ).fetchone()
    existing = row[0] if row and row[0] else ""
    days_set = set(existing.split(",")) if existing else set()
    days_set.discard("")
    days_set.add(str(days_left))
    updated = ",".join(sorted(days_set, key=int, reverse=True))
    conn.execute(
        "UPDATE processed_events SET story_days_posted = ?, story_posted_at = ? WHERE source = ? AND source_id = ?",
        (updated, datetime.now().isoformat(), source, source_id),
    )
    conn.commit()
    conn.close()


def get_unposted_events() -> list[Event]:
    """Return Indian events that haven't been posted yet, ordered by date."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT source, source_id, title, date, time_str, venue, address, city,
                  price, description, image_url, event_url, categories, languages,
                  organizer, image_urls
           FROM processed_events
           WHERE is_indian = 1 AND posted = 0
           ORDER BY date ASC"""
    ).fetchall()
    conn.close()

    events = []
    for r in rows:
        events.append(Event(
            source=r[0], source_id=r[1], title=r[2],
            date=datetime.fromisoformat(r[3]), time_str=r[4],
            venue=r[5], address=r[6], city=r[7], price=r[8],
            description=r[9], image_url=r[10], event_url=r[11],
            categories=r[12].split(",") if r[12] else [],
            languages=r[13].split(",") if r[13] else [],
            organizer=r[14] or "",
            image_urls=r[15].split(",") if r[15] else [],
        ))
    return events


def get_cached_handle(artist_name: str) -> tuple[str | None, bool] | None:
    """Return (handle, is_fresh) from cache, or None if not cached.

    Fresh = found handle < 30 days old, or failed lookup < 7 days old.
    """
    from datetime import timedelta
    conn = get_connection()
    row = conn.execute(
        "SELECT instagram_handle, looked_up_at FROM instagram_handles WHERE artist_name = ?",
        (artist_name,),
    ).fetchone()
    conn.close()

    if not row:
        return None

    handle, looked_up_at = row[0], row[1]
    if not looked_up_at:
        return None

    age = datetime.now() - datetime.fromisoformat(looked_up_at)
    ttl = timedelta(days=30) if handle else timedelta(days=7)
    return handle, age < ttl


def save_handle_cache(artist_name: str, performer_type: str, handle: str | None,
                      source: str, followers_count: int):
    """Cache a handle lookup result."""
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO instagram_handles
           (artist_name, performer_type, instagram_handle, source, followers_count, looked_up_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (artist_name, performer_type, handle, source, followers_count, datetime.now().isoformat()),
    )
    conn.commit()
    conn.close()
