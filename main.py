#!/usr/bin/env python3
"""Pipeline: Scrape -> Dedup -> Classify -> Generate Images -> Publish to Instagram"""

import os
import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent))

from scraper.sulekha import scrape_events
from data.store import is_new, save_event, mark_posted, get_unposted_events
from classifier.indian_classifier import classify_event
from image_generator.create_post import create_post_image
from publisher.instagram import publish_post, build_caption


def run(limit: int = 0, publish: bool = False, post_limit: int = 2):
    # Step 1: Scrape
    print("\n=== STEP 1: Scraping events ===")
    events = scrape_events()
    print(f"Scraped {len(events)} events total\n")

    # Step 2: Filter new events
    print("=== STEP 2: Checking for new events ===")
    new_events = [e for e in events if is_new(e)]
    print(f"{len(new_events)} new events (out of {len(events)} total)\n")

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
        is_indian, reason = classify_event(
            title=event.title,
            description=event.description,
            categories=event.categories,
            languages=event.languages,
            organizer=event.organizer,
        )
        print(f"    -> {'INDIAN' if is_indian else 'NOT INDIAN'}: {reason}")

        # Save to DB regardless
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

    # Step 5: Publish to Instagram (if enabled)
    if publish and generated:
        to_post = generated[:post_limit]
        print(f"\n=== STEP 5: Publishing to Instagram ({len(to_post)}/{len(generated)}) ===")
        for i, (event, path) in enumerate(to_post):
            print(f"  [{i+1}/{len(to_post)}] Posting: {event.title[:60]}...")
            try:
                caption = build_caption(event)
                media_id = publish_post(path, caption)
                mark_posted(event.source, event.source_id)
                print(f"    -> Published (media_id: {media_id})")
            except Exception as e:
                print(f"    -> PUBLISH ERROR: {e}")

        print(f"\nPublishing complete!")


def publish_unposted(post_limit: int = 2):
    """Publish previously generated but unposted events."""
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
            caption = build_caption(event)
            media_id = publish_post(image_path, caption)
            mark_posted(event.source, event.source_id)
            posted += 1
            print(f"    -> Published (media_id: {media_id})")
        except Exception as e:
            print(f"    -> PUBLISH ERROR: {e}")

    print(f"\n{posted} events published.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="Max images to generate (0 = all)")
    parser.add_argument("--publish", action="store_true", help="Also publish to Instagram")
    parser.add_argument("--post-limit", type=int, default=2, help="Max posts per run (default: 2)")
    parser.add_argument("--publish-only", action="store_true", help="Only publish unposted events (skip scrape/classify/generate)")
    args = parser.parse_args()

    if args.publish_only:
        publish_unposted(post_limit=args.post_limit)
    else:
        run(limit=args.limit, publish=args.publish, post_limit=args.post_limit)
