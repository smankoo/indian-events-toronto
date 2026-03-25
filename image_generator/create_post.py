"""Generate Instagram post images (1080x1350) using Pillow.

Layout (top → bottom):
  5 px   saffron top bar
  900 px image box (cover or contain-with-blur)
  1 px   separator
  391 px event info card
  50 px  branding row
  4 px   saffron bottom bar
"""

import io
import re
import textwrap
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from models import Event

# ── Paths ──────────────────────────────────────────────────────────
FONTS_DIR = Path(__file__).parent.parent / "fonts"
OUTPUT_DIR = Path(__file__).parent.parent / "output"
FONT_PATH = FONTS_DIR / "Montserrat.ttf"

# ── Canvas dimensions ──────────────────────────────────────────────
CANVAS_W = 1080
CANVAS_H = 1350
TOP_BAR_H = 5
IMAGE_BOX_H = 900
BRANDING_H = 50
BOTTOM_BAR_H = 4
CARD_H = CANVAS_H - TOP_BAR_H - IMAGE_BOX_H - BRANDING_H - BOTTOM_BAR_H  # 391

# ── Colors ─────────────────────────────────────────────────────────
ACCENT = (255, 153, 51)       # #FF9933 saffron
DARK_BG = (15, 15, 18)        # #0f0f12
CARD_BG = (10, 10, 14)        # #0a0a0e
WHITE = (255, 255, 255)
TITLE_COLOR = WHITE
DATE_COLOR = ACCENT
TIME_COLOR = (170, 170, 204)   # #aaaacc
TIME_DOT_COLOR = (102, 102, 102)  # #666666
VENUE_COLOR = (144, 144, 176)  # #9090b0
HANDLE_COLOR = ACCENT
SEPARATOR_COLOR = (255, 255, 255, 20)  # rgba(255,255,255,0.08)
GRADIENT_DARK = (42, 26, 10)   # fallback gradient center

# ── Font sizes & weights ──────────────────────────────────────────
TITLE_SIZE = 52
TITLE_WEIGHT = 800
DATE_SIZE = 30
DATE_WEIGHT = 700
TIME_SIZE = 28
TIME_WEIGHT = 400
VENUE_SIZE = 26
VENUE_WEIGHT = 400
PRICE_SIZE = 28
PRICE_WEIGHT = 700
HANDLE_SIZE = 22
HANDLE_WEIGHT = 600

# ── Card padding ──────────────────────────────────────────────────
CARD_PAD_TOP = 32
CARD_PAD_SIDE = 56


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

def _load_font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    """Load Montserrat at a given size and variable weight."""
    font = ImageFont.truetype(str(FONT_PATH), size=size)
    font.set_variation_by_axes([weight])
    return font


def _fit_image_cover(img: Image.Image, w: int, h: int) -> Image.Image:
    """Crop-fill image to exactly w×h (no letterboxing, guaranteed)."""
    return ImageOps.fit(img, (w, h), method=Image.LANCZOS)


