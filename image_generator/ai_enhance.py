"""AI-powered image enhancement using Gemini 2.5 Flash via OpenRouter.

Three strategies based on event type:
  - Solo artist (comedian/musician/dj/other): keep the person, replace background
  - Group/party event: enhance crowd/atmosphere, or generate fresh scene
  - Non-performance event: generate aesthetic mood scene from scratch
"""

import base64
import io
import os
from pathlib import Path

import requests
from PIL import Image

CACHE_DIR = Path(__file__).parent.parent / "data" / "image_cache"
MODEL = "google/gemini-2.5-flash-image"


def _autocrop_borders(img: Image.Image, threshold: int = 15) -> Image.Image:
    """Trim near-black or near-white borders that AI models sometimes add."""
    import numpy as np
    arr = np.array(img)
    h, w = img.height, img.width

    # Detect black borders: rows/cols where max brightness is below threshold
    row_max = arr.max(axis=(1, 2))  # shape: (H,)
    col_max = arr.max(axis=(0, 2))  # shape: (W,)
    black_rows = row_max > threshold
    black_cols = col_max > threshold

    # Detect white borders: rows/cols where min brightness is above (255-threshold)
    white_thresh = 255 - threshold
    row_min = arr.min(axis=(1, 2))  # shape: (H,)
    col_min = arr.min(axis=(0, 2))  # shape: (W,)
    white_rows = row_min < white_thresh
    white_cols = col_min < white_thresh

    # A row/col has content if it's not black AND not white
    content_rows = np.where(black_rows & white_rows)[0]
    content_cols = np.where(black_cols & white_cols)[0]

    if len(content_rows) == 0 or len(content_cols) == 0:
        return img  # all uniform or all content, don't crop

    top, bottom = int(content_rows[0]), int(content_rows[-1]) + 1
    left, right = int(content_cols[0]), int(content_cols[-1]) + 1

    # Only crop if we're removing a meaningful border (>2% per side)
    if (top / h > 0.02 or (h - bottom) / h > 0.02 or
            left / w > 0.02 or (w - right) / w > 0.02):
        cropped = img.crop((left, top, right, bottom))
        print(f"    AI autocrop: {w}x{h} -> {cropped.width}x{cropped.height}")
        return cropped
    return img


def _image_to_b64url(img: Image.Image) -> str:
    """Convert PIL Image to base64 data URL for the API."""
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


def _call_openrouter_image(prompt: str, source_img: Image.Image | None = None) -> Image.Image | None:
    """Call OpenRouter image generation API. Returns PIL Image or None."""
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("    AI enhance: no OPENROUTER_API_KEY, skipping")
        return None

    content = []
    if source_img:
        content.append({
            "type": "image_url",
            "image_url": {"url": _image_to_b64url(source_img)},
        })
    content.append({"type": "text", "text": prompt})

    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": content}],
        "modalities": ["image", "text"],
        "image_config": {"aspect_ratio": "5:4", "image_size": "2K"},
    }

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )
        if resp.status_code != 200:
            print(f"    AI enhance error: {resp.status_code} {resp.text[:200]}")
            return None

        result = resp.json()
        images = result.get("choices", [{}])[0].get("message", {}).get("images", [])
        if images:
            url = images[0].get("image_url", {}).get("url", "")
            if url.startswith("data:"):
                _, b64 = url.split(",", 1)
                raw = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
                return _autocrop_borders(raw)

        print("    AI enhance: no image in response")
        return None
    except Exception as e:
        print(f"    AI enhance failed: {e}")
        return None


def _get_ai_cached(cache_key: str) -> Image.Image | None:
    """Return cached AI-enhanced image, or None."""
    path = CACHE_DIR / f"{cache_key}_ai.jpg"
    if path.exists():
        try:
            img = Image.open(path).convert("RGB")
            # Re-autocrop cached images in case they were saved with borders
            cropped = _autocrop_borders(img)
            if cropped.size != img.size:
                _save_ai_cache(cache_key, cropped)
                img = cropped
            print(f"    AI enhance: using cached {img.width}x{img.height}")
            return img
        except Exception:
            path.unlink(missing_ok=True)
    return None


def _save_ai_cache(cache_key: str, img: Image.Image) -> None:
    """Cache an AI-enhanced image."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{cache_key}_ai.jpg"
    img.save(path, "JPEG", quality=95)


# ── Per-type prompt templates ──

_ARTIST_PROMPT = """You are editing a photo to create a professional Instagram event poster image.

Event: "{event_title}"
This is {artist_description}.

