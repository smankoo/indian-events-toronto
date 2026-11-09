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
from data.store import is_new, find_similar_event, save_event, mark_posted, get_story_candidates, mark_story_posted, _normalize_title
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


def ingest(classify_limit: int = 10, enrich: bool = True):
    """Ingest pipeline: scrape → filter → classify → profile → enrich → score.

    Scraping discovers new events and saves them to the DB. Profiling, enrichment (handle
    lookups) and scoring run on ALL future Indian events that still need them, so a failed
    step is retried on the next run. Each step can also be run on its own (--profile, --score).
    """
    _scrape(classify_limit)
    profile_events()
    if enrich:
        _enrich()
    score_events()
    print("\nIngestion complete. Run --post to generate images and publish.")


def _scrape(classify_limit: int = 10):
    """Scrape sources, filter, classify, and save to DB."""
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
        print("No new events to process.")
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


def _enrich():
    """Enrich ALL future Indian events: look up artist + venue IG handles.

    Runs on every event, not just new ones — the handle cache ensures
    already-looked-up artists/venues are instant (no API calls).
    """
    from publisher.instagram_handle import lookup_instagram_handle
    from publisher.venue_handle import lookup_venue_handle
    from data.store import query_events

    events = query_events("date >= date('now')")
    print(f"\n=== Enriching {len(events)} future Indian events ===")
    enriched = 0
    venues_enriched = 0
    for event in events:
        title, venue, city = event.title, event.venue, event.city
        try:
            for artist_name, performer_type in _headliners(event):
                try:
                    lookup_instagram_handle(artist_name, performer_type)
                    enriched += 1
                except Exception as e:
                    print(f"    Handle lookup error for '{artist_name}': {e}")
        except Exception as e:
            print(f"    Classification error for '{title[:50]}': {e}")

        # Venue handle lookup
        if venue:
            try:
                lookup_venue_handle(venue, city or "")
                venues_enriched += 1
            except Exception as e:
                print(f"    Venue handle lookup error for '{venue}': {e}")

    print(f"  Enrichment done ({enriched} artist lookups, {venues_enriched} venue lookups)")


# Profile roles → performer types used by the IG handle lookup
_ROLE_TO_TYPE = {"singer": "musician", "band": "musician", "musician": "musician",
                 "comedian": "comedian", "dj": "dj"}


def _headliners(event) -> list[tuple[str, str]]:
    """(name, performer_type) for each billed artist. Uses the profile; falls back to the
    older title-based classifier for events that haven't been profiled yet."""
    heads = (event.profile or {}).get("headliners")
    if heads is not None and event.profile:
        return [(h["name"], _ROLE_TO_TYPE.get(h.get("role", ""), "other")) for h in heads]
    from image_generator.image_search import classify_event as classify_performer
    info = classify_performer(event.title, event.description or "")
    return [(n, info["type"]) for n in info.get("artist_names", [])]


def _identity(event) -> tuple:
    """Two events with the same identity are the same show on different dates
    (e.g. the same series + headliners). Only one of them gets a feed post."""
    from data.store import _normalize_title
    from scoring.popularity import norm
    prof = event.profile or {}
    base = norm(prof.get("series") or "") or _normalize_title(event.title)
    heads = frozenset(norm(h["name"]) for h in prof.get("headliners") or [])
    return base, heads


def _awaiting_data(event) -> bool:
    """A likely-big event scored as notable while a popularity source was unavailable
    (rate limit, missing key) might really be a headliner. Hold it back while there's time;
    the next ingest re-scores it once the data arrives."""
    from datetime import datetime
    from data.store import get_score_breakdown
    if event.tier != "notable" or (event.profile or {}).get("prominence", 0) < 4:
        return False
    if (event.date.replace(tzinfo=None) - datetime.now()).days < 7:
        return False
    artists = get_score_breakdown(event.source, event.source_id).get("artists", [])
    return any("wikipedia" not in a.get("available", []) for a in artists)


