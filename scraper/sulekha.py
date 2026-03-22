import json
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from models import Event

BASE_URL = "https://events.sulekha.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}


def scrape_listing_page() -> list[dict]:
    """Fetch the main listing page and extract JSON-LD event data."""
    resp = requests.get(BASE_URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    events = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue

        # JSON-LD can be a single object or a list
        items = data if isinstance(data, list) else [data]
        for item in items:
            if item.get("@type") == "Event":
                events.append(item)

    return events


def parse_event_id_from_url(url: str) -> str:
    """Extract the numeric event ID from a Sulekha event URL."""
    match = re.search(r"_(\d+)$", url.rstrip("/"))
    return match.group(1) if match else url


def scrape_detail_page(event_url: str) -> dict:
    """Fetch an individual event page for additional details."""
    full_url = event_url if event_url.startswith("http") else BASE_URL + event_url
    resp = requests.get(full_url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    detail = {
        "image_url": "",
        "description": "",
        "categories": [],
        "languages": [],
        "organizer": "",
    }

    # Collect all event images from CDN, prioritize by quality
    candidates = {"header2": [], "header": [], "root": [], "thumbnail": []}
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if "usimg.sulekha.io/cdn/events/images/" not in src:
            continue
        if "/header2/" in src:
            candidates["header2"].append(src)
        elif "/header/" in src:
            candidates["header"].append(src)
        elif "/thumbnail/" in src:
            candidates["thumbnail"].append(src)
        elif "/organizer/" not in src:
            candidates["root"].append(src)

    # Prefer: header2 (1280x500) > root (varies) > header > thumbnail
    for key in ["header2", "root", "header", "thumbnail"]:
        if candidates[key]:
            detail["image_url"] = candidates[key][0]
            break

    # Get JSON-LD from detail page for richer data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if item.get("@type") == "Event":
                detail["description"] = item.get("description", "")
                if not detail["image_url"] and item.get("image"):
                    images = item["image"]
                    if isinstance(images, list) and images:
                        detail["image_url"] = images[0]
                    elif isinstance(images, str):
                        detail["image_url"] = images
                org = item.get("organizer", {})
                if isinstance(org, dict):
                    detail["organizer"] = org.get("name", "")

    # Try to extract categories/languages from page text
    page_text = soup.get_text()
    cat_match = re.search(r"Category[:\s]*([\w\s,&]+?)(?:\n|Languages)", page_text)
    if cat_match:
        detail["categories"] = [c.strip() for c in cat_match.group(1).split(",") if c.strip()]

    lang_match = re.search(r"Languages?[:\s]*([\w\s,&]+?)(?:\n|Category|$)", page_text)
    if lang_match:
        detail["languages"] = [l.strip() for l in lang_match.group(1).split(",") if l.strip()]

    return detail


def parse_listing_event(ld_event: dict) -> dict:
    """Extract basic event info from a JSON-LD event object on the listing page."""
    location = ld_event.get("location", {})
    address_obj = location.get("address", {})

    # Build the detail page URL
    event_url = ld_event.get("url", "")
    if event_url and not event_url.startswith("http"):
        event_url = BASE_URL + event_url

    # Parse price
    offers = ld_event.get("offers", {})
    if offers.get("@type") == "AggregateOffer":
        low = offers.get("lowPrice", "")
        high = offers.get("highPrice", "")
        currency = offers.get("priceCurrency", "CAD")
        if low and high and low != high:
            price = f"{currency} {low}-{high}"
        elif low:
            price = f"{currency} {low}"
        else:
            price = ""
    elif offers.get("price"):
        price = f"{offers.get('priceCurrency', 'CAD')} {offers['price']}"
    else:
        price = ""

    # Parse date
    start_date_str = ld_event.get("startDate", "")
    try:
        event_date = datetime.fromisoformat(start_date_str)
    except (ValueError, TypeError):
        event_date = datetime.now()

    return {
        "title": ld_event.get("name", ""),
        "date": event_date,
        "time_str": event_date.strftime("%-I:%M %p") if event_date else "",
        "venue": location.get("name", ""),
        "address": ", ".join(
            filter(None, [
                address_obj.get("streetAddress", ""),
                address_obj.get("addressLocality", ""),
                address_obj.get("addressRegion", ""),
            ])
        ),
        "city": address_obj.get("addressLocality", ""),
        "price": price,
        "event_url": event_url,
        "source_id": parse_event_id_from_url(event_url),
    }


def scrape_events() -> list[Event]:
    """Main entry point: scrape all events from Sulekha."""
    print("Scraping Sulekha listing page...")
    ld_events = scrape_listing_page()
    print(f"Found {len(ld_events)} events on listing page")

    events = []
    for i, ld_event in enumerate(ld_events):
        basic = parse_listing_event(ld_event)
        print(f"  [{i+1}/{len(ld_events)}] Fetching details: {basic['title'][:60]}...")

        try:
            detail = scrape_detail_page(basic["event_url"])
        except Exception as e:
            print(f"    Warning: could not fetch detail page: {e}")
            detail = {"image_url": "", "description": "", "categories": [], "languages": [], "organizer": ""}

        event = Event(
            source="sulekha",
            source_id=basic["source_id"],
            title=basic["title"],
            date=basic["date"],
            time_str=basic["time_str"],
            venue=basic["venue"],
            address=basic["address"],
            city=basic["city"],
            price=basic["price"],
            description=detail["description"],
            image_url=detail["image_url"],
            event_url=basic["event_url"],
            categories=detail["categories"],
            languages=detail["languages"],
            organizer=detail["organizer"],
        )
        events.append(event)

        # Be polite to the server
        if i < len(ld_events) - 1:
            time.sleep(0.5)

    return events


if __name__ == "__main__":
    events = scrape_events()
    for e in events:
        print(f"\n{'='*60}")
        print(f"  {e.title}")
        print(f"  {e.date.strftime('%b %d, %Y')} at {e.time_str}")
        print(f"  {e.venue}, {e.city}")
        print(f"  Price: {e.price}")
        print(f"  Image: {e.image_url[:80]}..." if e.image_url else "  No image")
        print(f"  Categories: {', '.join(e.categories) if e.categories else 'N/A'}")
