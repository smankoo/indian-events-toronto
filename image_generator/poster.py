"""Post designs (1080x1350):

  render_headliner(event, plate)   — full-bleed AI hero plate, artist name as the headline
  render_card(event)               — typographic card for notable events (no photo)
  render_roundup(events, label)    — weekly carousel: cover slide + list slides

Text comes from the event profile (classifier/profile.py): display_name, subtitle, category.
"""

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from image_generator.design import (
    W, H, cover, date_parts, ellipsize, fade_to, fit, fit_block, font, grain, handle,
    hexc, palette, price_label, time_label, tracked, wrap,
)
from models import Event

OUTPUT_DIR = Path(__file__).parent.parent / "output"


def _texts(event: Event) -> dict:
    p = event.profile or {}
    return {
        "name": p.get("display_name") or event.title,
        "sub": p.get("subtitle") or "",
        "category": p.get("category") or "community",
        **date_parts(event.date),
        "time": time_label(event.time_str),
        "venue": event.venue or "Venue TBA",
        "city": event.city or "",
        "price": price_label(event.price),
    }


def _out_path(event: Event, kind: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    return OUTPUT_DIR / f"{event.date:%Y%m%d}_{event.source_id}_{kind}.png"


# ── Headliner poster ───────────────────────────────────────────────────────

def render_headliner(event: Event, plate: Image.Image) -> Path:
    t = _texts(event)
    p = palette(t["category"], event.source_id)
    acc = p["acc"]
    M = 60

    img = cover(plate, W, H, ay=0.0)
    img = grain(img, 8)
    img = fade_to(img, p["dark"], 0, 210, strength=0.75, top=True)      # behind the kicker
    img = fade_to(img, p["dark"], 640, 1060)                              # behind the type
    d = ImageDraw.Draw(img)

    tracked(d, (M, 70), p["label"], font("inter-bold", 26), acc, track=5, anchor="lm")
    if t["city"]:
        tracked(d, (W - M, 70), t["city"].upper(), font("inter-bold", 26), acc, track=5, anchor="rm")

    # Headline: artist name, bottom-anchored so long names grow upward.
    f, lines = fit_block(t["name"].upper(), "anton", W - 2 * M, max_lines=3, max_size=190, min_size=80)
    lh = int(f.size * 0.98)
    base = 985 if t["sub"] else 1030
    y = base - lh * (len(lines) - 1)
    for line in lines:
        d.text((M - 8, y), line, font=f, fill="#ffffff", anchor="ls")
        y += lh
    if t["sub"]:
        sf = fit(t["sub"], "inter-medium", W - 2 * M, 40, 28)
        d.text((M, base + 55), t["sub"], font=sf, fill=acc, anchor="ls")

    _info_row(d, t, p, top=1080, light="#ffffff")
    handle(d, acc)
    out = _out_path(event, "headliner")
    img.save(out)
    return out


def _info_row(d: ImageDraw.ImageDraw, t: dict, p: dict, top: int, light: str):
    """Date block left; venue, time and price right. Shared by the headliner poster."""
    M, acc = 60, p["acc"]
    d.line([(M, top), (W - M, top)], fill=acc, width=3)
    tracked(d, (M, top + 38), t["dow"], font("inter-bold", 30), acc, track=4, anchor="lm")
    df = fit(f"{t['day']} {t['mon']}", "anton", 400, 96, 60)
    d.text((M, top + 128), f"{t['day']} {t['mon']}", font=df, fill=light, anchor="lm")

    vx, vw = 500, W - M - 500
    vf = fit(t["venue"], "inter-semibold", vw, 34, 26)
    d.text((vx, top + 58), ellipsize(t["venue"], vf, vw), font=vf, fill=light, anchor="lm")
    meta = "  ·  ".join(x for x in (t["time"], t["city"]) if x)
    d.text((vx, top + 106), meta, font=font("inter-regular", 32), fill=light, anchor="lm")
    if t["price"]:
        pf = font("inter-bold", 34)
        pw = pf.getlength(t["price"]) + 48
        d.rounded_rectangle([vx, top + 142, vx + pw, top + 196], radius=27, fill=acc)
        d.text((vx + pw / 2, top + 169), t["price"], font=pf, fill=p["dark"], anchor="mm")


# ── Typographic card ───────────────────────────────────────────────────────

def render_card(event: Event) -> Path:
    t = _texts(event)
    p = palette(t["category"], event.source_id)
    bg, ink, acc = p["bg"], p["ink"], p["acc"]
    # On light backgrounds (comedy yellow) the accent must be dark to stay readable.
    if t["category"] == "comedy":
        acc = "#111111"
    M = 64

    img = Image.new("RGB", (W, H), hexc(bg))
    rings = Image.new("RGB", (W, H), hexc(bg))
    rd = ImageDraw.Draw(rings)
    seed = sum(map(ord, event.source_id))
    cx, cy = [(W + 80, -60), (-120, 260), (W + 40, 560)][seed % 3]
    for i, r in enumerate(range(140, 1500, 70)):
        rd.ellipse([cx - r, cy - r, cx + r, cy + r], outline=hexc(acc), width=3 if i % 3 == 0 else 1)
    img = Image.blend(img, rings, 0.5)
    d = ImageDraw.Draw(img)

    tracked(d, (M, 86), p["label"], font("inter-bold", 26), acc, track=5, anchor="lm")

    day_f = font("anton", 360)
    d.text((M - 8, 480), t["day"], font=day_f, fill=ink, anchor="ls")
    dx = M + day_f.getlength(t["day"]) + 22
    d.text((dx, 300), t["mon"], font=font("anton", 110), fill=acc, anchor="ls")
    d.text((dx + 4, 360), t["dow"], font=font("inter-bold", 44), fill=ink, anchor="ls")
    if t["time"]:
        d.text((dx + 4, 412), t["time"], font=font("inter-medium", 38), fill=ink, anchor="ls")

    # Largest size whose wrapped block fits between the date block (y≈540) and the subtitle.
    size = 180
    while True:
        f, lines = fit_block(t["name"], "serif", W - 2 * M, max_lines=3, max_size=size, min_size=64)
        lh = int(f.size * 1.05)
        top = 1010 - lh * (len(lines) - 1) - int(f.size * 0.75)
        if top >= 540 or f.size <= 64:
            break
        size = f.size - 6
    y = 1010 - lh * (len(lines) - 1)
    for line in lines:
        d.text((M - 4, y), line, font=f, fill=ink, anchor="ls")
        y += lh
    if t["sub"]:
        sf = fit(t["sub"], "serif-italic", W - 2 * M, 50, 32)
        d.text((M, 1088), t["sub"], font=sf, fill=acc, anchor="ls")

    fy = 1140
    d.line([(M, fy), (W - M, fy)], fill=ink, width=2)
    pw = font("inter-black", 52).getlength(t["price"]) + 40 if t["price"] else 0
    vf = fit(t["venue"], "inter-bold", W - 2 * M - pw, 40, 28)
    d.text((M, fy + 58), ellipsize(t["venue"], vf, W - 2 * M - pw), font=vf, fill=ink, anchor="lm")
    d.text((M, fy + 108), t["city"], font=font("inter-regular", 34), fill=ink, anchor="lm")
    if t["price"]:
        d.text((W - M, fy + 82), t["price"], font=font("inter-black", 52), fill=acc, anchor="rm")
    handle(d, ink, y=H - 34)
    out = _out_path(event, "card")
    img.save(out)
    return out


# ── Weekly roundup carousel ────────────────────────────────────────────────

ROUNDUP_BG = "#0e0b14"
PAPER = "#f3ede2"
INK = "#16110c"


def _thumb_source(event: Event) -> Image.Image | None:
    """Prefer the AI plate (clean photo); fall back to the organiser's flyer."""
    from image_generator.hero_plate import _cache_path
    from classifier.profile import flyer_urls
    import io
    import requests

    plate = _cache_path(event)
    if plate.exists():
        return Image.open(plate).convert("RGB")
    poster = _posted_photo(event)
    if poster is not None:
        return poster
    for url in flyer_urls(event):
        try:
            r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            return Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception:
            continue
    return None


def _posted_photo(event: Event) -> Image.Image | None:
    """The photo area of an already-posted headliner poster (the AI plate cache doesn't
    survive between CI runs, but the published poster does)."""
    import io
    import requests
    if event.tier != "headliner" or not event.posted_image_url:
        return None
    try:
        r = requests.get(event.posted_image_url, timeout=20)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return None
    if img.size != (W, H):
        return None
    return img.crop((0, 130, W, 760))


def _photo_for_cover(event: Event) -> Image.Image | None:
    from image_generator.hero_plate import _cache_path
    if _cache_path(event).exists():
        return Image.open(_cache_path(event)).convert("RGB")
    return _posted_photo(event)


def _when(event: Event) -> str:
    dp = date_parts(event.date)
    t = time_label(event.time_str)
    return f"{dp['dow']} {dp['day']} {dp['mon']}" + (f" · {t}" if t else "")


def render_roundup(events: list[Event], heading: str, blurb: str, out_prefix: str,
                   per_slide: int = 4) -> list[Path]:
    """Cover slide + list slides. events should already be ordered (picks first)."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    paths = [_roundup_cover(events, heading, blurb, OUTPUT_DIR / f"{out_prefix}_0.png")]
    for i in range(0, len(events), per_slide):
        chunk = events[i:i + per_slide]
        paths.append(_roundup_list(chunk, heading, OUTPUT_DIR / f"{out_prefix}_{i // per_slide + 1}.png"))
    return paths


def _roundup_cover(events: list[Event], heading: str, blurb: str, out: Path) -> Path:
    img = Image.new("RGB", (W, H), hexc(ROUNDUP_BG))

    # Photo mosaic from headliners that have a clean artist photo; typographic cover otherwise.
    photos = []
    for e in events:
        ph = _photo_for_cover(e)
        if ph is not None:
            photos.append(ph)
        if len(photos) == 3:
            break
    if photos:
        g = 10
        layouts = {
            1: [(0, 0, W, 700)],
            2: [(0, 0, 540 - g // 2, 700), (540 + g // 2, 0, W, 700)],
            3: [(0, 0, 540 - g // 2, 700), (540 + g // 2, 0, W, 345), (540 + g // 2, 355, W, 700)],
        }[len(photos)]
        for (x0, y0, x1, y1), ph in zip(layouts, photos):
            tile = cover(ph, x1 - x0, y1 - y0, ay=0.15)
            img.paste(tile, (x0, y0))
        top = fade_to(img.crop((0, 0, W, 700)), ROUNDUP_BG, 420, 700)
        img.paste(top, (0, 0))
    else:
        d = ImageDraw.Draw(img)
        y = 140
        for e in events[:5]:
            pal = palette((e.profile or {}).get("category", "community"), e.source_id)
            name = (e.profile or {}).get("display_name") or e.title
            f = fit(name.upper(), "anton", W - 128, 96, 48)
            d.text((64, y), ellipsize(name.upper(), f, W - 128), font=f, fill=pal["acc"], anchor="lt")
            y += f.size + 14

    d = ImageDraw.Draw(img)
    tracked(d, (64, 660), "THIS WEEKEND IN THE GTA", font("inter-bold", 30), hexc("#ffb627"),
            track=6, anchor="lm")
    hf = fit(heading, "anton", W - 120, 230, 120)
    d.text((56, 900), heading, font=hf, fill="#ffffff", anchor="ls")
    bf = font("inter-medium", 38)
    y = 990
    for line in wrap(blurb, bf, W - 128)[:2]:
        d.text((64, y), line, font=bf, fill="#d9d2e6", anchor="ls")
        y += 52
    n = len(events)
    pill = f"{n} EVENT{'S' if n != 1 else ''}  »"
    pf = font("inter-black", 32)
    pw = pf.getlength(pill) + 70
    d.rounded_rectangle([64, 1130, 64 + pw, 1200], radius=35, fill=hexc("#ffb627"))
    d.text((64 + pw / 2, 1165), pill, font=pf, fill=ROUNDUP_BG, anchor="mm")
    handle(d, "#8a8299")
    img.save(out)
    return out


def _roundup_list(events: list[Event], heading: str, out: Path) -> Path:
    img = Image.new("RGB", (W, H), hexc(PAPER))
    d = ImageDraw.Draw(img)
    M = 56
    tracked(d, (M, 80), f"{heading} · WHAT'S ON", font("inter-bold", 28), INK, track=5, anchor="lm")
    y, rh = 140, 270
    for e in events:
        prof = e.profile or {}
        pal = palette(prof.get("category", "community"), e.source_id)
        src = _thumb_source(e)
        if src is not None:
            img.paste(cover(src, 220, 220, ay=0.15), (M, y + 20))
        else:
            d.rectangle([M, y + 20, M + 220, y + 240], fill=hexc(pal["bg"]))
        d.rectangle([M, y + 20, M + 10, y + 240], fill=hexc(pal["bg"] if prof.get("category") != "comedy" else "#c7a400"))
        x = M + 250
        label_col = hexc("#9a7d00") if prof.get("category") == "comedy" else hexc(pal["bg"] if pal["bg"] != "#111111" else "#555555")
        tracked(d, (x, y + 42), pal["label"], font("inter-bold", 20), label_col, track=4, anchor="lm")
        price = price_label(e.price)
        if price:
            d.text((W - M, y + 42), price, font=font("inter-black", 30), fill=INK, anchor="rm")
        name = prof.get("display_name") or e.title
        sub = prof.get("subtitle") or ""
        full = f"{name} · {sub}" if sub and sub.lower() not in name.lower() else name
        nf = font("inter-black", 38)
        ly = y + 92
        lines = wrap(full, nf, W - x - M)
        if len(lines) > 2:
            lines = [lines[0], ellipsize(" ".join(lines[1:]), nf, W - x - M)]
        for line in lines:
            d.text((x, ly), line, font=nf, fill=INK, anchor="lm")
            ly += 46
        d.text((x, ly + 8), _when(e), font=font("inter-semibold", 30), fill=INK, anchor="lm")
        where = ", ".join(v for v in (e.venue, e.city) if v)
        wf = font("inter-regular", 28)
        d.text((x, ly + 48), ellipsize(where, wf, W - x - M - 110), font=wf, fill="#4a4036", anchor="lm")
        if e.tier == "headliner":
            d.text((W - M, ly + 48), "TOP PICK", font=font("inter-black", 24), fill=hexc("#c2185b"), anchor="rm")
        y += rh
        d.line([(M, y + 5), (W - M, y + 5)], fill="#d6cdbd", width=2)
    d.text((M, H - 60), "Tickets & links: link in bio", font=font("inter-semibold", 30), fill="#4a4036", anchor="lm")
    handle(d, "#8a7f70", x=W - M, y=H - 60, anchor="rm")
    img.save(out)
    return out