FACE PRESERVATION (MOST IMPORTANT):
- Do NOT alter the person's face in ANY way. Preserve the EXACT facial features, eye shape, nose, jawline, skin texture, and expression.
- Do NOT beautify, smooth, reshape, or "improve" the face. Keep every facial detail IDENTICAL to the source photo.
- Preserve the exact same hairstyle, hair color, and facial hair.
- Keep the same pose, body proportions, and outfit.
- If the source face is low resolution, keep it slightly soft rather than inventing new facial details.

BACKGROUND CHANGES ONLY:
1. REMOVE any ugly/cluttered background, watermarks, low-quality elements, text overlays, or visual noise.
2. Replace ONLY the background with a premium, cinematic look: {background_style}.
3. Keep the exact same camera angle, framing, and position of the person.
4. Landscape orientation (5:4 aspect ratio, wider than tall). The background MUST fill the ENTIRE canvas edge-to-edge — NO black bars, borders, or letterboxing.
5. Rich, warm color palette for the background - golds, ambers, deep blacks.
6. Do NOT add any text, titles, dates, or watermarks.
7. Professional lighting with depth — the person should be the clear focal point.

Output ONLY the image, no text."""

_BACKGROUND_STYLES = {
    "comedian": "warm stage lighting with soft bokeh, comedy club atmosphere, spotlight effect",
    "musician": "dramatic concert stage lighting, warm golden spotlights, live music atmosphere",
    "dj": "vibrant club lighting, neon accents, DJ booth atmosphere with dynamic colored lights",
    "other": "elegant stage lighting, warm spotlight, premium event atmosphere",
}

_EVENT_ENHANCE_PROMPT = """You are creating a professional Instagram event poster image.

Here is the source image from an event listing. Enhance it into a stunning, premium-quality image.

REQUIREMENTS:
1. If there's a crowd, performers, or atmosphere in this image - enhance and elevate it.
2. Remove any text overlays, watermarks, dates, venue names, or promotional copy.
3. Make it look cinematic and premium - improve lighting, color grading, depth.
4. Style: {event_style}.
5. Portrait orientation (4:5 aspect ratio).
6. Do NOT add any text.

Output ONLY the image, no text."""

_EVENT_GENERATE_PROMPT = """Create a stunning, photorealistic image for an Instagram event post.

Event: {title}
Style: {event_style}

REQUIREMENTS:
1. Create a vibrant, atmospheric scene that captures the energy of this event.
2. Photorealistic quality - should look like a professional event photograph.
3. Landscape orientation (5:4 aspect ratio, wider than tall).
4. Rich, warm colors. Cinematic lighting.
5. Do NOT include any text, titles, logos, or watermarks.
6. Do NOT show specific recognizable faces - focus on atmosphere, lighting, movement.

Output ONLY the image, no text."""

_SCENE_PROMPT = """Create a beautiful, photorealistic image for an Instagram event post.

Event: {title}
Description: {description}

Create an aesthetic mood scene that captures the feeling of this event:
{scene_guidance}

REQUIREMENTS:
1. Photorealistic, high-quality - should look like a professional photograph.
2. Landscape orientation (5:4 aspect ratio, wider than tall).
3. Warm, inviting color palette. Beautiful lighting.
4. Do NOT include any text, titles, logos, or watermarks.
5. Do NOT show specific recognizable faces - focus on atmosphere and aesthetics.
6. The image should make someone want to attend this event.

