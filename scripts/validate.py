#!/usr/bin/env python3
"""Fast offline validation: stubs network/API calls, then runs the full dry-run pipeline.

Used as a pre-push hook to catch broken imports, refactoring errors, and
code-path regressions before they reach CI (which is effectively prod).

Runs in ~2 seconds with no API keys or network required.
"""

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

# Set dummy env vars so module-level lookups don't crash
for key in [
    "OPENROUTER_API_KEY", "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID",
    "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET",
    "FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_ACCESS_TOKEN",
]:
    os.environ.setdefault(key, "stub-for-validation")

# --- Build fake test events ---
from models import Event

FAKE_EVENTS = [
    Event(
        source="sulekha", source_id="validate-001",
        title="Bollywood Night - Live DJ",
        date=datetime.now() + timedelta(days=7),
        time_str="8:00 PM",
        venue="Test Venue", address="123 King St W, Toronto, ON",
        city="Toronto", price="CA$20",
        description="A fun Bollywood dance night in downtown Toronto.",
        image_url="https://example.com/fake.jpg",
        event_url="https://example.com/event",
        categories=["Music"], languages=["Hindi"], organizer="Test Org",
    ),
    Event(
        source="sulekha", source_id="validate-002",
        title="Arijit Singh Live in Concert - Toronto",
        date=datetime.now() + timedelta(days=14),
        time_str="7:00 PM",
        venue="Scotiabank Arena", address="40 Bay St, Toronto, ON",
        city="Toronto", price="CA$150",
        description="Arijit Singh performing his greatest hits live.",
        image_url="https://example.com/fake2.jpg",
        event_url="https://example.com/event2",
        categories=["Concert"], languages=["Hindi"], organizer="Live Nation",
    ),
]


def fake_scrape():
    return FAKE_EVENTS


def fake_classify(title, description, categories=None, languages=None, organizer=""):
    return True, "Validation stub: auto-classified as Indian", title


_cleanup_paths = []


def fake_create_post_image(event, style="A"):
    """Create a tiny placeholder PNG instead of using Playwright."""
    from PIL import Image
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    date_str = event.date.strftime("%Y%m%d")
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in event.title)[:50].strip().replace(" ", "_")
    path = output / f"{date_str}_{safe_title}.png"
    Image.new("RGB", (1080, 1080), color=(30, 30, 30)).save(path)
    _cleanup_paths.append(path)
    return path


def fake_create_story_image(event, days_left, style="C"):
    from PIL import Image
    output = ROOT / "output"
    output.mkdir(exist_ok=True)
    path = output / f"story_validate_{days_left}d.png"
    Image.new("RGB", (1080, 1920), color=(30, 30, 30)).save(path)
    return path


def fake_classify_performer(title, description=""):
    return {"type": "musician", "artist_name": "Test Artist", "artist_names": ["Test Artist"]}


def fake_lookup_handle(artist_name, performer_type=""):
    return None


def fake_is_new(event):
    """Treat validation events as new."""
    return event.source_id.startswith("validate-")


def main():
    print("=== Pipeline validation (offline, stubbed) ===\n")

    # Pre-import submodules so patch() can resolve dotted paths
    import scraper.sulekha  # noqa: F401
    import classifier.indian_classifier  # noqa: F401
    import image_generator.create_post  # noqa: F401
    import image_generator.create_story  # noqa: F401
    import image_generator.image_search  # noqa: F401
    import publisher.instagram_handle  # noqa: F401
    import publisher.linkinbio  # noqa: F401
    import data.store  # noqa: F401

    patches = [
        patch("scraper.sulekha.scrape_events", fake_scrape),
        patch("classifier.indian_classifier.classify_event", fake_classify),
        patch("image_generator.create_post.create_post_image", fake_create_post_image),
        patch("image_generator.create_story.create_story_image", fake_create_story_image),
        patch("image_generator.image_search.classify_event", fake_classify_performer),
        patch("publisher.instagram_handle.lookup_instagram_handle", fake_lookup_handle),
        patch("data.store.is_new", fake_is_new),
        patch("data.store.save_event", MagicMock()),
        patch("data.store.find_similar_event", lambda e: None),
        patch("data.store.get_unposted_events", lambda: FAKE_EVENTS),
        patch("data.store.mark_posted", MagicMock()),
        patch("data.store.mark_story_posted", MagicMock()),
        patch("data.store.get_story_candidates", lambda max_days=5: [(FAKE_EVENTS[0], 3)]),
        patch("publisher.linkinbio.generate_linkinbio", MagicMock()),
    ]

    for p in patches:
        p.start()

    try:
        # Import main AFTER patches are applied
        from main import ingest, post
        ingest(classify_limit=10)
        post(post_limit=2, dry_run=True, stories=True)
        print("\n=== Validation PASSED ===")
    except Exception as e:
        print(f"\n=== Validation FAILED: {e} ===")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        for p in patches:
            p.stop()
        # Clean up validation images
        for f in _cleanup_paths:
            f.unlink(missing_ok=True)
        for f in (ROOT / "output").glob("*validate*"):
            f.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
