"""Publish photos to a Facebook Page via the Graph API."""

import os

import requests

FB_GRAPH_API = "https://graph.facebook.com/v25.0"


def _get_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


def build_fb_caption(event, instagram_handle: str | None = None) -> str:
    """Build a Facebook caption — includes a direct event link (unlike Instagram)."""
    lines = []
    lines.append(event.title)
    if instagram_handle:
        lines.append(f"🎤 @{instagram_handle}")
    lines.append("")
    lines.append(f"📅 {event.date.strftime('%A, %B %-d, %Y')}")
    if event.time_str:
        lines.append(f"🕐 {event.time_str}")
    lines.append(f"📍 {event.venue}")
    if event.city:
        lines.append(f"   {event.city}")
    if event.price:
        lines.append(f"🎟️ {event.price}")
    lines.append("")
    if event.event_url:
        lines.append(f"🔗 Tickets & details: {event.event_url}")
    lines.append("")
    lines.append("#toronto #torontoevents #indianevents #desi #bollywood #desievents #indianeventstoronto #gta #brampton #mississauga")
    return "\n".join(lines)


def publish_to_facebook(image_url: str, caption: str) -> str:
    """
    Publish a photo post to the Facebook Page.

    Takes an already-public image URL (e.g. from freeimage.host) to avoid
    re-uploading the same image that was used for Instagram.

    Returns the Facebook post ID.
    """
    page_id = _get_env("FACEBOOK_PAGE_ID")
    page_token = _get_env("FACEBOOK_PAGE_ACCESS_TOKEN")

    resp = requests.post(
        f"{FB_GRAPH_API}/{page_id}/photos",
        data={
            "url": image_url,
            "caption": caption,
            "access_token": page_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    post_id = resp.json().get("post_id") or resp.json().get("id")
    return post_id