def select_for_posting(limit: int) -> list:
    """Headliner then notable events, soonest first, skipping repeats of an already-posted show."""
    from data.store import query_events, mark_covered

    future = "date >= date('now')"
    unscored = query_events(f"posted = 0 AND {future} AND (tier IS NULL OR tier = '')")
    if unscored:
        print(f"  {len(unscored)} unposted event(s) not scored yet — they'll be considered after --score")
    candidates = query_events(
        f"posted = 0 AND {future} AND tier IN ('headliner', 'notable') "
        "AND (covered_by IS NULL OR covered_by = '')"
    )
    posted = query_events("posted = 1 AND date >= date('now', '-45 days')")
    seen = {}
    for e in posted:
        seen.setdefault(_identity(e), e)

    rank = {"headliner": 0, "notable": 1}
    chosen = []
    for e in sorted(candidates, key=lambda e: (rank[e.tier], e.date)):
        if _awaiting_data(e):
            print(f"  Hold (popularity data incomplete, may be a headliner): {e.title[:60]}")
            continue
        twin = seen.get(_identity(e))
        if twin and abs((twin.date - e.date).days) <= 45:
            if twin.posted_image_url:  # a real post exists — record the coverage permanently
                mark_covered(e.source, e.source_id, twin.source_id)
            print(f"  Skip (same show already posted): {e.title[:60]}")
            continue
        seen[_identity(e)] = e
        chosen.append(e)
        if len(chosen) >= limit:
            break
    return chosen


def render_post_image(event):
    """Headliners get the AI artist poster; notable events (and headliners with no real
    photo of the artist) get a typographic card."""
    from image_generator.poster import render_card, render_headliner
    if event.tier == "headliner":
        from image_generator.hero_plate import make_hero_plate
        plate = make_hero_plate(event)
        if plate is not None:
            return render_headliner(event, plate)
    return render_card(event)


def post(post_limit: int = 2, dry_run: bool = False, stories: bool = True):
    """Render and publish the next headliner/notable events to IG + FB + link-in-bio."""
    from publisher.instagram import publish_post, build_caption
    from publisher.instagram_handle import lookup_instagram_handle
    from publisher.venue_handle import lookup_venue_handle
    from publisher.facebook import publish_to_facebook, build_fb_caption
    from publisher.linkinbio import generate_linkinbio

    to_post = select_for_posting(post_limit)
    if not to_post:
        print("No events to post.")
        print("\n=== Updating link-in-bio page ===")
        generate_linkinbio()
        return

    mode = "DRY RUN" if dry_run else "Publishing"
    print(f"\n=== {mode}: {len(to_post)} event(s) to Instagram + Facebook ===")

    posted = 0
    for i, event in enumerate(to_post):
        print(f"\n  [{i+1}/{len(to_post)}] {'[DRY RUN] ' if dry_run else ''}"
              f"[{event.tier} {event.score}] {event.title[:60]}...")

        try:
            path = render_post_image(event)
            print(f"    -> Image: {path.name}")
        except Exception as e:
            print(f"    -> IMAGE ERROR: {e}")
            continue

        ig_handles = []
        for artist_name, performer_type in _headliners(event):
            try:
                h = lookup_instagram_handle(artist_name, performer_type)
                if h:
                    ig_handles.append(h)
            except Exception as e:
                print(f"    -> Handle lookup error for '{artist_name}' (continuing): {e}")

        venue_handle = None
        try:
            venue_handle = lookup_venue_handle(event.venue, event.city)
        except Exception as e:
            print(f"    -> Venue handle lookup error (continuing): {e}")

        caption = build_caption(event, instagram_handles=ig_handles, venue_handle=venue_handle)

        if dry_run:
            print(f"    -> Artist tags: {', '.join(f'@{h}' for h in ig_handles) or 'none'}")
            print(f"    -> Venue tag: {'@' + venue_handle if venue_handle else 'none'}")
            print(f"    -> Caption preview:")
            for line in caption.split('\n')[:6]:
                print(f"       {line}")
            print(f"       ...")
            print(f"    -> [DRY RUN] Would publish to Instagram + Facebook")
            continue

        try:
            event_key = f"{event.source}::{event.source_id}"
            media_id, posted_image_url = publish_post(
                path, caption, instagram_handles=ig_handles,
                venue_handle=venue_handle, event_key=event_key,
            )
            mark_posted(event.source, event.source_id, posted_image_url)
            posted += 1
            print(f"    -> Instagram published (media_id: {media_id})")
            try:
                fb_caption = build_fb_caption(event, instagram_handles=ig_handles,
                                              venue_handle=venue_handle)
                fb_post_id = publish_to_facebook(posted_image_url, fb_caption)
                print(f"    -> Facebook published (post_id: {fb_post_id})")
            except Exception as e:
                print(f"    -> Facebook publish error: {e}")
        except Exception as e:
            print(f"    -> PUBLISH ERROR: {e}")

    print("\nDry run complete!" if dry_run else f"\n{posted} event(s) published.")

    if stories and not dry_run:
        print(f"\n=== Publishing countdown stories ===")
        publish_stories()
    elif stories and dry_run:
        print(f"\n=== [DRY RUN] Countdown stories ===")
        candidates = get_story_candidates(max_days=5)
        for event, days_left in candidates:
            print(f"  [{days_left}d to go] {event.title[:60]} — would publish story")
        if not candidates:
            print("  No story candidates found.")

    print("\n=== Updating link-in-bio page ===")
    generate_linkinbio()

    print("\n=== Updating admin dashboard ===")
    from publisher.admin_export import export_admin_json
    export_admin_json()


