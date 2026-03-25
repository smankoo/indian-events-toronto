#!/usr/bin/env python3
"""Pipeline with two independent stages:
  --ingest: Fetch events -> Filter -> Classify -> Save to DB
  --post:   Generate images -> Publish to IG + FB + link-in-bio
"""

import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from scraper.sulekha import scrape_events
from data.store import is_new, find_similar_event, save_event, mark_posted, get_unposted_events, get_story_candidates, mark_story_posted, _normalize_title
from classifier.indian_classifier import classify_event

from difflib import SequenceMatcher


def dedup_events(events: list) -> list:
    """Remove near-duplicate events (same date + similar title).

    Keeps the first occurrence. Events on different dates are never deduped.
    """
    kept = []
    for event in events:
        dominated = False
        norm = _normalize_title(event.title)
        for prev in kept:
            if event.date.date() != prev.date.date():
                continue
            prev_norm = _normalize_title(prev.title)
            similarity = SequenceMatcher(None, norm, prev_norm).ratio()
            if similarity > 0.7:
                print(f"  Dedup: skipping \"{event.title[:50]}\" (similar to \"{prev.title[:50]}\")")
                dominated = True
                break
        if not dominated:
            kept.append(event)
    return kept


# Toronto / GTA cities — events outside this area are skipped
GTA_CITIES = {
    "toronto", "mississauga", "brampton", "markham", "vaughan",
    "richmond hill", "scarborough", "etobicoke", "north york",
    "oakville", "burlington", "hamilton", "ajax", "pickering",
    "oshawa", "whitby", "milton", "newmarket", "aurora",
    "stouffville", "caledon", "halton hills", "guelph",
    "kitchener", "waterloo", "cambridge", "barrie",
}

GTA_KEYWORDS = {"toronto", "gta", "mississauga", "brampton", "markham", "vaughan", "scarborough"}


def is_gta_event(event) -> bool:
    """Check if an event is in the Toronto / GTA area."""
    searchable = " ".join([
        event.city, event.address, event.venue, event.title,
    ]).lower()
    if any(city in searchable for city in GTA_KEYWORDS):
        return True
    if event.city and event.city.lower().strip() in GTA_CITIES:
        return True
    # Ontario without a specific non-GTA city is likely GTA on Sulekha
    if ", on" in event.address.lower() or "ontario" in event.address.lower():
        return True
    return False


def publish_stories():
    """Publish countdown stories for posted events that are <5 days away."""
    from image_generator.create_story import create_story_image
    from publisher.instagram import publish_story

    candidates = get_story_candidates(max_days=5)
    if not candidates:
        print("No story candidates found.")
        return

    print(f"Found {len(candidates)} story candidate(s)")
    for event, days_left in candidates:
        print(f"  [{days_left}d to go] {event.title[:60]}...")
        try:
            story_path = create_story_image(event, days_left, style="C")
            print(f"    -> Story image: {story_path.name}")
            media_id, image_url = publish_story(story_path)
            mark_story_posted(event.source, event.source_id, days_left)
            print(f"    -> Story published (media_id: {media_id})")
        except Exception as e:
            print(f"    -> STORY ERROR: {e}")


def ingest(classify_limit: int = 10):
    """Ingest events: scrape sources, filter, classify, and save to DB. No image generation or publishing."""
    # Step 1: Scrape sources
    print("\n=== STEP 1: Scraping events ===")
    events = scrape_events()
    print(f"Scraped {len(events)} events total\n")

    # Step 2: Filter new + local events
    print("=== STEP 2: Filtering new events in Toronto/GTA ===")
    new_events = []
    skipped_location = 0
    for e in events:
        if not is_new(e):
            continue
        if not is_gta_event(e):
            skipped_location += 1
            print(f"  Skipping (not GTA): {e.title[:50]} [{e.city or 'no city'}]")
            continue
        similar = find_similar_event(e)
        if similar:
            print(f"  Skipping (similar to existing): {e.title[:50]} ≈ \"{similar['title'][:50]}\" (posted={similar['posted']})")
            continue
        new_events.append(e)
    print(f"{len(new_events)} new GTA events ({skipped_location} skipped for location)")

    # Deduplicate (same date + similar title = same event, different showtime)
    new_events = dedup_events(new_events)
    print(f"{len(new_events)} after dedup\n")

    if not new_events:
        print("No new events to process. Done!")
        return

    # Step 3: Classify (lazily — stop after classify_limit)
    print(f"=== STEP 3: Classifying events (limit: {classify_limit}) ===")
    indian_count = 0
    classified = 0
    for i, event in enumerate(new_events):
        if classified >= classify_limit:
            print(f"\n  Reached classify limit of {classify_limit}, skipping remaining {len(new_events) - classified} events")
            break

        print(f"  [{i+1}/{len(new_events)}] Classifying: {event.title[:60]}...")
        is_indian, reason, cleaned_title = classify_event(
            title=event.title,
            description=event.description,
            categories=event.categories,
            languages=event.languages,
            organizer=event.organizer,
        )
        if cleaned_title != event.title:
            print(f"    -> Title cleaned: {event.title!r} → {cleaned_title!r}")
            event.title = cleaned_title
        print(f"    -> {'INDIAN' if is_indian else 'NOT INDIAN'}: {reason}")

        save_event(event, is_indian, reason)
        classified += 1
        if is_indian:
            indian_count += 1

    print(f"\n{indian_count} Indian events found (classified {classified}/{len(new_events)})")
    print("Ingestion complete. Run --post to generate images and publish.")


