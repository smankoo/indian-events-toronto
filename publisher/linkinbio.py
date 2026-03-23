"""Generate a link-in-bio page listing posted events with ticket links."""

import html
from datetime import datetime
from pathlib import Path

from data.store import get_posted_events

DOCS_DIR = Path(__file__).parent.parent / "docs"
SITE_TITLE = "Indian Events Toronto"
HANDLE = "@indian.events.toronto"


def generate_linkinbio():
    """Generate a static link-in-bio page from posted events."""
    events = get_posted_events()
    now = datetime.now()
    # Only show upcoming events, most recent post first
    upcoming = [e for e in events if e.date.date() >= now.date()]
    upcoming.reverse()

    DOCS_DIR.mkdir(exist_ok=True)
    html_content = _build_page(upcoming)
    out = DOCS_DIR / "index.html"
    out.write_text(html_content, encoding="utf-8")
    print(f"  Link-in-bio page generated: {len(upcoming)} events")
    return out


def _build_page(events) -> str:
    event_cards = "\n".join(_event_card(e) for e in events)
    if not event_cards:
        event_cards = '<p class="empty">No upcoming events right now.<br>Check back soon!</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0a0a0f">
<title>{SITE_TITLE}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    font-family: 'Inter', -apple-system, sans-serif;
    background: #0a0a0f;
    color: #e8e8e8;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
}}

.container {{
    max-width: 440px;
    margin: 0 auto;
    padding: 32px 16px 64px;
}}

/* ── Header ── */
.header {{
    text-align: center;
    margin-bottom: 28px;
}}

.avatar {{
    width: 72px;
    height: 72px;
    border-radius: 50%;
    border: 2px solid #FF9933;
    margin: 0 auto 12px;
    display: block;
    object-fit: cover;
}}

.header h1 {{
    font-size: 18px;
    font-weight: 700;
    color: #fff;
    letter-spacing: -0.3px;
}}

.header .handle {{
    color: #FF9933;
    font-size: 13px;
    font-weight: 600;
    margin-top: 2px;
}}

.header .tagline {{
    color: #777;
    font-size: 12px;
    margin-top: 8px;
    line-height: 1.4;
}}

/* ── Grid of event images ── */
.grid {{
    display: flex;
    flex-direction: column;
    gap: 14px;
}}

.card {{
    display: block;
    position: relative;
    border-radius: 14px;
    overflow: hidden;
    text-decoration: none;
    transition: transform 0.15s ease;
    box-shadow: 0 2px 12px rgba(0,0,0,0.4);
}}

.card:active {{
    transform: scale(0.98);
}}

.card img {{
    width: 100%;
    display: block;
    aspect-ratio: 4/5;
    object-fit: cover;
}}

/* Gradient overlay at bottom of image for the CTA */
.card .overlay {{
    position: absolute;
    bottom: 0;
    left: 0;
    right: 0;
    padding: 32px 16px 14px;
    background: linear-gradient(transparent, rgba(0,0,0,0.85));
    display: flex;
    align-items: center;
    justify-content: space-between;
}}

.card .overlay .cta {{
    color: #FF9933;
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 0.3px;
    text-transform: uppercase;
}}

.card .overlay .arrow {{
    color: #FF9933;
    font-size: 18px;
    font-weight: 700;
}}

/* Cards without images — text-only fallback */
.card-text {{
    display: block;
    background: #16161c;
    border: 1px solid #2a2a35;
    border-radius: 14px;
    padding: 20px;
    text-decoration: none;
    color: inherit;
    transition: border-color 0.2s;
}}

.card-text:hover {{
    border-color: #FF9933;
}}

.card-text .title {{
    font-size: 16px;
    font-weight: 600;
    color: #fff;
    margin-bottom: 6px;
}}

.card-text .meta {{
    font-size: 12px;
    color: #FF9933;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.3px;
    margin-bottom: 4px;
}}

.card-text .venue {{
    font-size: 13px;
    color: #888;
}}

.card-text .cta {{
    margin-top: 10px;
    color: #FF9933;
    font-size: 13px;
    font-weight: 700;
}}

/* ── Empty state ── */
.empty {{
    text-align: center;
    color: #555;
    padding: 48px 0;
    font-size: 14px;
    line-height: 1.6;
}}

/* ── Footer ── */
.footer {{
    text-align: center;
    margin-top: 40px;
    color: #333;
    font-size: 11px;
}}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🎶 {SITE_TITLE}</h1>
        <div class="handle">{HANDLE}</div>
        <div class="tagline">Tap any event to get tickets</div>
    </div>
    <div class="grid">
        {event_cards}
    </div>
    <div class="footer">{datetime.now().strftime('%b %-d, %Y')}</div>
</div>
</body>
</html>"""


def _event_card(event) -> str:
    title = html.escape(event.title)
    url = html.escape(event.event_url)
    poster_url = html.escape(event.posted_image_url) if event.posted_image_url else ""

    # If we have a poster image, show it as the full card
    if poster_url:
        return f"""    <a class="card" href="{url}" target="_blank" rel="noopener">
        <img src="{poster_url}" alt="{title}" loading="lazy">
        <div class="overlay">
            <span class="cta">Get Tickets</span>
            <span class="arrow">&rarr;</span>
        </div>
    </a>"""

    # Fallback: text-only card when no image
    date_str = event.date.strftime("%a, %b %-d")
    venue = html.escape(event.venue)
    return f"""    <a class="card-text" href="{url}" target="_blank" rel="noopener">
        <div class="meta">{date_str}</div>
        <div class="title">{title}</div>
        <div class="venue">{venue}</div>
        <div class="cta">Get Tickets &rarr;</div>
    </a>"""


if __name__ == "__main__":
    generate_linkinbio()