def weekend_window(today=None):
    """(friday, sunday) of the upcoming weekend; the current one if run Fri–Sun."""
    from datetime import date, timedelta
    today = today or date.today()
    wd = today.weekday()  # Mon=0 … Sun=6
    friday = today + timedelta(days=4 - wd) if wd <= 4 else today - timedelta(days=wd - 4)
    return friday, friday + timedelta(days=2)


def _range_label(start, end) -> str:
    if start.month == end.month:
        return f"{start:%b} {start.day}–{end.day}".upper()
    return f"{start:%b} {start.day}–{end:%b} {end.day}".upper()


def roundup(dry_run: bool = False, force: bool = False, max_events: int = 12):
    """Publish the weekly "This weekend in the GTA" carousel covering every tier."""
    from datetime import date
    from data.store import query_events, roundup_exists, save_roundup
    from image_generator.poster import render_roundup

    friday, sunday = weekend_window()
    week_key = friday.isoformat()
    if roundup_exists(week_key) and not force and not dry_run:
        print(f"Roundup for weekend of {week_key} already published.")
        return

    start = max(friday, date.today())
    events = query_events("date >= ? AND date < date(?, '+1 day')", (start.isoformat(), sunday.isoformat()))
    # One entry per show (a series running Fri+Sat appears once, on its first date)
    seen, unique = set(), []
    for e in events:
        if _identity(e) in seen:
            continue
        seen.add(_identity(e))
        unique.append(e)
    rank = {"headliner": 0, "notable": 1, "listing": 2}
    unique.sort(key=lambda e: (rank.get(e.tier, 3), -e.score, e.date))
    picks = unique[:max_events]
    print(f"\n=== Weekend roundup {_range_label(friday, sunday)}: {len(picks)} event(s) ===")
    for e in picks:
        print(f"  [{e.tier or '?':9}] {e.date:%a %d} {e.title[:60]}")
    if len(picks) < 2:
        print("  Fewer than 2 events — skipping roundup this week.")
        return

    names = [(e.profile or {}).get("display_name") or e.title for e in picks]
    blurb = "Featuring " + (", ".join(names[:2]) + (f" and {len(picks) - 2} more." if len(picks) > 2 else "."))
    heading = _range_label(friday, sunday)
    paths = render_roundup(picks, heading, blurb, out_prefix=f"roundup_{week_key}")
    print(f"  Rendered {len(paths)} slide(s): {', '.join(p.name for p in paths)}")

    lines = [f"This weekend in the GTA ✨ {heading}", ""]
    for e in picks:
        prof = e.profile or {}
        name = prof.get("display_name") or e.title
        sub = prof.get("subtitle") or ""
        label = f"{name} · {sub}" if sub and sub.lower() not in name.lower() else name
        lines.append(f"• {e.date:%a %-d %b} — {label} @ {e.venue}")
    lines += ["", "🔗 Tickets & details: link in bio", "",
              "#toronto #torontoevents #indianevents #desi #bollywood #weekendplans #indianeventstoronto #gta #brampton #mississauga"]
    caption = "\n".join(lines)

    if dry_run:
        print("  [DRY RUN] Caption:\n" + "\n".join("    " + l for l in caption.split("\n")))
        return

    from publisher.instagram import publish_carousel
    from publisher.facebook import publish_album_to_facebook
    media_id, urls = publish_carousel(paths, caption, alt_key=f"roundup::{week_key}")
    save_roundup(week_key, media_id, [f"{e.source}::{e.source_id}" for e in picks])
    try:
        fb_id = publish_album_to_facebook(urls, caption)
        print(f"  Facebook published (post_id: {fb_id})")
    except Exception as e:
        print(f"  Facebook publish error: {e}")


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


