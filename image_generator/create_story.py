"""Create Instagram Story countdown images (1080x1920) with multiple style options."""

import io
import tempfile
from pathlib import Path

import requests
from PIL import Image

from models import Event
from image_generator.create_post import clean_title, FONTS_DIR, OUTPUT_DIR

STORY_W = 1080
STORY_H = 1920
ACCENT_HEX = "#FF9933"


def _download_and_crop_posted_image(posted_image_url: str) -> Image.Image | None:
    """Download the posted Instagram image and crop to the image-only portion.

    The posted image is 1080x1350 with a 5px saffron bar at top and info card below.
    We extract the 900px image box (rows 5-905).
    """
    try:
        resp = requests.get(posted_image_url, timeout=30, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        })
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content)).convert("RGB")
        # Crop to image box only: skip 5px top bar, take 900px
        return img.crop((0, 5, 1080, 905))
    except Exception as e:
        print(f"    Warning: could not download posted image: {e}")
        return None


def _save_bg_image(bg_img: Image.Image | None) -> str | None:
    """Save background image to temp file, return path."""
    if not bg_img:
        return None
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    bg_img.save(tmp.name, "JPEG", quality=95)
    return tmp.name


# ═══════════════════════════════════════════════════════════════════
# Shared CSS + HTML fragments
# ═══════════════════════════════════════════════════════════════════

def _cta_css():
    """CTA 2 (outlined pill) CSS with dark gradient backdrop."""
    return f"""
  /* Dark gradient behind CTA area */
  .cta-backdrop {{
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 380px;
    background: linear-gradient(
      to bottom,
      rgba(0,0,0,0) 0%,
      rgba(0,0,0,0.6) 30%,
      rgba(0,0,0,0.85) 70%,
      rgba(0,0,0,0.95) 100%
    );
    z-index: 11;
  }}

  .cta-container {{
    position: absolute;
    bottom: 110px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 12;
    text-align: center;
  }}

  .cta-pill {{
    display: inline-block;
    border: 3px solid {ACCENT_HEX};
    border-radius: 100px;
    padding: 22px 60px;
    box-shadow: 0 0 30px rgba(255, 153, 51, 0.35), 0 0 60px rgba(255, 153, 51, 0.12);
    background: rgba(255, 153, 51, 0.08);
  }}

  .cta-pill-text {{
    font-size: 34px;
    font-weight: 800;
    color: {ACCENT_HEX};
    letter-spacing: 5px;
    text-transform: uppercase;
    text-shadow: 0 0 15px rgba(255, 153, 51, 0.3);
  }}

  .cta-sub {{
    margin-top: 18px;
    font-size: 22px;
    font-weight: 700;
    color: rgba(255,255,255,0.75);
    letter-spacing: 2px;
  }}

  .handle {{
    position: absolute;
    bottom: 50px;
    left: 50%;
    transform: translateX(-50%);
    font-size: 22px;
    font-weight: 600;
    color: rgba(255,255,255,0.45);
    z-index: 12;
    letter-spacing: 2px;
  }}
"""


def _cta_html():
    """CTA 2 (outlined pill) HTML."""
    return """
  <div class="cta-backdrop"></div>
  <div class="cta-container">
    <div class="cta-pill">
      <span class="cta-pill-text">GET TICKETS</span>
    </div>
    <div class="cta-sub">TAP OUR PROFILE &bull; LINK IN BIO</div>
  </div>
  <div class="handle">@indian.events.toronto</div>
"""


# ═══════════════════════════════════════════════════════════════════
# Style A — Giant saffron circle badge
# ═══════════════════════════════════════════════════════════════════

