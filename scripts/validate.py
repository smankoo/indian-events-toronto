#!/usr/bin/env python3
"""Fast offline validation: stubs network/API calls, then runs the whole pipeline in dry-run
mode against a throwaway database:

  ingest (scrape → classify → profile → enrich → score) → post --dry-run → roundup --dry-run

The real SQL, scoring maths and Pillow renderers run; only scraping, LLM/image-model calls,
platform lookups and publishing are stubbed. Used as a pre-push hook to catch broken imports
and code-path regressions before they reach CI (which is effectively prod).
"""

import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

for key in [
    "OPENROUTER_API_KEY", "INSTAGRAM_ACCESS_TOKEN", "INSTAGRAM_USER_ID",
    "SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET",
    "FACEBOOK_PAGE_ID", "FACEBOOK_PAGE_ACCESS_TOKEN",
]:
    os.environ.setdefault(key, "stub-for-validation")

from PIL import Image
from models import Event


def _next_weekend_day(offset: int) -> datetime:
    """A date in the upcoming weekend (same rule as main.weekend_window — main must not be
    imported before the patches are applied, or it binds the real functions)."""
    today = datetime.now().date()
    wd = today.weekday()
    friday = today + timedelta(days=4 - wd) if wd <= 4 else today - timedelta(days=wd - 4)
    d = datetime.combine(friday, datetime.min.time()) + timedelta(days=offset)
    return max(d, datetime.now() + timedelta(hours=2)).replace(hour=20, minute=0)


def fake_events() -> list[Event]:
    common = dict(source="sulekha", address="Toronto, ON", city="Toronto",
                  categories=["Music"], languages=["Hindi"])
    return [
        Event(source_id="validate-001", title="Bollywood Night - Live DJ",
              date=_next_weekend_day(0), time_str="10:00 PM", venue="Test Lounge",
              price="CA$20", description="A Bollywood dance night.", organizer="Test Org",
              image_url="https://example.invalid/a.jpg", event_url="https://example.invalid/a",
              **common),
        Event(source_id="validate-002", title="Arijit Singh Live in Concert - Toronto",
              date=_next_weekend_day(1), time_str="7:00 PM", venue="Scotiabank Arena",
              price="CA$150", description="Arijit Singh performing his greatest hits live.",
              organizer="Live Nation", image_url="https://example.invalid/b.jpg",
              event_url="https://example.invalid/b", **common),
        Event(source_id="validate-003", title="Desi Comedy Night",
              date=_next_weekend_day(1), time_str="8:00 PM", venue="Comedy Hall Theatre",
              price="CA$35", description="Stand-up comedy with Test Comic.",
              organizer="Test Org", image_url="https://example.invalid/c.jpg",
              event_url="https://example.invalid/c", **common),
    ]


FAKE_PROFILES = {
    "validate-001": dict(headliners=[], display_name="Bollywood Night", subtitle="Live DJ",
                         category="party", series="Bollywood Night", prominence=2),
    "validate-002": dict(headliners=[{"name": "Arijit Singh", "role": "singer", "pictured_in_image": 0}],
                         display_name="Arijit Singh", subtitle="Live in Concert",
                         category="concert", series=None, prominence=5),
    "validate-003": dict(headliners=[{"name": "Test Comic", "role": "comedian", "pictured_in_image": None}],
                         display_name="Test Comic", subtitle="Desi Comedy Night",
                         category="comedy", series=None, prominence=3),
}

FAKE_STATS = {
    "Arijit Singh": {"instagram": {"status": "ok", "followers": 40_000_000, "confidence": "high"},
                     "wikipedia": {"status": "ok", "pageviews_60d": 400_000, "confidence": "high"}},
    "Test Comic": {"instagram": {"status": "ok", "followers": 30_000, "confidence": "medium"}},
}


def fake_profile(event):
    p = dict(FAKE_PROFILES[event.source_id])
    p.setdefault("prominence_reason", "validation stub")
    return p


def fake_plate(event):
    return Image.new("RGB", (1080, 1350), (90, 40, 60))


def main():
    print("=== Pipeline validation (offline, stubbed) ===\n")
    tmp = Path(tempfile.mkdtemp(prefix="iet-validate-"))
    tmp_out = tmp / "output"

    import scraper.sulekha, classifier.indian_classifier, classifier.profile  # noqa: E401,F401
    import image_generator.hero_plate, image_generator.poster, image_generator.create_story  # noqa: E401,F401
    import publisher.instagram_handle, publisher.venue_handle, publisher.linkinbio  # noqa: E401,F401
    import publisher.admin_export, scoring.popularity, data.store  # noqa: E401,F401

    events = fake_events()
    patches = [
        patch("data.store.DB_PATH", tmp / "events.db"),
        patch("image_generator.poster.OUTPUT_DIR", tmp_out),
        patch("scraper.sulekha.scrape_events", lambda: events),
        patch("classifier.indian_classifier.classify_event",
              lambda title, description, categories=None, languages=None, organizer="":
              (True, "Validation stub", title)),
        patch("classifier.profile.profile_event", fake_profile),
        patch("scoring.popularity.artist_stats", lambda name, refresh=False: FAKE_STATS.get(name, {})),
        patch("image_generator.hero_plate.make_hero_plate", fake_plate),
        patch("image_generator.hero_plate._cache_path", lambda e: tmp / "no-plate.jpg"),
        patch("image_generator.poster._thumb_source", lambda e: None),
        patch("image_generator.poster._photo_for_cover",
              lambda e: fake_plate(e) if e.tier == "headliner" else None),
        patch("publisher.instagram_handle.lookup_instagram_handle", lambda name, t="": None),
        patch("publisher.venue_handle.lookup_venue_handle", lambda venue, city="": None),
        patch("publisher.linkinbio.generate_linkinbio", MagicMock()),
        patch("publisher.admin_export.export_admin_json", MagicMock()),
    ]
    for p in patches:
        p.start()

    try:
        from main import ingest, post, roundup
        from data.store import query_events
        ingest(classify_limit=10)

        tiers = {e.source_id: e.tier for e in query_events("1")}
        print(f"\nTiers: {tiers}")
        assert tiers["validate-002"] == "headliner", "Arijit should be a headliner"
        assert tiers["validate-001"] == "listing", "a generic club night should be listing-tier"

        post(post_limit=3, dry_run=True, stories=True)
        rendered = sorted(p.name for p in tmp_out.glob("*.png"))
        assert any("validate-002_headliner" in n for n in rendered), f"no headliner poster: {rendered}"
        assert not any("validate-001" in n for n in rendered), "listing-tier event must not get a post"

        roundup(dry_run=True)
        assert any(n.startswith("roundup_") for n in (p.name for p in tmp_out.glob("*.png"))), \
            "roundup slides not rendered"
        print("\n=== Validation PASSED ===")
    except Exception as e:
        print(f"\n=== Validation FAILED: {e} ===")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        for p in patches:
            p.stop()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
