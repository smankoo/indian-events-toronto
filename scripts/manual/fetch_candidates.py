"""Manual run: turn the Eventbrite/AllEvents sweep into Events in the (copied) DB.

Usage: EVENTS_DB=... python -I fetch_candidates.py <sweep.json> <days>
Fetches each event page's JSON-LD, keeps GTA events in the window, skips ones already
in the DB (or near-duplicates), classifies them, and saves them. Profile/score run after
via main.py --profile / --score.
"""
import concurrent.futures as cf
import datetime as dt
import html
import json
import re
import sys
import time

sys.path.insert(0, "/home/user/indian-events-toronto")
import requests

from models import Event
from main import is_gta_event
from data.store import is_new, find_similar_event, save_event
from classifier.indian_classifier import classify_event

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
      "Accept-Language": "en-CA,en;q=0.9"}
EVENT_TYPES = {"Event", "MusicEvent", "ComedyEvent", "DanceEvent", "SocialEvent", "TheaterEvent",
               "Festival", "EducationEvent", "ExhibitionEvent", "LiteraryEvent", "ScreeningEvent"}


def ld_event(page: str) -> dict | None:
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S):
        try:
            d = json.loads(m.group(1).strip())
        except Exception:
            continue
        for it in (d if isinstance(d, list) else [d]):
            t = it.get("@type") if isinstance(it, dict) else None
            if t in EVENT_TYPES or (isinstance(t, list) and EVENT_TYPES & set(t)):
                return it
    return None


def to_event(src: str, url: str, e: dict) -> Event | None:
    try:
        start = dt.datetime.fromisoformat(e["startDate"])
    except Exception:
        return None
    loc = e.get("location") or {}
    if isinstance(loc, list):
        loc = loc[0] if loc else {}
    addr = loc.get("address") or {}
    if isinstance(addr, str):
        addr = {"streetAddress": addr}
    offers = e.get("offers") or []
    if isinstance(offers, dict):
        offers = [offers]
    prices = []
    for o in offers:
        for k in ("lowPrice", "price"):
            try:
                prices.append(float(o.get(k)))
            except (TypeError, ValueError):
                pass
    price = f"CAD {min(prices):.2f}" if prices else ""
    img = e.get("image") or ""
    if isinstance(img, list):
        img = img[0] if img else ""
    if isinstance(img, dict):
        img = img.get("url", "")
    org = e.get("organizer") or {}
    if isinstance(org, list):
        org = org[0] if org else {}
    sid = (re.search(r"(\d{6,})/?$", url.split("?")[0]) or re.search(r"(\d+)", url)).group(1)
    return Event(
        source=src, source_id=sid,
        title=html.unescape(re.sub(r"\s+", " ", e.get("name", "")).strip()),
        date=start, time_str=start.strftime("%-I:%M %p"),
        venue=html.unescape(loc.get("name", "") or ""),
        address=addr.get("streetAddress", "") or "",
        city=addr.get("addressLocality", "") or "",
        price=price,
        description=html.unescape(re.sub(r"<[^>]+>", " ", e.get("description", "") or ""))[:3000],
        image_url=img, image_urls=[img] if img else [],
        event_url=url, organizer=(org.get("name", "") if isinstance(org, dict) else str(org)),
    )


def fetch(item):
    src = "eventbrite" if "eventbrite" in item["sources"] else "allevents"
    url = item["url"]
    for attempt in range(2):
        try:
            r = requests.get(url, headers=UA, timeout=30)
            if r.status_code == 200:
                e = ld_event(r.text)
                return to_event(src, url, e) if e else None
        except requests.RequestException:
            pass
        time.sleep(2)
    return None


def main():
    sweep = json.load(open(sys.argv[1]))
    days = int(sys.argv[2])
    today = dt.date.today()
    end = (today + dt.timedelta(days=days)).isoformat()
    window = [x for x in sweep if today.isoformat() <= x["date"] <= end and x.get("url")]
    print(f"{len(window)} sweep events in the next {days} days")

    with cf.ThreadPoolExecutor(6) as ex:
        events = [e for e in ex.map(fetch, window) if e]
    print(f"{len(events)} event pages parsed")

    fresh, skipped = [], {"not GTA": 0, "already in DB": 0, "near-duplicate": 0}
    for e in events:
        if not is_gta_event(e):
            skipped["not GTA"] += 1
        elif not is_new(e):
            skipped["already in DB"] += 1
        elif find_similar_event(e):
            skipped["near-duplicate"] += 1
        else:
            fresh.append(e)
    # same show listed on both sources / twice: keep first per (date, normalized title)
    seen, unique = set(), []
    for e in fresh:
        k = (e.date.date(), re.sub(r"[^a-z0-9]", "", e.title.lower())[:30])
        if k in seen:
            skipped["near-duplicate"] += 1
            continue
        seen.add(k)
        unique.append(e)
    print(f"{len(unique)} new; skipped {skipped}")

    def classify(e):
        return e, classify_event(title=e.title, description=e.description,
                                 categories=e.categories, languages=e.languages, organizer=e.organizer)

    n_ind = 0
    with cf.ThreadPoolExecutor(6) as ex:
        for e, (is_ind, reason, cleaned) in ex.map(classify, unique):
            e.title = cleaned or e.title
            save_event(e, is_ind, reason)
            n_ind += bool(is_ind)
            print(f"  {'IND ' if is_ind else 'skip'}  {e.date:%m-%d}  {e.title[:60]:60}  {reason[:70]}")
    print(f"{n_ind}/{len(unique)} classified Indian")


if __name__ == "__main__":
    main()
