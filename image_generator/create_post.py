import io
import re
import tempfile
from pathlib import Path

import requests
from PIL import Image

from models import Event

FONTS_DIR = Path(__file__).parent.parent / "fonts"
OUTPUT_DIR = Path(__file__).parent.parent / "output"

# Instagram portrait (4:5)
CANVAS_W = 1080
CANVAS_H = 1350

# Layout split — image box vs event info (in px, not counting the fixed bars)
TOP_BAR_H    = 5      # saffron accent line
BOTTOM_BAR_H = 4      # saffron accent line
BRANDING_H   = 50     # @handle row
IMAGE_BOX_H  = 900    # ~70% of canvas
# INFO_H is whatever is left

# Colors
ACCENT_HEX  = "#FF9933"
DARK_BG_HEX = "#0f0f12"
CARD_BG_HEX = "#16161c"


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


def clean_title(title: str) -> str:
    patterns = [
        r'\s*[-–—]\s*Live\s+In\s+Toronto.*$',
        r'\s*Live\s+In\s+Toronto.*$',
        r'\s*[-–—]\s*Toronto,?\s*O[Nn]?.*$',
        r'\s*\|\s*Tickets\s+Start.*$',
        r'\s*\((?:\d+:\d+\s*(?:am|pm))\).*$',
        r'\s*Stand\s*-?\s*Up\s+Comedy\s+Live\s+In\s+Toronto.*$',
        r'\s*Standup\s+Comedy\s+Live\s+\d{4}$',
    ]
    cleaned = title
    for pat in patterns:
        cleaned = re.sub(pat, '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'^(?:Toronto|Brampton|Mississauga),?\s*(?:On)?\s*[-–—]\s*', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip() or title


def format_price(price: str) -> str:
    p = price.replace("CAD ", "CA$").replace("CAD", "CA$")
    m = re.match(r'CA\$(\d+)(?:\.\d+)?(?:\s*[-–]\s*(?:CA\$)?(\d+)(?:\.\d+)?)?', p)
    if m:
        low, high = m.group(1), m.group(2)
        if high and low != high:
            return f"From CA${low}"
        return f"CA${low}"
    return p


def _image_box_css(bg_path: str | None) -> str:
    """
    CSS for the image box.
    The image is always centered and contained (no cropping of content).
    A blurred, darkened copy of the same image fills any empty space around it
    — the ambient backlight effect — all within the box, never outside.
    """
    if not bg_path:
        return f"background: {DARK_BG_HEX};"
    url = f"url('file://{bg_path}')"
    return f"""
    position: relative;
    overflow: hidden;
    background: {DARK_BG_HEX};"""


def _build_html(bg_path: str | None, event: Event, style: str = "A") -> str:
    from image_generator.styles import build_html_A, build_html_B, build_html_C, build_html_D

    font_path    = str(FONTS_DIR / "Montserrat.ttf")
    title        = clean_title(event.title)
    date_text    = event.date.strftime("%A, %B %-d").upper()
    time_text    = event.time_str.upper() if event.time_str else ""
    venue_text   = event.venue
    if event.city and event.city.lower() not in event.venue.lower():
        venue_text += f"  ·  {event.city}"
    price_text   = format_price(event.price) if event.price else ""

    builders = {"A": build_html_A, "B": build_html_B, "C": build_html_C, "D": build_html_D}
    builder  = builders.get(style, build_html_A)
    return builder(font_path, bg_path, title, date_text, time_text, venue_text, price_text)


def create_post_image(event: Event, style: str = "A") -> Path:
    """Create an Instagram post image using Playwright for crisp text rendering."""
    from playwright.sync_api import sync_playwright
    from image_generator.image_search import search_event_image

    OUTPUT_DIR.mkdir(exist_ok=True)

    # --- Fetch background image (raw — layout handled by CSS) ---
    print(f"    Searching for high-res image...")
    bg_img = search_event_image(event.title, description=event.description, max_results=8)
    if bg_img:
        print(f"    Found web image: {bg_img.size[0]}x{bg_img.size[1]}")
    else:
        bg_img = download_image(event.image_url) if event.image_url else None
        if bg_img:
            print(f"    Using Sulekha image: {bg_img.size[0]}x{bg_img.size[1]}")

    # Save raw image to temp file — CSS does all the fitting/cropping
    bg_path = None
    tmp_img = None
    if bg_img:
        tmp_img = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        bg_img.save(tmp_img.name, "JPEG", quality=95)
        bg_path = tmp_img.name

    html = _build_html(bg_path, event, style)

    safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in event.title)[:50].strip().replace(" ", "_")
    date_str   = event.date.strftime("%Y%m%d")
    output_path = OUTPUT_DIR / f"{date_str}_{safe_title}.png"

    tmp_html = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
    tmp_html.write(html)
    tmp_html.close()

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--allow-file-access-from-files"])
        ctx  = browser.new_context(viewport={"width": CANVAS_W, "height": CANVAS_H})
        page = ctx.new_page()
        page.goto(f"file://{tmp_html.name}", wait_until="networkidle")
        page.screenshot(path=str(output_path))
        browser.close()

    Path(tmp_html.name).unlink(missing_ok=True)
    if tmp_img:
        Path(tmp_img.name).unlink(missing_ok=True)

    return output_path
