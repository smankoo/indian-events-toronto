import sqlite3
from datetime import datetime
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
            processed_at TEXT,
            PRIMARY KEY (source, source_id)
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


def save_event(event: Event, is_indian: bool, classification_reason: str = ""):
    conn = get_connection()
    conn.execute(
        """INSERT OR REPLACE INTO processed_events
           (source, source_id, title, date, time_str, venue, address, city, price,
            description, image_url, event_url, categories, languages, organizer,
            is_indian, classification_reason, processed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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


def mark_posted(source: str, source_id: str):
    conn = get_connection()
    conn.execute(
        "UPDATE processed_events SET posted = 1 WHERE source = ? AND source_id = ?",
        (source, source_id),
    )
    conn.commit()
    conn.close()


def get_posted_events() -> list[Event]:
    """Return Indian events that have been posted, ordered by date (upcoming first)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT source, source_id, title, date, time_str, venue, address, city,
                  price, description, image_url, event_url, categories, languages, organizer
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
        ))
    return events


def get_unposted_events() -> list[Event]:
    """Return Indian events that haven't been posted yet, ordered by date."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT source, source_id, title, date, time_str, venue, address, city,
                  price, description, image_url, event_url, categories, languages, organizer
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
        ))
    return events
