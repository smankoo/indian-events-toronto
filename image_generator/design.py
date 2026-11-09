"""Shared design system for posts, cards and roundups: fonts, category palettes, text helpers.

Every event category gets its own palette so the feed doesn't collapse into one look.
Party nights rotate through several palettes because they're the most common category.
"""

from datetime import datetime
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

FONTS = Path(__file__).parent.parent / "fonts"
W, H = 1080, 1350
HANDLE = "@indian.events.toronto"

_font_cache: dict = {}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    """name: anton | serif (Playfair Black) | serif-italic | inter-{regular,medium,semibold,bold,black}"""
    files = {
        "anton": "Anton-Regular.woff",
        "serif": "PlayfairDisplay-Black.woff",
        "serif-italic": "PlayfairDisplay-BoldItalic.woff",
        "inter-regular": "Inter-Regular.woff",
        "inter-medium": "Inter-Medium.woff",
        "inter-semibold": "Inter-SemiBold.woff",
        "inter-bold": "Inter-Bold.woff",
        "inter-black": "Inter-Black.woff",
    }
    key = (name, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(FONTS / files[name]), size)
    return _font_cache[key]


def hexc(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# dark: scrims/backgrounds · bg: card background · acc: accent on dark · ink: text on bg
PALETTES = {
    "garba":     dict(dark="#3a0626", bg="#c2185b", acc="#ffc23d", ink="#fff4e0", label="GARBA · DANDIYA"),
    "comedy":    dict(dark="#111111", bg="#ffd400", acc="#ffd400", ink="#111111", label="STAND-UP COMEDY"),
    "concert":   dict(dark="#2a0a06", bg="#c4401a", acc="#ffb74d", ink="#fff3e6", label="LIVE MUSIC"),
    "classical": dict(dark="#1f0d05", bg="#7a2410", acc="#e9c46a", ink="#fbf0dc", label="CLASSICAL"),
    "qawwali":   dict(dark="#06292a", bg="#0d4a4b", acc="#e9c46a", ink="#f6ecd4", label="QAWWALI · SUFI"),
    "festival":  dict(dark="#120c33", bg="#241a66", acc="#ffb627", ink="#fff3d6", label="FESTIVAL"),
    "party":     dict(dark="#0a0618", bg="#2a12ff", acc="#ff3d8b", ink="#ffffff", label="DESI NIGHT OUT"),
    "theatre":   dict(dark="#1c0a18", bg="#6a1b4d", acc="#f4a261", ink="#fdeee4", label="THEATRE · POETRY"),
    "community": dict(dark="#0b2a1f", bg="#1b5e45", acc="#f2c14e", ink="#f1f7ee", label="COMMUNITY"),
}
PARTY_VARIANTS = [
    dict(dark="#0a0618", bg="#2a12ff", acc="#ff3d8b", ink="#ffffff"),
    dict(dark="#0b0b0b", bg="#111111", acc="#c6ff3d", ink="#ffffff"),
    dict(dark="#2b0016", bg="#ff2e7e", acc="#ffe14d", ink="#ffffff"),
    dict(dark="#1a0633", bg="#4b1484", acc="#ff8a3d", ink="#fff1e6"),
]


def palette(category: str, seed: str = "") -> dict:
    p = dict(PALETTES.get(category, PALETTES["community"]))
    if category == "party" and seed:
        p.update(PARTY_VARIANTS[sum(map(ord, seed)) % len(PARTY_VARIANTS)])
    return p


# ── Event text formatting ──────────────────────────────────────────────────

def date_parts(dt: datetime) -> dict:
    return {"dow": dt.strftime("%a").upper(), "day": str(dt.day), "mon": dt.strftime("%b").upper()}


def price_label(price: str) -> str:
    import re
    if not price:
        return ""
    m = re.search(r"(\d+(?:\.\d+)?)", price.replace(",", ""))
    if not m:
        return price.strip()[:12]
    v = float(m.group(1))
    if v == 0:
        return "FREE"
    return f"${v:.0f}"


def time_label(time_str: str) -> str:
    return (time_str or "").strip().upper().replace(":00 ", " ")


# ── Image helpers ──────────────────────────────────────────────────────────

def cover(img: Image.Image, w: int, h: int, ay: float = 0.35) -> Image.Image:
    """Scale to fill w×h and crop; ay = vertical anchor (0 top, 1 bottom)."""
    r = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * r), round(img.height * r)), Image.LANCZOS)
    x = (img.width - w) // 2
    y = int((img.height - h) * ay)
    return img.crop((x, y, x + w, y + h))


def duotone(img: Image.Image, dark: str, light: str, contrast: float = 1.1) -> Image.Image:
    g = ImageOps.autocontrast(ImageOps.grayscale(img), cutoff=1)
    g = g.point(lambda v: max(0, min(255, int((v - 128) * contrast + 128))))
    return ImageOps.colorize(g, hexc(dark), hexc(light))


def grain(img: Image.Image, amount: int = 10) -> Image.Image:
    n = Image.effect_noise(img.size, amount).convert("L")
    n = ImageOps.colorize(n, (0, 0, 0), (255, 255, 255)).convert(img.mode)
    return ImageChops.blend(img, ImageChops.overlay(img, n), 0.3)


def fade_to(img: Image.Image, color: str, start: int, end: int, strength: float = 1.0,
            top: bool = False) -> Image.Image:
    """Blend into a solid colour: fully image above `start`, fully colour (x strength) past `end`.

    With top=True the direction flips: colour at the top edge fading out by `end`.
    """
    col = Image.new("L", (1, img.height))
    for y in range(img.height):
        if top:
            t = 1 - min(1, y / end) if end else 0
        else:
            t = 0 if y < start else 1 if y >= end else (y - start) / (end - start)
        col.putpixel((0, y), int(255 * t * strength))
    return Image.composite(Image.new("RGB", img.size, hexc(color)), img, col.resize(img.size))


# ── Text helpers ───────────────────────────────────────────────────────────

def fit(text: str, name: str, max_w: int, max_size: int, min_size: int = 20) -> ImageFont.FreeTypeFont:
    s = max_size
    while s > min_size and font(name, s).getlength(text) > max_w:
        s -= 2
    return font(name, s)


def wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if f.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit_block(text: str, name: str, max_w: int, max_lines: int, max_size: int,
              min_size: int = 40) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    """Largest font size at which text wraps into <= max_lines lines that each fit max_w."""
    s = max_size
    while s >= min_size:
        f = font(name, s)
        lines = wrap(text, f, max_w)
        if len(lines) <= max_lines and all(f.getlength(l) <= max_w for l in lines):
            return f, lines
        s -= 4
    f = font(name, min_size)
    return f, wrap(text, f, max_w)[:max_lines]


def ellipsize(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> str:
    if f.getlength(text) <= max_w:
        return text
    while text and f.getlength(text + "…") > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def tracked(d: ImageDraw.ImageDraw, xy, text: str, f, fill, track: int = 0, anchor: str = "la"):
    """Draw letter-spaced text. anchor 'l?' or 'r?' (? = vertical anchor)."""
    x, y = xy
    width = sum(f.getlength(c) + track for c in text) - track
    if anchor[0] == "r":
        x -= width
    elif anchor[0] == "m":
        x -= width / 2
    for c in text:
        d.text((x, y), c, font=f, fill=fill, anchor="l" + anchor[1])
        x += f.getlength(c) + track
    return width


def handle(d: ImageDraw.ImageDraw, color, y: int = H - 44, x: int = W // 2, anchor: str = "mm"):
    d.text((x, y), HANDLE, font=font("inter-semibold", 24), fill=color, anchor=anchor)
