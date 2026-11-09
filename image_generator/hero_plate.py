"""AI "hero plate": a clean, text-free photo of the real headliner, lit and backed in the
event category's colours, with the bottom third left dark for the poster typography.

The model only ever *edits a real photo of the person* — taken from the organiser's flyer
(where the profile says they are pictured) or from Wikipedia/Wikidata. If no photo of the
headliner exists, no plate is made and the event falls back to a typographic card. We never
ask the model to invent a person.

Model: IMAGE_MODEL env var. Defaults to Flash for development; production workflows set Pro.
"""

import base64
import io
import os
from pathlib import Path

import requests
from PIL import Image

from models import Event

DEFAULT_MODEL = "google/gemini-3.1-flash-image"
CACHE_DIR = Path(__file__).parent.parent / "data" / "image_cache" / "plates"

# Per-category scene direction. Keep backdrops photographic and uncluttered.
SCENES = {
    "garba":     ("deep wine and magenta stage haze with soft out-of-focus warm festival lights",
                  "warm key light from the front-left with a soft magenta rim light"),
    "comedy":    ("a dark comedy-club brick wall, mostly in shadow",
                  "a single hard spotlight from above-front, like a comedy stage"),
    "concert":   ("a dark concert stage with blurred amber and red stage lights",
                  "dramatic warm stage lighting with an orange rim light"),
    "classical": ("a dim auditorium stage with a deep maroon curtain, softly out of focus",
                  "soft warm spotlight, elegant and calm"),
    "qawwali":   ("a dim, deep teal mehfil setting with blurred warm candle-like lights",
                  "soft warm candlelight from one side, intimate and spiritual"),
    "festival":  ("a night sky with soft blurred golden diyas and distant fireworks bokeh, deep indigo",
                  "warm golden key light with a cool indigo rim light"),
    "party":     ("a dark nightclub with blurred neon pink and electric blue lights",
                  "colourful club lighting with a neon rim light"),
    "theatre":   ("a dark theatre stage with a deep plum curtain, softly out of focus",
                  "a soft theatrical spotlight"),
    "community": ("a softly blurred warm, deep green interior",
                  "soft natural key light"),
}

PROMPT = """This image contains a photo of {who} ({role}). It may be an event flyer with other text and graphics.

Create a clean, premium poster photograph of THIS EXACT PERSON for an Instagram event poster.

IDENTITY (most important):
- It must be the same real person. Do NOT change the face: same features, eyes, nose, jaw, skin tone, age, expression, hair and facial hair.
- Keep their outfit, but you may extend it naturally where the image crops it.
- Do not beautify, slim, or de-age them.

REMOVE everything else from the source: all text, logos, dates, prices, QR codes, borders, city skylines, other people, illustrations, frames.

COMPOSITION (portrait 4:5):
- Subject shown from roughly mid-chest up, head in the upper third, centred or slightly right.
- The bottom 35% of the frame must be quiet, dark, out-of-focus background with no subject detail (text will be placed there later).
- Background: {backdrop}. Simple, uncluttered, photographic, not illustrated.
- Lighting: {light}.
- Photorealistic, sharp on the face, natural skin texture.

Do NOT add any text, letters, logos or watermarks. Output only the image."""


def model_name() -> str:
    return os.environ.get("IMAGE_MODEL", DEFAULT_MODEL)


def _cache_path(event: Event) -> Path:
    tag = model_name().split("/")[-1]
    return CACHE_DIR / f"{event.source}_{event.source_id}_{tag}.jpg"


def _download(url: str) -> Image.Image | None:
    try:
        r = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        return Image.open(io.BytesIO(r.content)).convert("RGB")
    except Exception:
        return None


def source_photo(event: Event) -> tuple[Image.Image | None, str]:
    """A real photo of the main headliner: the flyer they're pictured in, else Wikipedia/Wikidata."""
    from classifier.profile import flyer_urls

    heads = (event.profile or {}).get("headliners") or []
    if not heads:
        return None, "no headliner"
    main = heads[0]
    idx = main.get("pictured_in_image")
    urls = flyer_urls(event)
    if isinstance(idx, int) and 0 <= idx < len(urls):
        img = _download(urls[idx])
        if img:
            return img, f"flyer #{idx}"

    from image_generator.artist_image_sources import fetch_wikipedia, fetch_wikidata
    for fn, label in ((fetch_wikipedia, "wikipedia"), (fetch_wikidata, "wikidata")):
        try:
            img = fn(main["name"], performer_type=main.get("role", ""))
        except Exception:
            img = None
        if img:
            return img, label
    return None, "headliner not pictured anywhere"


def make_hero_plate(event: Event) -> Image.Image | None:
    """Return the cached or newly generated plate (1080x1350-ish, 4:5), or None."""
    path = _cache_path(event)
    if path.exists():
        return Image.open(path).convert("RGB")

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("    Hero plate: no OPENROUTER_API_KEY")
        return None

    src, origin = source_photo(event)
    if src is None:
        print(f"    Hero plate: skipped ({origin})")
        return None
    src.thumbnail((1600, 1600))

    profile = event.profile or {}
    main = profile["headliners"][0]
    backdrop, light = SCENES.get(profile.get("category"), SCENES["community"])
    prompt = PROMPT.format(who=main["name"], role=main.get("role", "performer"),
                           backdrop=backdrop, light=light)
    buf = io.BytesIO()
    src.save(buf, "JPEG", quality=92)
    data_url = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()

    print(f"    Hero plate: {model_name()} from {origin}...")
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model_name(),
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": prompt},
                ]}],
                "modalities": ["image", "text"],
                "image_config": {"aspect_ratio": "4:5", "image_size": "2K"},
            },
            timeout=240,
        )
        r.raise_for_status()
        images = r.json()["choices"][0]["message"].get("images") or []
        if not images:
            print("    Hero plate: model returned no image")
            return None
        raw = base64.b64decode(images[0]["image_url"]["url"].split(",", 1)[1])
        plate = Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception as e:
        print(f"    Hero plate failed: {e}")
        return None

    path.parent.mkdir(parents=True, exist_ok=True)
    plate.save(path, "JPEG", quality=93)
    return plate