def profile_events(include_past: bool = False, refresh: bool = False, workers: int = 6):
    """Extract headliners / category / series / prominence for Indian events (classifier/profile.py).

    Only events without a profile are processed unless refresh=True.
    """
    import concurrent.futures as cf
    from classifier.profile import profile_event
    from data.store import query_events, save_profile

    where = "1" if include_past else "date >= date('now')"
    if not refresh:
        where += " AND (profile_json IS NULL OR profile_json = '')"
    events = query_events(where)
    print(f"\n=== Profiling {len(events)} event(s) ===")
    done = 0
    with cf.ThreadPoolExecutor(workers) as ex:
        for event, profile in zip(events, ex.map(profile_event, events)):
            if not profile:
                continue
            save_profile(event.source, event.source_id, profile)
            done += 1
            heads = ", ".join(h["name"] for h in profile["headliners"]) or "—"
            print(f"  {event.title[:55]:55}  {profile['category']:9} p{profile['prominence']}  {heads}")
    print(f"  Profiled {done}/{len(events)}")


def score_events(include_past: bool = False, refresh: bool = False):
    """Score profiled events into headliner / notable / listing tiers (scoring/score.py).

    Unposted upcoming events are re-scored on every run, so a tier improves once a
    platform that was unavailable (rate limit, missing key) answers. Artist stats are
    cached, so this is cheap. Posted events keep their tier unless refresh=True.
    """
    from data.store import query_events, save_score
    from scoring.score import score_event

    where = "profile_json != ''"
    if not include_past:
        where += " AND date >= date('now')"
    if not refresh:
        where += " AND (tier IS NULL OR tier = '' OR posted = 0)"
    events = query_events(where)
    print(f"\n=== Scoring {len(events)} event(s) ===")
    for event in events:
        try:
            tier, score, breakdown = score_event(event)
        except Exception as e:
            print(f"  Score failed for {event.title[:50]!r}: {e}")
            continue
        save_score(event.source, event.source_id, tier, score, breakdown)
        p = breakdown["points"]
        print(f"  {score:3d} {tier:9}  {event.title[:52]:52}  "
              f"reach {p['reach']:4.1f} prom {p['prominence']:4.1f} venue {p['venue']:4.1f} price {p['price']:4.1f}")


def backfill_handles():
    """Alias for _enrich() — look up IG handles for all future Indian events."""
    _enrich()
    print("\nBackfill complete.")


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
    parser.add_argument("--backfill-handles", action="store_true", help="Look up IG handles for all future Indian events missing them")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be posted without publishing")
    parser.add_argument("--profile", action="store_true", help="Extract headliners/category/series for unprofiled events")
    parser.add_argument("--score", action="store_true", help="Score profiled events into headliner/notable/listing tiers")
    parser.add_argument("--roundup", action="store_true", help="Publish the weekly weekend-roundup carousel")
    parser.add_argument("--force", action="store_true", help="With --roundup: publish even if this weekend's roundup exists")
    parser.add_argument("--include-past", action="store_true", help="With --profile/--score: also process past events")
    parser.add_argument("--refresh", action="store_true", help="With --profile/--score: redo events that already have results")
    args = parser.parse_args()

    if args.profile:
        profile_events(include_past=args.include_past, refresh=args.refresh)
    elif args.score:
        score_events(include_past=args.include_past, refresh=args.refresh)
    elif args.roundup:
        roundup(dry_run=args.dry_run, force=args.force)
    elif args.backfill_handles:
        backfill_handles()
    elif args.reconcile:
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