def post(post_limit: int = 2, dry_run: bool = False, stories: bool = True):
    """Generate images and publish unposted events to IG + FB + link-in-bio."""
    from image_generator.create_post import create_post_image
    from image_generator.image_search import classify_event as classify_performer
    from publisher.instagram import publish_post, build_caption
    from publisher.instagram_handle import lookup_instagram_handle
    from publisher.facebook import publish_to_facebook, build_fb_caption
    from publisher.linkinbio import generate_linkinbio

    # Get unposted events, filtering out those with a similar already-posted event
    all_unposted = get_unposted_events()
    unposted = []
    for e in all_unposted:
        similar = find_similar_event(e)
        if similar and similar["posted"]:
            continue  # a similar event was already posted (e.g. different showtime)
        unposted.append(e)

    if not unposted:
        print("No unposted events found.")
        # Still update link-in-bio in case events expired
        print("\n=== Updating link-in-bio page ===")
        generate_linkinbio()
        return

    to_post = unposted[:post_limit]
    mode = "DRY RUN" if dry_run else "Publishing"
    print(f"\n=== {mode}: {len(to_post)} event(s) to Instagram + Facebook ===")

    posted = 0
    for i, event in enumerate(to_post):
        print(f"\n  [{i+1}/{len(to_post)}] {'[DRY RUN] ' if dry_run else ''}{event.title[:60]}...")

        # Generate image
        try:
            path = create_post_image(event, style="B")
        except Exception as e:
            print(f"    -> IMAGE ERROR: {e}")
            continue

        # Look up Instagram handles for all artists
        ig_handles = []
        try:
            info = classify_performer(event.title, event.description)
            for artist_name in info.get("artist_names", []):
                try:
                    h = lookup_instagram_handle(artist_name, info["type"])
                    if h:
                        ig_handles.append(h)
                except Exception as e:
                    print(f"    -> Handle lookup error for '{artist_name}' (continuing): {e}")
        except Exception as e:
            print(f"    -> Classification error (continuing): {e}")

        caption = build_caption(event, instagram_handles=ig_handles)

        if dry_run:
            if ig_handles:
                print(f"    -> Artist tags: {', '.join(f'@{h}' for h in ig_handles)}")
            else:
                print(f"    -> Artist tags: none")
            print(f"    -> Caption preview:")
            for line in caption.split('\n')[:6]:
                print(f"       {line}")
            print(f"       ...")
            print(f"    -> [DRY RUN] Would publish to Instagram + Facebook")
        else:
            try:
                event_key = f"{event.source}::{event.source_id}"
                media_id, posted_image_url = publish_post(
                    path, caption, instagram_handles=ig_handles, event_key=event_key,
                )
                mark_posted(event.source, event.source_id, posted_image_url)
                posted += 1
                print(f"    -> Instagram published (media_id: {media_id})")

                # Cross-post to Facebook using the same uploaded image
                try:
                    fb_caption = build_fb_caption(event, instagram_handles=ig_handles)
                    fb_post_id = publish_to_facebook(posted_image_url, fb_caption)
                    print(f"    -> Facebook published (post_id: {fb_post_id})")
                except Exception as e:
                    print(f"    -> Facebook publish error: {e}")
            except Exception as e:
                print(f"    -> PUBLISH ERROR: {e}")

    if dry_run:
        print(f"\nDry run complete!")
    else:
        print(f"\n{posted} event(s) published.")

    # Publish countdown stories
    if stories and not dry_run:
        print(f"\n=== Publishing countdown stories ===")
        publish_stories()
    elif stories and dry_run:
        print(f"\n=== [DRY RUN] Countdown stories ===")
        candidates = get_story_candidates(max_days=5)
        if candidates:
            for event, days_left in candidates:
                print(f"  [{days_left}d to go] {event.title[:60]} — would publish story")
        else:
            print("  No story candidates found.")

    # Update link-in-bio page
    print("\n=== Updating link-in-bio page ===")
    generate_linkinbio()

    # Export admin dashboard data
    print("\n=== Updating admin dashboard ===")
    from publisher.admin_export import export_admin_json
    export_admin_json()


