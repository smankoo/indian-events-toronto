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


def _build_html(bg_path: str | None, event: Event, style: str = "A", image_fit: str = "contain") -> str:
    from image_generator.styles import build_html_A, build_html_B, build_html_C, build_html_D

    font_path    = str(FONTS_DIR / "Montserrat.ttf")
    title        = event.title
    date_text    = event.date.strftime("%A, %B %-d").upper()
    time_text    = event.time_str.upper() if event.time_str else ""
    venue_text   = event.venue
    if event.city and event.city.lower() not in event.venue.lower():
        venue_text += f"  ·  {event.city}"
    price_text   = format_price(event.price) if event.price else ""

    builders = {"A": build_html_A, "B": build_html_B, "C": build_html_C, "D": build_html_D}
    builder  = builders.get(style, build_html_A)
    return builder(font_path, bg_path, title, date_text, time_text, venue_text, price_text, image_fit=image_fit)


def create_post_image(event: Event, style: str = "A") -> Path:
    """Create an Instagram post image using Playwright for crisp text rendering."""
    from playwright.sync_api import sync_playwright
    from image_generator.image_search import search_event_image, classify_event, cache_key as _cache_key, is_placeholder
    from image_generator.ai_enhance import enhance_image

    OUTPUT_DIR.mkdir(exist_ok=True)

    # --- Classify event type (used for AI enhancement prompting) ---
    info = classify_event(event.title, event.description)
    performer_type = info["type"]
    artist_name = info["artist_name"]
    event_cache_key = _cache_key(event.title)

    # --- Primary source: best Sulekha event image ---
    # Pick the image closest to square/portrait from all available URLs.
    # header2 images are 1280x500 banners (often horizontally squished);
    # gallery/root images tend to have the original aspect ratio.
    sulekha_img = None
    image_urls = getattr(event, "image_urls", []) or ([event.image_url] if event.image_url else [])
    best_score = float("inf")  # lower = closer to 1:1 = better
    for url in image_urls:
        raw = download_image(url)
        if raw and not is_placeholder(raw):
            ratio = raw.width / raw.height
            score = abs(ratio - 1.0)  # prefer square-ish
            print(f"    Sulekha image option: {raw.width}x{raw.height} (ratio {ratio:.2f}, score {score:.2f})")
            if score < best_score:
                best_score = score
                sulekha_img = raw
    if sulekha_img:
        print(f"    Best Sulekha image: {sulekha_img.width}x{sulekha_img.height}")
    elif image_urls:
        print(f"    All Sulekha images unusable (placeholder or download failed)")

    # --- AI Enhancement (Sulekha image → Gemini) ---
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
        # AI failed — use Sulekha image directly if it's reasonably clean
        from image_generator.image_search import has_significant_text
        if not has_significant_text(sulekha_img):
            bg_img = sulekha_img
            print(f"    AI enhance failed, using Sulekha image directly")
        else:
            print(f"    Sulekha image has text overlays, skipping")

    if not bg_img:
        # Last resort: try web search
        print(f"    No Sulekha image, falling back to web search...")
        bg_img = search_event_image(event.title, description=event.description, max_results=8, event_info=info)

    # Save raw image to temp file — CSS does all the fitting/cropping
    bg_path = None
    tmp_img = None
    if bg_img:
        tmp_img = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        bg_img.save(tmp_img.name, "JPEG", quality=95)
        bg_path = tmp_img.name

    # AI images have a known 5:4 ratio — use cover to fill the box cleanly
    image_fit = "cover" if ai_generated else "contain"
    html = _build_html(bg_path, event, style, image_fit=image_fit)

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
