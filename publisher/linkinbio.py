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
    # Only show upcoming events (date >= today)
    upcoming = [e for e in events if e.date.date() >= now.date()]

    DOCS_DIR.mkdir(exist_ok=True)
    html_content = _build_page(upcoming)
    out = DOCS_DIR / "index.html"
    out.write_text(html_content, encoding="utf-8")
    print(f"  Link-in-bio page generated: {len(upcoming)} events")
    return out


def _build_page(events) -> str:
    event_cards = "\n".join(_event_card(e) for e in events)
    if not event_cards:
        event_cards = '<p class="empty">No upcoming events right now. Check back soon!</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{SITE_TITLE}</title>
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');

* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    font-family: 'Inter', -apple-system, sans-serif;
    background: #0a0a0f;
    color: #e8e8e8;
    min-height: 100vh;
}}

.container {{
    max-width: 480px;
    margin: 0 auto;
    padding: 24px 16px 48px;
}}

.header {{
    text-align: center;
    margin-bottom: 32px;
}}

.header h1 {{
    font-size: 22px;
    font-weight: 700;
    color: #fff;
    margin-bottom: 4px;
}}

.header .handle {{
    color: #FF9933;
    font-size: 14px;
    font-weight: 600;
}}

.header .subtitle {{
    color: #888;
    font-size: 13px;
    margin-top: 8px;
}}

.event-card {{
    display: block;
    background: #16161c;
    border: 1px solid #2a2a35;
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 12px;
    text-decoration: none;
    color: inherit;
    transition: border-color 0.2s, transform 0.1s;
}}

.event-card:hover {{
    border-color: #FF9933;
    transform: translateY(-1px);
}}

.event-card .date {{
    color: #FF9933;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
}}

.event-card .title {{
    font-size: 16px;
    font-weight: 600;
    color: #fff;
    margin-bottom: 8px;
    line-height: 1.3;
}}

.event-card .details {{
    font-size: 13px;
    color: #999;
    line-height: 1.5;
}}

.event-card .details span {{
    display: block;
}}

.event-card .price {{
    display: inline-block;
    margin-top: 8px;
    background: rgba(255, 153, 51, 0.15);
    color: #FF9933;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
}}

.event-card .cta {{
    display: block;
    margin-top: 10px;
    color: #FF9933;
    font-size: 13px;
    font-weight: 600;
}}

.empty {{
    text-align: center;
    color: #666;
    padding: 40px 0;
    font-size: 15px;
}}

.footer {{
    text-align: center;
    margin-top: 32px;
    padding-top: 20px;
    border-top: 1px solid #1a1a24;
    color: #555;
    font-size: 12px;
}}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>{SITE_TITLE}</h1>
        <div class="handle">{HANDLE}</div>
        <div class="subtitle">Upcoming Indian events in Toronto &amp; GTA. Tap to get tickets.</div>
    </div>
    {event_cards}
    <div class="footer">Updated {datetime.now().strftime('%b %-d, %Y')}</div>
</div>
</body>
</html>"""


def _event_card(event) -> str:
    title = html.escape(event.title)
    date_str = event.date.strftime("%A, %B %-d")
    time_str = html.escape(event.time_str) if event.time_str else ""
    venue = html.escape(event.venue)
    city = html.escape(event.city) if event.city else ""
    price = html.escape(event.price) if event.price else ""
    url = html.escape(event.event_url)

    details = f'<span>{venue}</span>'
    if city and city.lower() not in venue.lower():
        details += f'<span>{city}</span>'
    if time_str:
        details = f'<span>{time_str}</span>' + details

    price_tag = f'<span class="price">{price}</span>' if price else ""

    return f"""    <a class="event-card" href="{url}" target="_blank" rel="noopener">
        <div class="date">{date_str}</div>
        <div class="title">{title}</div>
        <div class="details">{details}</div>
        {price_tag}
        <span class="cta">Get Tickets &rarr;</span>
    </a>"""


if __name__ == "__main__":
    generate_linkinbio()