def reconcile(dry_run: bool = False):
    """Reconcile DB posted status with what's actually on Instagram.

    Fetches all posts from our IG account, matches them to DB events via
    alt_text keys (format "iet::source::source_id"), and marks any DB events
    as unposted if they're no longer on Instagram (e.g. manually deleted).

    For legacy posts without alt_text keys, falls back to caption title matching.
    """
    from publisher.instagram import fetch_posted_media
    from data.store import get_connection

    print("\n=== Reconciling DB with Instagram ===")

    # Step 1: Fetch all posts from Instagram
    print("  Fetching posts from Instagram...")
    ig_media = fetch_posted_media(limit=200)
    print(f"  Found {len(ig_media)} posts on Instagram")

    # Build lookup sets
    ig_keys = set()       # event keys from alt_text (reliable)
    ig_captions = set()   # first line of captions (fallback for legacy)
    for m in ig_media:
        if m["event_key"]:
            ig_keys.add(m["event_key"])
        caption = m.get("caption", "") or ""
        first_line = caption.split("\n")[0].strip()
        if first_line:
            ig_captions.add(first_line.lower())

    # Step 2: Check DB events marked as posted (future events only)
    conn = get_connection()
    rows = conn.execute(
        "SELECT source, source_id, title FROM processed_events "
        "WHERE posted = 1 AND is_indian = 1 AND date >= date('now')"
    ).fetchall()
    print(f"  DB has {len(rows)} events marked as posted")

    missing = []
    for source, source_id, title in rows:
        key = f"{source}::{source_id}"
        if key in ig_keys:
            continue  # found by alt_text key — confirmed on IG
        if title.lower() in ig_captions:
            continue  # found by caption match
        # Only mark as missing if we can verify it was posted with alt_text keys.
        # If its key isn't in ig_keys, it could be a legacy post that never had
        # alt_text — we can't tell if it was deleted or just predates the feature.
        # Safe heuristic: only reconcile if at least SOME posts have alt_text keys
        # (meaning the feature is active) AND this event was posted recently enough
        # to have had one.
        if not ig_keys:
            continue  # no alt_text keys on any post yet — can't reconcile safely
        missing.append((source, source_id, title))

    if not missing:
        print("  ✓ All posted events are still on Instagram")
        conn.close()
        return

    print(f"\n  Found {len(missing)} event(s) in DB marked posted but NOT on Instagram:")
    for source, source_id, title in missing:
        print(f"    - {title}")

    if dry_run:
        print(f"\n  [DRY RUN] Would mark {len(missing)} event(s) as unposted")
    else:
        for source, source_id, title in missing:
            conn.execute(
                "UPDATE processed_events SET posted = 0, posted_image_url = '' "
                "WHERE source = ? AND source_id = ?",
                (source, source_id),
            )
        conn.commit()
        print(f"\n  ✓ Marked {len(missing)} event(s) as unposted — they'll be reposted on next --post run")

    conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ingest", action="store_true", help="Ingest events: scrape sources, filter, classify, and save to DB")
    parser.add_argument("--post", action="store_true", help="Generate images and publish unposted events")
    parser.add_argument("--reconcile", action="store_true", help="Sync DB posted status with what's actually on Instagram")
    parser.add_argument("--post-limit", type=int, default=2, help="Max posts per run (default: 2)")
    parser.add_argument("--classify-limit", type=int, default=10, help="Max events to classify per ingest (default: 10)")
    parser.add_argument("--no-stories", action="store_true", help="Skip publishing countdown stories")
    parser.add_argument("--stories-only", action="store_true", help="Only publish countdown stories")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be posted without publishing")
    args = parser.parse_args()

    if args.reconcile:
        reconcile(dry_run=args.dry_run)
    elif args.stories_only:
        if args.dry_run:
            print("\n=== [DRY RUN] Countdown stories ===")
            candidates = get_story_candidates(max_days=5)
            if candidates:
                for event, days_left in candidates:
                    print(f"  [{days_left}d to go] {event.title[:60]} — would publish story")
            else:
                print("  No story candidates found.")
        else:
            print("\n=== Publishing countdown stories ===")
            publish_stories()
    elif args.ingest:
        ingest(classify_limit=args.classify_limit)
    elif args.post:
        post(post_limit=args.post_limit, dry_run=args.dry_run, stories=not args.no_stories)
    else:
        parser.print_help()
        sys.exit(1)