def _style_a_html(font_path: str, bg_path: str | None, days: int, title: str, date_text: str) -> str:
    bg_url = f"url('file://{bg_path}')" if bg_path else "none"
    bg_filter = "filter: brightness(0.45) saturate(1.3);" if bg_path else ""
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  @font-face {{ font-family: 'Montserrat'; src: url('file://{font_path}'); font-weight: 100 900; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:{STORY_W}px; height:{STORY_H}px; overflow:hidden; font-family:'Montserrat',sans-serif; background:#000; }}
  .bg {{ position:absolute; inset:0; background-image:{bg_url}; background-size:cover; background-position:center; {bg_filter} }}
  .bar {{ position:absolute; left:0; right:0; height:6px; background:{ACCENT_HEX}; z-index:10; }}
  .bar.top {{ top:0; }} .bar.bottom {{ bottom:0; }}
  .content {{ position:relative; z-index:2; width:100%; height:100%; display:flex; flex-direction:column; justify-content:center; align-items:center; }}
  .countdown-badge {{ position:relative; width:480px; height:480px; display:flex; flex-direction:column; justify-content:center; align-items:center; margin-bottom:80px; }}
  .countdown-badge::before {{ content:''; position:absolute; inset:0; background:{ACCENT_HEX}; border-radius:50%; box-shadow:0 0 100px rgba(255,153,51,0.6),0 0 200px rgba(255,153,51,0.2); }}
  .number {{ position:relative; font-size:200px; font-weight:900; color:#fff; line-height:1; text-shadow:0 4px 20px rgba(0,0,0,0.3); }}
  .days-text {{ position:relative; font-size:48px; font-weight:800; color:#fff; letter-spacing:14px; margin-top:-5px; }}
  .to-go {{ position:relative; font-size:32px; font-weight:600; color:rgba(255,255,255,0.85); letter-spacing:8px; margin-top:4px; }}
  .event-info {{ position:absolute; bottom:280px; text-align:center; z-index:2; padding:0 60px; }}
  .event-title {{ font-size:46px; font-weight:800; color:#fff; text-shadow:0 2px 20px rgba(0,0,0,0.8); margin-bottom:12px; line-height:1.15; }}
  .event-date {{ font-size:28px; font-weight:600; color:{ACCENT_HEX}; letter-spacing:4px; text-shadow:0 2px 10px rgba(0,0,0,0.8); }}
  {_cta_css()}
</style></head>
<body>
  <div class="bg"></div>
  <div class="bar top"></div><div class="bar bottom"></div>
  <div class="content">
    <div class="countdown-badge">
      <div class="number">{days}</div>
      <div class="days-text">{"DAY" if days == 1 else "DAYS"}</div>
      <div class="to-go">TO GO</div>
    </div>
  </div>
  <div class="event-info">
    <div class="event-title">{title}</div>
    <div class="event-date">{date_text}</div>
  </div>
  {_cta_html()}
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Style B — Cinematic gradient, countdown at bottom
# ═══════════════════════════════════════════════════════════════════

def _style_b_html(font_path: str, bg_path: str | None, days: int, title: str, date_text: str) -> str:
    bg_url = f"url('file://{bg_path}')" if bg_path else "none"
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  @font-face {{ font-family: 'Montserrat'; src: url('file://{font_path}'); font-weight: 100 900; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:{STORY_W}px; height:{STORY_H}px; overflow:hidden; font-family:'Montserrat',sans-serif; background:#0a0a0e; }}
  .bg {{ position:absolute; top:0; left:0; right:0; height:1300px; background-image:{bg_url}; background-size:cover; background-position:center; }}
  .gradient {{ position:absolute; top:0; left:0; right:0; height:1300px; background:linear-gradient(to bottom, rgba(0,0,0,0) 0%, rgba(0,0,0,0) 40%, rgba(0,0,0,0.3) 60%, rgba(10,10,14,0.9) 80%, rgba(10,10,14,1) 100%); z-index:1; }}
  .bar {{ position:absolute; left:0; right:0; height:6px; background:{ACCENT_HEX}; z-index:10; }}
  .bar.top {{ top:0; }} .bar.bottom {{ bottom:0; }}
  .handle-top {{ position:absolute; top:40px; right:50px; font-size:22px; font-weight:600; color:rgba(255,255,255,0.7); z-index:5; text-shadow:0 2px 10px rgba(0,0,0,0.9); }}
  .content {{ position:absolute; bottom:280px; left:0; right:0; z-index:2; padding:0 70px; }}
  .countdown-row {{ display:flex; align-items:baseline; gap:20px; margin-bottom:30px; }}
  .number {{ font-size:180px; font-weight:900; color:{ACCENT_HEX}; line-height:1; text-shadow:0 0 60px rgba(255,153,51,0.4); }}
  .days-label {{ display:flex; flex-direction:column; }}
  .days-word {{ font-size:64px; font-weight:900; color:#fff; line-height:1; letter-spacing:4px; }}
  .to-go {{ font-size:64px; font-weight:900; color:#fff; line-height:1; letter-spacing:4px; }}
  .event-title {{ font-size:44px; font-weight:700; color:#fff; margin-bottom:8px; line-height:1.2; }}
  .event-date {{ font-size:26px; font-weight:600; color:rgba(255,255,255,0.6); letter-spacing:3px; }}
  {_cta_css()}
</style></head>
<body>
  <div class="bg"></div>
  <div class="gradient"></div>
  <div class="bar top"></div><div class="bar bottom"></div>
  <div class="handle-top">@indian.events.toronto</div>
  <div class="content">
    <div class="countdown-row">
      <div class="number">{days}</div>
      <div class="days-label">
        <span class="days-word">{"DAY" if days == 1 else "DAYS"}</span>
        <span class="to-go">TO GO</span>
      </div>
    </div>
    <div class="event-title">{title}</div>
    <div class="event-date">{date_text}</div>
  </div>
  {_cta_html()}
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Style C — Neon frame (DEFAULT)
# ═══════════════════════════════════════════════════════════════════

def _style_c_html(font_path: str, bg_path: str | None, days: int, title: str, date_text: str) -> str:
    bg_url = f"url('file://{bg_path}')" if bg_path else "none"
    bg_filter = "filter: brightness(0.35) saturate(1.5);" if bg_path else ""
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  @font-face {{ font-family: 'Montserrat'; src: url('file://{font_path}'); font-weight: 100 900; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:{STORY_W}px; height:{STORY_H}px; overflow:hidden; font-family:'Montserrat',sans-serif; background:#000; }}
  .bg {{ position:absolute; inset:0; background-image:{bg_url}; background-size:cover; background-position:center; {bg_filter} }}
  .bar {{ position:absolute; left:0; right:0; height:6px; background:{ACCENT_HEX}; z-index:10; }}
  .bar.top {{ top:0; }} .bar.bottom {{ bottom:0; }}
  .ticker {{ position:absolute; top:36px; left:0; right:0; z-index:8; text-align:center; }}
  .ticker-text {{ font-size:16px; font-weight:700; color:rgba(255,153,51,0.5); letter-spacing:10px; text-transform:uppercase; }}
  .center {{ position:absolute; top:44%; left:50%; transform:translate(-50%,-55%); z-index:5; text-align:center; }}
  .frame {{ display:inline-block; padding:50px 90px; border:4px solid {ACCENT_HEX}; box-shadow:0 0 40px rgba(255,153,51,0.35),inset 0 0 40px rgba(255,153,51,0.08); position:relative; margin-bottom:50px; }}
  .frame::after {{ content:''; position:absolute; inset:6px; border:1px solid rgba(255,153,51,0.25); }}
  .number {{ font-size:220px; font-weight:900; color:{ACCENT_HEX}; line-height:1; text-shadow:0 0 80px rgba(255,153,51,0.5),0 0 160px rgba(255,153,51,0.2); }}
  .days-text {{ font-size:50px; font-weight:800; color:#fff; letter-spacing:22px; margin-top:5px; }}
  .to-go {{ font-size:36px; font-weight:700; color:rgba(255,255,255,0.6); letter-spacing:16px; margin-top:8px; }}
  .event-title {{ font-size:50px; font-weight:800; color:#fff; text-shadow:0 0 30px rgba(255,153,51,0.3); margin-bottom:14px; line-height:1.15; }}
  .event-date {{ font-size:28px; font-weight:600; color:{ACCENT_HEX}; letter-spacing:5px; }}
  {_cta_css()}
</style></head>
<body>
  <div class="bg"></div>
  <div class="bar top"></div><div class="bar bottom"></div>
  <div class="ticker">
    <span class="ticker-text">COMING SOON &nbsp; &bull; &nbsp; COMING SOON &nbsp; &bull; &nbsp; COMING SOON</span>
  </div>
  <div class="center">
    <div class="frame">
      <div class="number">{days}</div>
      <div class="days-text">{"DAY" if days == 1 else "DAYS"}</div>
      <div class="to-go">TO GO</div>
    </div>
    <div>
      <div class="event-title">{title}</div>
      <div class="event-date">{date_text}</div>
    </div>
  </div>
  {_cta_html()}
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Style D — Split screen (original post + countdown banner)
# ═══════════════════════════════════════════════════════════════════

def _style_d_html(font_path: str, bg_path: str | None, days: int, title: str, date_text: str,
                  original_post_path: str | None = None) -> str:
    post_src = f"file://{original_post_path}" if original_post_path else ""
    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  @font-face {{ font-family: 'Montserrat'; src: url('file://{font_path}'); font-weight: 100 900; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:{STORY_W}px; height:{STORY_H}px; overflow:hidden; font-family:'Montserrat',sans-serif; background:#0f0f12; display:flex; flex-direction:column; }}
  .post-image {{ width:1080px; height:1350px; flex-shrink:0; position:relative; overflow:hidden; }}
  .post-image img {{ width:100%; height:100%; object-fit:cover; }}
  .post-image::after {{ content:''; position:absolute; bottom:0; left:0; right:0; height:80px; background:linear-gradient(to bottom,transparent,#0f0f12); }}
  .countdown-section {{ flex:1; display:flex; align-items:center; justify-content:center; gap:28px; position:relative; padding:0 60px; }}
  .countdown-section::before {{ content:''; position:absolute; top:0; left:70px; right:70px; height:4px; background:linear-gradient(to right,transparent,{ACCENT_HEX},transparent); }}
  .number {{ font-size:200px; font-weight:900; color:{ACCENT_HEX}; line-height:1; text-shadow:0 0 40px rgba(255,153,51,0.3); }}
  .text-block {{ display:flex; flex-direction:column; }}
  .days-word {{ font-size:80px; font-weight:900; color:#fff; line-height:1; letter-spacing:6px; }}
  .to-go {{ font-size:80px; font-weight:900; color:#fff; line-height:1; letter-spacing:6px; }}
  .handle {{ position:absolute; bottom:25px; right:50px; font-size:20px; font-weight:600; color:{ACCENT_HEX}; }}
  .bar {{ position:absolute; left:0; right:0; height:5px; background:{ACCENT_HEX}; z-index:10; }}
  .bar.top {{ top:0; }} .bar.bottom {{ bottom:0; height:4px; }}
</style></head>
<body>
  <div class="bar top"></div>
  <div class="post-image">
    {"<img src='" + post_src + "' />" if post_src else ""}
  </div>
  <div class="countdown-section">
    <div class="number">{days}</div>
    <div class="text-block">
      <span class="days-word">{"DAY" if days == 1 else "DAYS"}</span>
      <span class="to-go">TO GO</span>
    </div>
    <div class="handle">@indian.events.toronto</div>
  </div>
  <div class="bar bottom"></div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════

_STYLE_BUILDERS = {
    "A": _style_a_html,
    "B": _style_b_html,
    "C": _style_c_html,
    "D": _style_d_html,
}


def create_story_image(event: Event, days_left: int, style: str = "C") -> Path:
    """Create a 1080x1920 Instagram Story countdown image.

    Args:
        event: The event to create a story for (must have posted_image_url set).
        days_left: Number of days until the event.
        style: Visual style — "A" (circle), "B" (cinematic), "C" (neon frame), "D" (split).

    Returns:
        Path to the generated PNG file.
    """
    from playwright.sync_api import sync_playwright

    OUTPUT_DIR.mkdir(exist_ok=True)
    font_path = str(FONTS_DIR / "Montserrat.ttf")
    title = clean_title(event.title)
    date_text = event.date.strftime("%A, %B %-d").upper()

    # Download and crop the posted image to get the background
    bg_img = _download_and_crop_posted_image(event.posted_image_url)
    bg_path = _save_bg_image(bg_img)

    # Build HTML
    builder = _STYLE_BUILDERS.get(style.upper(), _style_c_html)
    if style.upper() == "D":
        # Style D needs the full original post image, not the cropped version
        # Download and save the full post image
        original_path = None
        if event.posted_image_url:
            try:
                resp = requests.get(event.posted_image_url, timeout=30, headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
                })
                resp.raise_for_status()
                tmp_orig = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp_orig.write(resp.content)
                tmp_orig.close()
                original_path = tmp_orig.name
            except Exception:
                pass
        html = builder(font_path, bg_path, days_left, title, date_text, original_post_path=original_path)
    else:
        html = builder(font_path, bg_path, days_left, title, date_text)

    # Render with Playwright
    safe_title = "".join(c if c.isalnum() or c in "-_ " else "" for c in event.title)[:50].strip().replace(" ", "_")
    date_str = event.date.strftime("%Y%m%d")
    output_path = OUTPUT_DIR / f"story_{date_str}_{safe_title}_{days_left}d.png"

    tmp_html = tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8")
    tmp_html.write(html)
    tmp_html.close()

    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--allow-file-access-from-files"])
        ctx = browser.new_context(viewport={"width": STORY_W, "height": STORY_H})
        page = ctx.new_page()
        page.goto(f"file://{tmp_html.name}", wait_until="networkidle")
        page.screenshot(path=str(output_path))
        ctx.close()
        browser.close()

    # Cleanup temp files
    Path(tmp_html.name).unlink(missing_ok=True)
    if bg_path:
        Path(bg_path).unlink(missing_ok=True)

    return output_path
