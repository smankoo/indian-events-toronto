"""Create Instagram Story countdown images (1080x1920) using Pillow.

Style C (neon frame) is the only production style.  The Playwright-based
styles A/B/D have been removed — they were unused and Pillow gives us
deterministic rendering without a headless browser.
"""

import io
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from models import Event
from image_generator.create_post import FONTS_DIR, OUTPUT_DIR

STORY_W = 1080
STORY_H = 1920
ACCENT = (255, 153, 51)
FONT_PATH = str(FONTS_DIR / "Montserrat.ttf")


# ══════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════

def _font(size: int, weight: int = 400) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(FONT_PATH, size=size)
    f.set_variation_by_axes([weight])
    return f


def _text_w(font: ImageFont.FreeTypeFont, text: str) -> int:
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def _text_h(font: ImageFont.FreeTypeFont, text: str) -> int:
    bbox = font.getbbox(text)
    return bbox[3] - bbox[1]


def _center_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
                 y: int, fill) -> None:
    tw = _text_w(font, text)
    draw.text(((STORY_W - tw) // 2, y), text, fill=fill, font=font)


def _wrap_lines(text: str, font: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        test = f"{cur} {w}".strip()
        if _text_w(font, test) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [text]


def _composite(canvas: Image.Image, layer: Image.Image) -> Image.Image:
    """Alpha-composite an RGBA layer onto an RGB canvas, return RGB."""
    return Image.alpha_composite(canvas.convert("RGBA"), layer).convert("RGB")


def _make_glow(shape_fn, blur_radius: int) -> Image.Image:
    """Create a glow RGBA layer at full story size."""
    layer = Image.new("RGBA", (STORY_W, STORY_H), (0, 0, 0, 0))
    shape_fn(ImageDraw.Draw(layer))
    return layer.filter(ImageFilter.GaussianBlur(blur_radius))


# ══════════════════════════════════════════════════════════════════
# Background loading
# ══════════════════════════════════════════════════════════════════

def _download_and_prepare_bg(posted_image_url: str) -> Image.Image | None:
    """Download the posted image and extract a clean background.

    The posted image is 1080×1350 with possible light edges from contain-mode
    blur.  We crop to the image box (rows 5–905), trim any bright borders,
    then return the result for ImageOps.fit to cover the story canvas.
    """
    try:
        resp = requests.get(posted_image_url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        box = img.crop((0, 5, 1080, 905))

        # Trim light borders so cover-fit doesn't show white edges.
        arr = np.array(box)
        brightness = arr.mean(axis=2)
        thresh = 200

        top = 0
        for y in range(arr.shape[0] // 2):
            if brightness[y].mean() < thresh:
                top = y
                break

        bot = arr.shape[0]
        for y in range(arr.shape[0] - 1, arr.shape[0] // 2, -1):
            if brightness[y].mean() < thresh:
                bot = y + 1
                break

        left = 0
        for x in range(arr.shape[1] // 2):
            if brightness[:, x].mean() < thresh:
                left = x
                break

        right = arr.shape[1]
        for x in range(arr.shape[1] - 1, arr.shape[1] // 2, -1):
            if brightness[:, x].mean() < thresh:
                right = x + 1
                break

        trimmed = box.crop((left, top, right, bot))
        if trimmed.width < 200 or trimmed.height < 200:
            return box
        return trimmed
    except Exception as e:
        print(f"    Warning: could not download posted image: {e}")
        return None


# ══════════════════════════════════════════════════════════════════
# Style C — Neon frame
# ══════════════════════════════════════════════════════════════════

def _render_style_c(bg: Image.Image | None, days: int, title: str,
                    date_text: str) -> Image.Image:
    canvas = Image.new("RGB", (STORY_W, STORY_H), (0, 0, 0))

    # ── Background: cover full canvas, darken + saturate ──
    if bg:
        bg_cover = ImageOps.fit(bg, (STORY_W, STORY_H), method=Image.LANCZOS)
        bg_cover = ImageEnhance.Brightness(bg_cover).enhance(0.35)
        bg_cover = ImageEnhance.Color(bg_cover).enhance(1.5)
        canvas.paste(bg_cover)

    draw = ImageDraw.Draw(canvas)

    # ── Saffron bars ──
    draw.rectangle([0, 0, STORY_W, 6], fill=ACCENT)
    draw.rectangle([0, STORY_H - 6, STORY_W, STORY_H], fill=ACCENT)

    # ── Ticker ──
    ticker_font = _font(16, 700)
    _center_text(draw, "COMING SOON   \u2022   COMING SOON   \u2022   COMING SOON",
                 ticker_font, 38, (255, 153, 51, 128))

    # ── Neon frame geometry ──
    cx = STORY_W // 2
    cy = int(STORY_H * 0.39)
    hw, hh = 200, 185  # half-width, half-height
    fx1, fy1 = cx - hw, cy - hh
    fx2, fy2 = cx + hw, cy + hh

    # ── Neon glow (3 layers: wide halo → medium → tight hot edge) ──
    canvas = _composite(canvas, _make_glow(
        lambda d: d.rectangle([fx1 - 6, fy1 - 6, fx2 + 6, fy2 + 6],
                              outline=(255, 153, 51, 70), width=12),
        blur_radius=100,
    ))
    canvas = _composite(canvas, _make_glow(
        lambda d: d.rectangle([fx1 - 4, fy1 - 4, fx2 + 4, fy2 + 4],
                              outline=(255, 153, 51, 130), width=10),
        blur_radius=40,
    ))
    canvas = _composite(canvas, _make_glow(
        lambda d: d.rectangle([fx1 - 1, fy1 - 1, fx2 + 1, fy2 + 1],
                              outline=(255, 180, 80, 180), width=6),
        blur_radius=12,
    ))

    # ── Subtle inner fill ──
    fill_layer = Image.new("RGBA", (STORY_W, STORY_H), (0, 0, 0, 0))
    ImageDraw.Draw(fill_layer).rectangle([fx1, fy1, fx2, fy2], fill=(255, 153, 51, 8))
    canvas = _composite(canvas, fill_layer)

    # ── Frame borders (solid outer + subtle inner hairline) ──
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([fx1, fy1, fx2, fy2], outline=ACCENT, width=4)
    border_layer = Image.new("RGBA", (STORY_W, STORY_H), (0, 0, 0, 0))
    ImageDraw.Draw(border_layer).rectangle(
        [fx1 + 8, fy1 + 8, fx2 - 8, fy2 - 8], outline=(255, 153, 51, 65), width=1,
    )
    canvas = _composite(canvas, border_layer)

    # ── Number with saffron glow ──
    num_font = _font(220, 900)
    num_text = str(days)
    num_x = (STORY_W - _text_w(num_font, num_text)) // 2
    num_y = fy1 + 25

    canvas = _composite(canvas, _make_glow(
        lambda d: d.text((num_x, num_y), num_text, fill=(255, 153, 51, 130), font=num_font),
        blur_radius=80,
    ))
    canvas = _composite(canvas, _make_glow(
        lambda d: d.text((num_x, num_y), num_text, fill=(255, 153, 51, 50), font=num_font),
        blur_radius=160,
    ))
    draw = ImageDraw.Draw(canvas)
    draw.text((num_x, num_y), num_text, fill=ACCENT, font=num_font)

    # ── DAYS / TO GO ──
    _center_text(draw, "DAY" if days == 1 else "DAYS", _font(50, 800), fy2 - 120, WHITE)
    togo_layer = Image.new("RGBA", (STORY_W, STORY_H), (0, 0, 0, 0))
    togo_font = _font(36, 700)
    ImageDraw.Draw(togo_layer).text(
        ((STORY_W - _text_w(togo_font, "TO GO")) // 2, fy2 - 62),
        "TO GO", fill=(255, 255, 255, 153), font=togo_font,
    )
    canvas = _composite(canvas, togo_layer)

    # ── Event title (centered, with saffron text shadow) ──
    title_font = _font(50, 800)
    title_lines = _wrap_lines(title, title_font, 960)
    y = fy2 + 55
    for line in title_lines:
        lw = _text_w(title_font, line)
        lx = (STORY_W - lw) // 2
        canvas = _composite(canvas, _make_glow(
            lambda d, _lx=lx, _y=y, _l=line: d.text(
                (_lx, _y), _l, fill=(255, 153, 51, 77), font=title_font),
            blur_radius=30,
        ))
        draw = ImageDraw.Draw(canvas)
        draw.text((lx, y), line, fill=WHITE, font=title_font)
        y += int(50 * 1.15)

    # ── Date ──
    _center_text(draw, date_text, _font(28, 600), y + 12, ACCENT)

    # ── CTA gradient backdrop ──
    grad_h = 380
    grad_arr = np.zeros((grad_h, STORY_W, 4), dtype=np.uint8)
    t = np.linspace(0, 1, grad_h).reshape(-1, 1)
    grad_arr[:, :, 3] = np.broadcast_to(
        (t * t * 242).clip(0, 242).astype(np.uint8), (grad_h, STORY_W),
    )
    canvas_rgba = canvas.convert("RGBA")
    gradient = Image.fromarray(grad_arr, "RGBA")
    canvas_rgba.paste(gradient, (0, STORY_H - grad_h), gradient)
    canvas = canvas_rgba.convert("RGB")

    # ── CTA pill ──
    pill_font = _font(34, 800)
    pill_text = "GET TICKETS"
    pill_tw, pill_th = _text_w(pill_font, pill_text), _text_h(pill_font, pill_text)
    px, py = 60, 22  # padding
    pw, ph = pill_tw + px * 2, pill_th + py * 2
    pill_x = (STORY_W - pw) // 2
    pill_y = STORY_H - 260

    # Pill glow
    canvas = _composite(canvas, _make_glow(
        lambda d: d.rounded_rectangle(
            [pill_x - 10, pill_y - 10, pill_x + pw + 10, pill_y + ph + 10],
            radius=ph, fill=(255, 153, 51, 90)),
        blur_radius=30,
    ))
    canvas = _composite(canvas, _make_glow(
        lambda d: d.rounded_rectangle(
            [pill_x - 20, pill_y - 20, pill_x + pw + 20, pill_y + ph + 20],
            radius=ph, fill=(255, 153, 51, 30)),
        blur_radius=60,
    ))

    # Pill fill + border
    pfill = Image.new("RGBA", (STORY_W, STORY_H), (0, 0, 0, 0))
    ImageDraw.Draw(pfill).rounded_rectangle(
        [pill_x, pill_y, pill_x + pw, pill_y + ph],
        radius=ph, fill=(255, 153, 51, 20),
    )
    canvas = _composite(canvas, pfill)
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [pill_x, pill_y, pill_x + pw, pill_y + ph],
        radius=ph, outline=ACCENT, width=3,
    )

    # Pill text
    pill_bbox = pill_font.getbbox(pill_text)
    draw.text((pill_x + px, pill_y + py - pill_bbox[1]), pill_text, fill=ACCENT, font=pill_font)

    # ── CTA subtitle ──
    sub_font = _font(22, 700)
    sub_text = "TAP OUR PROFILE \u2022 LINK IN BIO"
    sub_layer = Image.new("RGBA", (STORY_W, STORY_H), (0, 0, 0, 0))
    ImageDraw.Draw(sub_layer).text(
        ((STORY_W - _text_w(sub_font, sub_text)) // 2, pill_y + ph + 18),
        sub_text, fill=(255, 255, 255, 190), font=sub_font,
    )
    canvas = _composite(canvas, sub_layer)

    # ── Handle ──
    handle_layer = Image.new("RGBA", (STORY_W, STORY_H), (0, 0, 0, 0))
    hfont = _font(22, 600)
    htxt = "@indian.events.toronto"
    ImageDraw.Draw(handle_layer).text(
        ((STORY_W - _text_w(hfont, htxt)) // 2, STORY_H - 58),
        htxt, fill=(255, 255, 255, 115), font=hfont,
    )
    canvas = _composite(canvas, handle_layer)

    # ── Final bars (ensure gradient didn't cover them) ──
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, 0, STORY_W, 6], fill=ACCENT)
    draw.rectangle([0, STORY_H - 6, STORY_W, STORY_H], fill=ACCENT)

    return canvas


# White constant used by the renderer
WHITE = (255, 255, 255)


# ══════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════

def create_story_image(event: Event, days_left: int, style: str = "C") -> Path:
    """Create a 1080×1920 Instagram Story countdown image.

    Args:
        event: The event (must have posted_image_url set).
        days_left: Number of days until the event.
        style: Ignored (only Style C is supported). Kept for API compat.

    Returns:
        Path to the generated PNG file.
    """
    OUTPUT_DIR.mkdir(exist_ok=True)

    title = event.title
    date_text = event.date.strftime("%A, %B %-d").upper()

    bg = _download_and_prepare_bg(event.posted_image_url)
    canvas = _render_style_c(bg, days_left, title, date_text)

    safe_title = "".join(
        c if c.isalnum() or c in "-_ " else "" for c in event.title
    )[:50].strip().replace(" ", "_")
    date_str = event.date.strftime("%Y%m%d")
    output_path = OUTPUT_DIR / f"story_{date_str}_{safe_title}_{days_left}d.png"
    canvas.save(str(output_path), "PNG")
    print(f"    -> Story: {output_path.name}")

    return output_path
