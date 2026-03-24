#!/usr/bin/env python3
"""Pipeline: Scrape -> Dedup -> Classify -> Generate Images -> Publish to Instagram + Facebook"""

import os
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from scraper.sulekha import scrape_events
from data.store import is_new, save_event, mark_posted, get_unposted_events, get_story_candidates, mark_story_posted
from classifier.indian_classifier import classify_event
from image_generator.create_post import create_post_image
from publisher.instagram import publish_post, publish_story, build_caption
from publisher.facebook import publish_to_facebook, build_fb_caption
from publisher.linkinbio import generate_linkinbio

import re
from difflib import SequenceMatcher


def _normalize_title(title: str) -> str:
    """Normalize a title for fuzzy comparison — strip times, years, filler."""
    t = title.lower()
    # Remove time references like (3:30pm), (7:00 pm)
    t = re.sub(r'\(?\d{1,2}:\d{2}\s*(?:am|pm)\)?', '', t)
    # Remove years
    t = re.sub(r'\b20\d{2}\b', '', t)
    # Remove common filler
    for filler in ['live in toronto', 'live in brampton', 'live in mississauga',
                   'toronto', 'brampton', 'mississauga', 'live', 'in', 'on']:
        t = re.sub(rf'\b{filler}\b', '', t)
    # Collapse whitespace and strip punctuation
    t = re.sub(r'[^a-z0-9 ]', '', t)
    return ' '.join(t.split())


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


def run(limit: int = 0, publish: bool = False, post_limit: int = 2, stories: bool = True):
    # Step 1: Scrape
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
        new_events.append(e)
    print(f"{len(new_events)} new GTA events ({skipped_location} skipped for location)")

    # Deduplicate (same date + similar title = same event, different showtime)
    new_events = dedup_events(new_events)
    print(f"{len(new_events)} after dedup\n")

    if not new_events:
        print("No new events to process. Done!")
        return

    # Step 3: Classify (lazily — stop once we have enough Indian events)
    target = limit if limit else post_limit
    print(f"=== STEP 3: Classifying events (need {target} Indian events) ===")
    indian_events = []
    classified = 0
    for i, event in enumerate(new_events):
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

        # Save to DB regardless (with cleaned title)
        save_event(event, is_indian, reason)
        classified += 1

        if is_indian:
            indian_events.append(event)
            if len(indian_events) >= target:
                print(f"\n  Reached target of {target} Indian events, skipping remaining {len(new_events) - classified} events")
                break

    print(f"\n{len(indian_events)} Indian events found (classified {classified}/{len(new_events)})\n")

    # Step 4: Generate images
    to_generate = indian_events[:limit] if limit else indian_events
    print(f"=== STEP 4: Generating Instagram images (producing {len(to_generate)}) ===")
    generated = []
    for i, event in enumerate(to_generate):
        print(f"  [{i+1}/{len(to_generate)}] Creating image: {event.title[:60]}...")
        try:
            path = create_post_image(event, style="B")
            print(f"    -> Saved: {path.name}")
            generated.append((event, path))
        except Exception as e:
            print(f"    -> ERROR: {e}")

    print(f"\nDone! {len(generated)} images saved to output/")

    # Step 5: Publish to Instagram + Facebook (if enabled)
    if publish and generated:
        from image_generator.image_search import classify_event as classify_performer
        from publisher.instagram_handle import lookup_instagram_handle

        to_post = generated[:post_limit]
        print(f"\n=== STEP 5: Publishing to Instagram & Facebook ({len(to_post)}/{len(generated)}) ===")
        for i, (event, path) in enumerate(to_post):
            print(f"  [{i+1}/{len(to_post)}] Posting: {event.title[:60]}...")
            try:
                # Look up artist's Instagram handle for tagging
                ig_handle = None
                try:
                    info = classify_performer(event.title, event.description)
                    if info["artist_name"]:
                        ig_handle = lookup_instagram_handle(info["artist_name"], info["type"])
                except Exception as e:
                    print(f"    -> Handle lookup error (continuing): {e}")

                caption = build_caption(event, instagram_handle=ig_handle)
                media_id, posted_image_url = publish_post(path, caption, instagram_handle=ig_handle)
                mark_posted(event.source, event.source_id, posted_image_url)
                print(f"    -> Instagram published (media_id: {media_id})")

                # Cross-post to Facebook using the same uploaded image
                try:
                    fb_caption = build_fb_caption(event, instagram_handle=ig_handle)
                    fb_post_id = publish_to_facebook(posted_image_url, fb_caption)
                    print(f"    -> Facebook published (post_id: {fb_post_id})")
                except Exception as e:
                    print(f"    -> Facebook publish error: {e}")
            except Exception as e:
                print(f"    -> PUBLISH ERROR: {e}")

        print(f"\nPublishing complete!")

    # Step 5.5: Publish countdown stories for upcoming posted events
    if stories:
        print(f"\n=== STEP 5.5: Publishing countdown stories ===")
        publish_stories()

    # Step 6: Update link-in-bio page
    print("\n=== STEP 6: Updating link-in-bio page ===")
    generate_linkinbio()


