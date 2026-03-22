"""Publish images to Instagram via the Graph API (Instagram Business Login flow)."""

import os
import time
import base64
from pathlib import Path

import requests

GRAPH_API = "https://graph.instagram.com/v21.0"
FREEIMAGE_API = "https://freeimage.host/api/1/upload"
FREEIMAGE_KEY = "6d207e02198a847aa98d0a2a901485a5"


def _get_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required env var: {name}")
    return val


def upload_image(image_path: Path) -> str:
    """Upload a local image to freeimage.host and return the public URL."""
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    resp = requests.post(
        FREEIMAGE_API,
        data={"key": FREEIMAGE_KEY, "source": b64, "format": "json"},
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status_code") != 200:
        raise RuntimeError(f"Image upload failed: {data}")
    return data["image"]["url"]


def publish_post(image_path: Path, caption: str) -> tuple[str, str]:
    """
    Publish a single-image post to Instagram.

    Returns (media_id, public_image_url).
    """
    access_token = _get_env("INSTAGRAM_ACCESS_TOKEN")
    ig_user_id = _get_env("INSTAGRAM_USER_ID")

    # Step 1: Upload image to get a public URL
    print(f"    Uploading image...")
    image_url = upload_image(image_path)
    print(f"    Public URL: {image_url}")

    # Step 2: Create media container
    print(f"    Creating Instagram media container...")
    resp = requests.post(
        f"{GRAPH_API}/{ig_user_id}/media",
        data={
            "image_url": image_url,
            "caption": caption,
            "access_token": access_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    container_id = resp.json()["id"]
    print(f"    Container ID: {container_id}")

    # Step 3: Poll until container is ready (or timeout)
    print(f"    Waiting for container to be ready...")
    for attempt in range(30):
        resp = requests.get(
            f"{GRAPH_API}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=15,
        )
        resp.raise_for_status()
        status = resp.json().get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise RuntimeError(f"Container {container_id} failed: {resp.json()}")
        time.sleep(2)
    else:
        raise RuntimeError(f"Container {container_id} not ready after 60s")

    # Step 4: Publish
    print(f"    Publishing post...")
    resp = requests.post(
        f"{GRAPH_API}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=30,
    )
    resp.raise_for_status()
    media_id = resp.json()["id"]
    print(f"    Published! Media ID: {media_id}")
    return media_id, image_url


def build_caption(event) -> str:
    """Build an Instagram caption from an Event object."""
    lines = []
    lines.append(event.title)
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
    lines.append("🔗 Link in bio for tickets & details")
    lines.append("")
    lines.append("#toronto #torontoevents #indianevents #desi #bollywood #torontonightlife #desievents #indianeventstoronto #gta #brampton #mississauga")
    return "\n".join(lines)
