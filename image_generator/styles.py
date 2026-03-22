"""
Post layout contract (all styles share this):

  ┌────────────────────────┐  ← 5px saffron top bar
  │                        │
  │      IMAGE BOX         │  ← IMAGE_BOX_H px, hard boundary
  │  (contain + blur fill) │    image centered, bleeds within box only
  │                        │
  ├────────────────────────┤  ← hard cut, no bleed
  │      EVENT INFO        │  ← solid background
  │                        │
  ├────────────────────────┤
  │  @indian.events.toronto│  ← 50px branding row
  └────────────────────────┘  ← 4px saffron bottom bar
"""

CANVAS_W     = 1080
CANVAS_H     = 1350
IMAGE_BOX_H  = 900
TOP_BAR_H    = 5
BOTTOM_BAR_H = 4
BRANDING_H   = 50
ACCENT_HEX   = "#FF9933"
DARK_BG_HEX  = "#0f0f12"

# Minimum font sizes (px) — must stay legible on a phone screen
MIN_FONT_TITLE   = 52
MIN_FONT_DATE    = 30
MIN_FONT_TIME    = 28
MIN_FONT_VENUE   = 26
MIN_FONT_PRICE   = 28
MIN_FONT_HANDLE  = 22


def _base_html(font_path: str, bg_path: str | None,
               card_css: str, card_inner_html: str) -> str:
    """Shared skeleton — image box is identical for all styles."""
    img_url = f"url('file://{bg_path}')" if bg_path else "none"
    info_h  = CANVAS_H - TOP_BAR_H - IMAGE_BOX_H - BRANDING_H - BOTTOM_BAR_H

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
  @font-face {{
    font-family: 'Montserrat';
    src: url('file://{font_path}');
    font-weight: 100 900;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}

  body {{
    width: {CANVAS_W}px;
    height: {CANVAS_H}px;
    font-family: 'Montserrat', sans-serif;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    background: {DARK_BG_HEX};
  }}

  .top-bar    {{ height:{TOP_BAR_H}px;    background:{ACCENT_HEX}; flex-shrink:0; }}
  .bottom-bar {{ height:{BOTTOM_BAR_H}px; background:{ACCENT_HEX}; flex-shrink:0; }}

  /* ── Image box: hard boundary, nothing escapes ── */
  .image-box {{
    width: {CANVAS_W}px;
    height: {IMAGE_BOX_H}px;
    flex-shrink: 0;
    position: relative;
    overflow: hidden;
    /* Warm gradient fallback when no photo is available */
    background: radial-gradient(ellipse at 60% 40%, #2a1a0a 0%, #12080e 45%, #0a0a10 100%);
  }}

  /* Blurred ambient fill — brightened so it's visible even with dark source images */
  .image-box .blur-bg {{
    position: absolute;
    inset: -60px;
    background-image: {img_url};
    background-size: cover;
    background-position: center;
    filter: blur(40px) brightness(0.55) saturate(1.8);
    z-index: 0;
  }}

  /* Sharp image — fully contained, pushed slightly toward top so
     the bottom gap (and thus blur) is more visible */
  .image-box img {{
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: contain;
    object-position: center 35%;
    z-index: 1;
  }}

  /* Thin separator between image box and card */
  .image-box .separator {{
    position: absolute;
    bottom: 0; left: 0; right: 0;
    height: 1px;
    background: rgba(255,255,255,0.08);
    z-index: 2;
  }}

  /* ── Event info card ── */
  .card {{
    width: {CANVAS_W}px;
    height: {info_h}px;
    flex-shrink: 0;
    overflow: hidden;
    {card_css}
  }}

  /* ── Branding row ── */
  .branding {{
    height: {BRANDING_H}px;
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: flex-end;
    padding: 0 56px;
    background: {DARK_BG_HEX};
  }}
  .handle {{
    font-size: {MIN_FONT_HANDLE}px;
    font-weight: 600;
    color: {ACCENT_HEX};
    letter-spacing: 0.3px;
  }}
</style></head>
<body>
  <div class="top-bar"></div>

  <div class="image-box">
    <div class="blur-bg"></div>
    {"<img src='file://" + bg_path + "' />" if bg_path else ""}
    <div class="separator"></div>
  </div>

  <div class="card">
    {card_inner_html}
  </div>

  <div class="branding">
    <span class="handle">@indian.events.toronto</span>
  </div>
  <div class="bottom-bar"></div>
</body></html>"""


# ══════════════════════════════════════════════════════════════════════════
# STYLE B — Cinematic
# Near-black card, saffron date, outlined price pill, generous whitespace.
# ══════════════════════════════════════════════════════════════════════════
def build_html_B(font_path, bg_path, title, date_text, time_text, venue_text, price_text):
    time_html = ""
    if time_text:
        time_html = (
            f'<span style="color:#666;margin:0 8px;">·</span>'
            f'<span style="color:#aaaacc;font-weight:400">{time_text}</span>'
        )

    price_html = ""
    if price_text:
        price_html = f"""
        <span class="price-pill">{price_text}</span>"""

    card_css = f"""
      background: #0a0a0e;
      padding: 32px 56px 0;
    """

    card_inner = f"""
    <style>
      .title {{
        font-size: {MIN_FONT_TITLE}px;
        font-weight: 800;
        color: #fff;
        line-height: 1.15;
        letter-spacing: -0.8px;
        margin-bottom: 22px;
      }}
      .date-row {{
        display: flex;
        align-items: baseline;
        flex-wrap: wrap;
        margin-bottom: 10px;
        font-size: {MIN_FONT_DATE}px;
      }}
      .date {{
        font-size: {MIN_FONT_DATE}px;
        font-weight: 700;
        color: {ACCENT_HEX};
        letter-spacing: 1px;
      }}
      .venue {{
        font-size: {MIN_FONT_VENUE}px;
        font-weight: 400;
        color: #9090b0;
        margin-bottom: 22px;
        line-height: 1.4;
      }}
      .price-pill {{
        display: inline-block;
        border: 2px solid {ACCENT_HEX};
        color: {ACCENT_HEX};
        font-size: {MIN_FONT_PRICE}px;
        font-weight: 700;
        padding: 8px 26px;
        border-radius: 100px;
        letter-spacing: 0.5px;
      }}
    </style>
    <div class="title">{title}</div>
    <div class="date-row">
      <span class="date">{date_text}</span>
      {time_html}
    </div>
    <div class="venue">{venue_text}</div>
    {price_html}
    """

    return _base_html(font_path, bg_path, card_css, card_inner)


# Keep the router in create_post.py pointing to build_html_B as default
build_html_A = build_html_B   # only B survives
build_html_C = build_html_B
build_html_D = build_html_B