def _fit_image_contain(img: Image.Image, w: int, h: int) -> Image.Image:
    """Fit image inside w×h with blurred ambient background fill."""
    # Scale the image to fit inside the box
    img_ratio = img.width / img.height
    box_ratio = w / h
    if img_ratio > box_ratio:
        # Image is wider — fit to width
        new_w = w
        new_h = round(w / img_ratio)
    else:
        # Image is taller — fit to height
        new_h = h
        new_w = round(h * img_ratio)
    sharp = img.resize((new_w, new_h), Image.LANCZOS)

    # Create blurred ambient background from the same image
    # Oversized so blur doesn't create white edges
    pad = 80
    bg = img.resize((w + pad * 2, h + pad * 2), Image.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=40))
    bg = ImageEnhance.Brightness(bg).enhance(0.55)
    bg = ImageEnhance.Color(bg).enhance(1.8)
    bg = bg.crop((pad, pad, pad + w, pad + h))

    # Center the sharp image on top of the blur
    x = (w - new_w) // 2
    y = (h - new_h) // 2
    bg.paste(sharp, (x, y))
    return bg


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = font.getbbox(test)
        if bbox[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _draw_price_pill(draw: ImageDraw.ImageDraw, x: int, y: int, text: str,
                     font: ImageFont.FreeTypeFont) -> None:
    """Draw an outlined saffron pill with text."""
    pad_x, pad_y = 26, 8
    border = 2
    bbox = font.getbbox(text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pill_w = text_w + pad_x * 2
    pill_h = text_h + pad_y * 2
    # Rounded rectangle outline
    draw.rounded_rectangle(
        [x, y, x + pill_w, y + pill_h],
        radius=pill_h,  # fully rounded ends
        outline=ACCENT,
        width=border,
    )
    # Center text inside pill
    tx = x + pad_x
    ty = y + pad_y - bbox[1]  # compensate for font ascent offset
    draw.text((tx, ty), text, fill=ACCENT, font=font)


def download_image(url: str) -> Image.Image | None:
    try:
        resp = requests.get(url, timeout=15, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        resp.raise_for_status()
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        print(f"    Warning: could not download image: {e}")
        return None


def format_price(price: str) -> str:
    p = price.replace("CAD ", "CA$").replace("CAD", "CA$")
    m = re.match(r'CA\$(\d+)(?:\.\d+)?(?:\s*[-–]\s*(?:CA\$)?(\d+)(?:\.\d+)?)?', p)
    if m:
        low, high = m.group(1), m.group(2)
        if high and low != high:
            return f"From CA${low}"
        return f"CA${low}"
    return p


# ══════════════════════════════════════════════════════════════════
# Rendering
# ══════════════════════════════════════════════════════════════════

def _render_post(bg_img: Image.Image | None, title: str, date_text: str,
                 time_text: str, venue_text: str, price_text: str,
                 image_fit: str = "cover") -> Image.Image:
    """Compose the full 1080×1350 post image using Pillow."""
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), DARK_BG)
    draw = ImageDraw.Draw(canvas)

    # ── Top saffron bar ──
    draw.rectangle([0, 0, CANVAS_W, TOP_BAR_H], fill=ACCENT)

    # ── Image box ──
    y_img = TOP_BAR_H
    if bg_img:
        if image_fit == "cover":
            fitted = _fit_image_cover(bg_img, CANVAS_W, IMAGE_BOX_H)
        else:
            fitted = _fit_image_contain(bg_img, CANVAS_W, IMAGE_BOX_H)
        canvas.paste(fitted, (0, y_img))
    else:
        # Warm gradient fallback
        draw.rectangle([0, y_img, CANVAS_W, y_img + IMAGE_BOX_H], fill=GRADIENT_DARK)

    # ── Separator line ──
    sep_y = y_img + IMAGE_BOX_H
    sep_overlay = Image.new("RGBA", (CANVAS_W, 1), SEPARATOR_COLOR)
    canvas.paste(sep_overlay.convert("RGB"), (0, sep_y))

    # ── Card background ──
    card_y = sep_y + 1
    draw.rectangle([0, card_y, CANVAS_W, card_y + CARD_H], fill=CARD_BG)

    # ── Card text ──
    max_text_w = CANVAS_W - CARD_PAD_SIDE * 2
    cursor_y = card_y + CARD_PAD_TOP

    # Title
    title_font = _load_font(TITLE_SIZE, TITLE_WEIGHT)
    title_lines = _wrap_text(title, title_font, max_text_w)
    line_spacing = round(TITLE_SIZE * 1.15)
    for line in title_lines:
        draw.text((CARD_PAD_SIDE, cursor_y), line, fill=TITLE_COLOR, font=title_font)
        cursor_y += line_spacing
    cursor_y += 22 - (line_spacing - TITLE_SIZE)  # margin-bottom: 22px

    # Date + Time row
    date_font = _load_font(DATE_SIZE, DATE_WEIGHT)
    draw.text((CARD_PAD_SIDE, cursor_y), date_text, fill=DATE_COLOR, font=date_font)
    if time_text:
        date_bbox = date_font.getbbox(date_text)
        date_w = date_bbox[2] - date_bbox[0]
        dot_x = CARD_PAD_SIDE + date_w
        # Dot separator
        time_font = _load_font(TIME_SIZE, TIME_WEIGHT)
        dot_text = "  ·  "
        draw.text((dot_x, cursor_y + 1), dot_text, fill=TIME_DOT_COLOR, font=time_font)
        dot_bbox = time_font.getbbox(dot_text)
        dot_w = dot_bbox[2] - dot_bbox[0]
        # Time
        draw.text((dot_x + dot_w, cursor_y + 1), time_text, fill=TIME_COLOR, font=time_font)
    cursor_y += DATE_SIZE + 10  # margin-bottom: 10px

    # Venue
    venue_font = _load_font(VENUE_SIZE, VENUE_WEIGHT)
    venue_lines = _wrap_text(venue_text, venue_font, max_text_w)
    venue_line_h = round(VENUE_SIZE * 1.4)
    for line in venue_lines:
        draw.text((CARD_PAD_SIDE, cursor_y), line, fill=VENUE_COLOR, font=venue_font)
        cursor_y += venue_line_h
    cursor_y += 22 - (venue_line_h - VENUE_SIZE)  # margin-bottom: 22px

    # Price pill
    if price_text:
        price_font = _load_font(PRICE_SIZE, PRICE_WEIGHT)
        _draw_price_pill(draw, CARD_PAD_SIDE, cursor_y, price_text, price_font)

    # ── Branding row ──
    branding_y = CANVAS_H - BOTTOM_BAR_H - BRANDING_H
    handle_font = _load_font(HANDLE_SIZE, HANDLE_WEIGHT)
    handle_text = "@indian.events.toronto"
    handle_bbox = handle_font.getbbox(handle_text)
    handle_w = handle_bbox[2] - handle_bbox[0]
    handle_x = CANVAS_W - CARD_PAD_SIDE - handle_w
    handle_text_y = branding_y + (BRANDING_H - (handle_bbox[3] - handle_bbox[1])) // 2
    draw.text((handle_x, handle_text_y), handle_text, fill=HANDLE_COLOR, font=handle_font)

    # ── Bottom saffron bar ──
    draw.rectangle([0, CANVAS_H - BOTTOM_BAR_H, CANVAS_W, CANVAS_H], fill=ACCENT)

    return canvas


# ══════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════

def create_post_image(event: Event, style: str = "A") -> Path:
    """Create an Instagram post image (1080×1350) using Pillow."""
    from image_generator.image_search import (
        search_event_image, classify_event, cache_key as _cache_key, is_placeholder,
    )
    from image_generator.ai_enhance import enhance_image

    OUTPUT_DIR.mkdir(exist_ok=True)

    # --- Classify event type (used for AI enhancement prompting) ---
    info = classify_event(event.title, event.description)
    performer_type = info["type"]
    artist_name = info["artist_name"]
    event_cache_key = _cache_key(event.title)

    # --- Primary source: best Sulekha event image ---
    sulekha_img = None
    image_urls = getattr(event, "image_urls", []) or ([event.image_url] if event.image_url else [])
    best_score = float("inf")
    for url in image_urls:
        raw = download_image(url)
        if raw and not is_placeholder(raw):
            ratio = raw.width / raw.height
            score = abs(ratio - 1.0)
            print(f"    Sulekha image option: {raw.width}x{raw.height} (ratio {ratio:.2f}, score {score:.2f})")
            if score < best_score:
                best_score = score
                sulekha_img = raw
    if sulekha_img:
        print(f"    Best Sulekha image: {sulekha_img.width}x{sulekha_img.height}")
    elif image_urls:
        print(f"    All Sulekha images unusable (placeholder or download failed)")

    # --- AI Enhancement ---
    ai_generated = False
    bg_img = enhance_image(
        source_img=sulekha_img,
        title=event.title,
        description=event.description,
        performer_type=performer_type,
        artist_name=artist_name,
        cache_key=event_cache_key,
    )
    if bg_img:
        ai_generated = True

    if not bg_img and sulekha_img:
        from image_generator.image_search import has_significant_text
        if not has_significant_text(sulekha_img):
            bg_img = sulekha_img
            print(f"    AI enhance failed, using Sulekha image directly")
        else:
            print(f"    Sulekha image has text overlays, skipping")

    if not bg_img:
        print(f"    No Sulekha image, falling back to web search...")
        bg_img = search_event_image(
            event.title, description=event.description, max_results=8, event_info=info,
        )

    # --- Render with Pillow ---
    title = event.title
    date_text = event.date.strftime("%A, %B %-d").upper()
    time_text = event.time_str.upper() if event.time_str else ""
    venue_text = event.venue
    if event.city and event.city.lower() not in event.venue.lower():
        venue_text += "  ·  " + event.city
    price_text = format_price(event.price) if event.price else ""

    image_fit = "cover" if ai_generated else "contain"
    canvas = _render_post(bg_img, title, date_text, time_text, venue_text, price_text, image_fit)

    safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in event.title)[:50].strip().replace(" ", "_")
    date_str = event.date.strftime("%Y%m%d")
    output_path = OUTPUT_DIR / f"{date_str}_{safe_title}.png"
    canvas.save(str(output_path), "PNG")
    print(f"    -> Image: {output_path.name}")

    return output_path
