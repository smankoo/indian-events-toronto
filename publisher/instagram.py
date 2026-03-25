"""Publish images to Instagram via the Graph API (Instagram Business Login flow)."""

import json
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


def publish_post(image_path: Path, caption: str, instagram_handle: str | None = None,
                 instagram_handles: list[str] | None = None) -> tuple[str, str]:
    """
    Publish a single-image post to Instagram.

    If instagram_handles (or instagram_handle) is provided, artists are tagged in the image.
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
    container_data = {
        "image_url": image_url,
        "caption": caption,
        "access_token": access_token,
    }
    handles_to_tag = instagram_handles or ([instagram_handle] if instagram_handle else [])
    if handles_to_tag:
        tags = []
        for idx, h in enumerate(handles_to_tag):
            x = 0.3 + (idx * 0.2)  # spread tags horizontally: 0.3, 0.5, 0.7, ...
            x = min(x, 0.9)
            tags.append({"username": h, "x": x, "y": 0.8})
        container_data["user_tags"] = json.dumps(tags)
    resp = requests.post(
        f"{GRAPH_API}/{ig_user_id}/media",
        data=container_data,
        timeout=30,
    )
    # If user_tags caused an error, retry without them
    if not resp.ok and handles_to_tag:
        print(f"    user_tags rejected, retrying without tags...")
        container_data.pop("user_tags", None)
        resp = requests.post(
            f"{GRAPH_API}/{ig_user_id}/media",
            data=container_data,
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


def publish_story(image_path: Path) -> tuple[str, str]:
    """
    Publish a single image to Instagram Stories.

    Stories auto-expire after 24 hours and do not become Highlights.
    Returns (media_id, public_image_url).
    """
    access_token = _get_env("INSTAGRAM_ACCESS_TOKEN")
    ig_user_id = _get_env("INSTAGRAM_USER_ID")

    # Step 1: Upload image to get a public URL
    print(f"    Uploading story image...")
    image_url = upload_image(image_path)
    print(f"    Public URL: {image_url}")

    # Step 2: Create story media container
    print(f"    Creating Instagram story container...")
    resp = requests.post(
        f"{GRAPH_API}/{ig_user_id}/media",
        data={
            "image_url": image_url,
            "media_type": "STORIES",
            "access_token": access_token,
        },
        timeout=30,
    )
    resp.raise_for_status()
    container_id = resp.json()["id"]
    print(f"    Container ID: {container_id}")

    # Step 3: Poll until container is ready
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
            raise RuntimeError(f"Story container {container_id} failed: {resp.json()}")
        time.sleep(2)
    else:
        raise RuntimeError(f"Story container {container_id} not ready after 60s")

    # Step 4: Publish
    print(f"    Publishing story...")
    resp = requests.post(
        f"{GRAPH_API}/{ig_user_id}/media_publish",
        data={"creation_id": container_id, "access_token": access_token},
        timeout=30,
    )
    resp.raise_for_status()
    media_id = resp.json()["id"]
    print(f"    Story published! Media ID: {media_id}")
    return media_id, image_url


def build_caption(event, instagram_handle: str | None = None,
                  instagram_handles: list[str] | None = None) -> str:
    """Build an Instagram caption from an Event object."""
    lines = []
    lines.append(event.title)
    handles = instagram_handles or ([instagram_handle] if instagram_handle else [])
    if handles:
        lines.append("🎤 " + " ".join(f"@{h}" for h in handles))
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