Output ONLY the image, no text."""


def _get_event_style(title: str) -> str:
    """Infer a visual style from the event title."""
    t = title.lower()
    if any(w in t for w in ["bollywood", "desi night", "desi party"]):
        return "vibrant Bollywood dance party with colorful lights, energetic crowd silhouettes, festive Indian atmosphere"
    if any(w in t for w in ["sufi", "qawwali", "mehfil"]):
        return "intimate Sufi music gathering with warm candlelight, ornate venue, spiritual atmosphere"
    if any(w in t for w in ["bhangra"]):
        return "energetic Bhangra dance event with vibrant colors, dynamic movement, Punjabi celebration"
    if any(w in t for w in ["party", "night", "after dark"]):
        return "upscale nightlife event with dramatic lighting, energetic atmosphere, premium club feel"
    if any(w in t for w in ["festival", "mela", "holi", "diwali", "navratri"]):
        return "colorful Indian festival celebration with lights, decorations, joyful atmosphere"
    return "premium Indian cultural event with warm lighting and elegant atmosphere"


def _get_scene_guidance(title: str, description: str) -> str:
    """Generate scene guidance for non-performance events."""
    t = (title + " " + description).lower()
    if any(w in t for w in ["speed dating", "dating"]):
        return "An upscale, warmly-lit restaurant or lounge setting. Soft ambient lighting, elegant table arrangements, warm bokeh lights. Sophisticated and inviting social atmosphere. South Asian aesthetic touches."
    if any(w in t for w in ["fashion", "sari", "saree", "nari"]):
        return "Beautiful display of colorful Indian fashion - vibrant silk fabrics, intricate embroidery, rich textures. Elegant runway or boutique atmosphere with dramatic lighting."
    if any(w in t for w in ["holi"]):
        return "Explosion of vibrant colored powder in the air, joyful festival of colors atmosphere, bright and energetic."
    if any(w in t for w in ["diwali"]):
        return "Beautiful display of diyas (oil lamps), warm golden light, rangoli patterns, festive decorations, sparklers."
    if any(w in t for w in ["navratri", "garba", "dandiya"]):
        return "Colorful Garba/Dandiya dance celebration, vibrant traditional outfits, decorated venue with lights."
    if any(w in t for w in ["food", "dinner", "brunch", "culinary"]):
        return "Beautifully plated Indian cuisine, warm restaurant ambiance, rich colors and textures of Indian food."
    if any(w in t for w in ["yoga", "meditation", "wellness"]):
        return "Serene wellness setting with soft natural light, peaceful atmosphere, subtle Indian spiritual elements."
    return "Elegant Indian cultural event setting with warm ambient lighting, rich textures, and inviting atmosphere."


def enhance_artist_image(source_img: Image.Image, performer_type: str, artist_name: str, title: str = "") -> Image.Image | None:
    """Enhance a solo artist image: keep the person, replace background."""
    bg_style = _BACKGROUND_STYLES.get(performer_type, _BACKGROUND_STYLES["other"])
    type_labels = {
        "comedian": "a stand-up comedian",
        "musician": "a musician/singer",
        "dj": "a DJ",
        "other": "a performer",
    }
    type_label = type_labels.get(performer_type, "a performer")
    artist_desc = f"{artist_name}, {type_label}" if artist_name else type_label
    prompt = _ARTIST_PROMPT.format(
        artist_description=artist_desc,
        background_style=bg_style,
        event_title=title,
    )
    print(f"    AI enhance: artist mode ({performer_type})")
    return _call_openrouter_image(prompt, source_img)


def enhance_event_image(source_img: Image.Image | None, title: str) -> Image.Image | None:
    """Enhance or generate an event/party image."""
    style = _get_event_style(title)
    if source_img:
        # Try enhancing the source image
        prompt = _EVENT_ENHANCE_PROMPT.format(event_style=style)
        print(f"    AI enhance: event mode (with source)")
        return _call_openrouter_image(prompt, source_img)
    else:
        prompt = _EVENT_GENERATE_PROMPT.format(title=title, event_style=style)
        print(f"    AI enhance: event mode (generating fresh)")
        return _call_openrouter_image(prompt)


def generate_scene_image(title: str, description: str) -> Image.Image | None:
    """Generate an aesthetic mood scene for non-performance events."""
    guidance = _get_scene_guidance(title, description)
    prompt = _SCENE_PROMPT.format(title=title, description=description[:200], scene_guidance=guidance)
    print(f"    AI enhance: scene mode (no source image)")
    return _call_openrouter_image(prompt)


def enhance_image(
    source_img: Image.Image | None,
    title: str,
    description: str,
    performer_type: str,
    artist_name: str,
    cache_key: str,
) -> Image.Image | None:
    """Main dispatcher — picks the right strategy based on performer type.

    Returns an enhanced/generated PIL Image, or None on failure.
    The caller should fall back to the original image if None is returned.
    """
    # Check cache first
    cached = _get_ai_cached(cache_key)
    if cached:
        return cached

    result = None

    if performer_type in ("comedian", "musician", "dj", "other") and artist_name:
        # Solo artist — enhance with source image
        if source_img:
            result = enhance_artist_image(source_img, performer_type, artist_name, title=title)
        else:
            # No source image for a named artist — generate a scene instead
            result = enhance_event_image(None, title)
    elif performer_type == "event":
        if source_img:
            # Check if source image is a usable photo vs a text flyer
            from image_generator.image_search import has_significant_text
            if has_significant_text(source_img):
                print(f"    AI enhance: source is a text flyer, generating fresh")
                result = enhance_event_image(None, title)
            else:
                result = enhance_event_image(source_img, title)
        else:
            result = generate_scene_image(title, description)
    else:
        # Unknown type — try scene generation
        result = generate_scene_image(title, description)

    if result:
        _save_ai_cache(cache_key, result)
        print(f"    AI enhance: success {result.width}x{result.height}")

    return result