def publish_unposted(post_limit: int = 2):
    """Publish previously generated but unposted events."""
    from image_generator.image_search import classify_event as classify_performer
    from publisher.instagram_handle import lookup_instagram_handle

    print("\n=== Publishing unposted events ===")
    unposted = get_unposted_events()
    if not unposted:
        print("No unposted events found.")
        return

    output_dir = Path(__file__).parent / "output"
    to_post = unposted[:post_limit]
    posted = 0

    for event in to_post:
        # Find the matching image in output/
        date_str = event.date.strftime("%Y%m%d")
        safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in event.title)[:50].strip().replace(" ", "_")
        image_path = output_dir / f"{date_str}_{safe_title}.png"

        if not image_path.exists():
            print(f"  Skipping {event.title[:60]} — image not found: {image_path.name}")
            continue

        print(f"  Posting: {event.title[:60]}...")
        try:
            # Look up artist's Instagram handle for tagging
            ig_handle = None
            try:
                info = classify_performer(event.title, event.description)
                if info["artist_name"]:
                    ig_handle = lookup_instagram_handle(info["artist_name"], info["type"])
            except Exception as e:
                print(f"    -> Handle lookup error (continuing): {e}")

            caption = build_caption(event, instagram_handle=ig_handle)
            media_id, posted_image_url = publish_post(image_path, caption, instagram_handle=ig_handle)
            mark_posted(event.source, event.source_id, posted_image_url)
            posted += 1
            print(f"    -> Instagram published (media_id: {media_id})")

            try:
                fb_caption = build_fb_caption(event, instagram_handle=ig_handle)
                fb_post_id = publish_to_facebook(posted_image_url, fb_caption)
                print(f"    -> Facebook published (post_id: {fb_post_id})")
            except Exception as e:
                print(f"    -> Facebook publish error: {e}")
        except Exception as e:
            print(f"    -> PUBLISH ERROR: {e}")

    print(f"\n{posted} events published.")

    # Update link-in-bio page
    print("\n=== Updating link-in-bio page ===")
    generate_linkinbio()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Max images to generate (0 = all)")
    parser.add_argument("--publish", action="store_true", help="Also publish to Instagram")
    parser.add_argument("--post-limit", type=int, default=2, help="Max posts per run (default: 2)")
    parser.add_argument("--publish-only", action="store_true", help="Only publish unposted events (skip scrape/classify/generate)")
    parser.add_argument("--no-stories", action="store_true", help="Skip publishing countdown stories")
    parser.add_argument("--stories-only", action="store_true", help="Only publish countdown stories (skip everything else)")
    args = parser.parse_args()

    if args.stories_only:
        print("\n=== Publishing countdown stories ===")
        publish_stories()
    elif args.publish_only:
        publish_unposted(post_limit=args.post_limit)
        if not args.no_stories:
            print("\n=== Publishing countdown stories ===")
            publish_stories()
    else:
        run(limit=args.limit, publish=args.publish, post_limit=args.post_limit, stories=not args.no_stories)
