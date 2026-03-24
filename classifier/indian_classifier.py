import json
import os

from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.environ.get("OPENROUTER_API_KEY", ""),
)

MODEL = "google/gemini-2.5-flash-lite"

SYSTEM_PROMPT = """You classify events for @indian.events.toronto, an Instagram account posting Indian events in the Toronto/GTA area.

You have TWO jobs:

## Job 1: Classify
Decide if an event is genuinely "Indian" — meaning it would specifically interest the Indian diaspora.

IMPORTANT: The "Categories" and "Languages" metadata from event listing sites are often WRONG or generic defaults. Do NOT rely on them. Base your decision on the event TITLE, DESCRIPTION, and ORGANIZER — the actual content.

INCLUDE (clearly Indian):
- Bollywood / Bhangra / Indian classical music events
- Indian stand-up comedians (Amit Tandon, Abhishek Upmanyu, Sumukhi Suresh, etc.)
- Indian cultural celebrations (Diwali, Holi, Navratri, Ganesh Chaturthi, etc.)
- Indian dance forms (Bharatanatyam, Garba, Kathak, Bollywood dance)
- Indian fashion shows, mehndi/sangeet nights, sari events
- South Asian speed dating / networking explicitly for Indians/South Asians
- Sufi / Qawwali music (broadly appeals to Indian audience)
- Indian bands/artists touring (SANAM, Arijit Singh, etc.)
- Desi parties, Bollywood nights, "desi night" events
- Events at Indian restaurants/venues with Indian themes

INCLUDE (borderline but yes):
- Pakistani artists performing for a broadly South Asian audience (e.g., Ali Soomro, Atif Aslam)
- Mixed genre events with a strong Bollywood/Indian component (e.g., "Bollywood x Latin")

EXCLUDE (these are HARD rules — never classify as Indian):
- Afghan events (Afghan party nights, Afghan music, Afghan Eid parties) — ALWAYS exclude, even if Eid is shared across cultures. Afghan ≠ Indian.
- Sri Lankan, Nepali, or Bangladeshi community-specific events — unless they have explicit Indian/Bollywood content
- Caribbean / Caribana events — not Indian unless explicitly Indo-Caribbean
- Generic boat parties, club nights, fashion events with NO Indian connection in the title/description
- Victoria Day / Canada Day / holiday parties that just happen to be listed on an Indian site
- Events where the ONLY "Indian" signal is the website it was listed on
- Do NOT rationalize inclusion by saying "appeals to South Asian diaspora" — this account is specifically for INDIAN events, not broadly South Asian

## Job 2: Clean up the event title
Scraped event titles often have formatting issues and redundant info. Return a polished version:
- Remove venue names, city names, and location info that's redundant (we show these separately on the post). E.g. "Afghan Party Night Eid Special Toronto Luna Lounge" → "Afghan Party Night Eid Special", "Bollywood Night at Rebel Toronto" → "Bollywood Night"
- Remove redundant dates/years from titles (e.g. "Diwali Bash 2026 March 22" → "Diwali Bash 2026")
- Fix bad spacing (e.g. "2026Dopamine" → "2026 Dopamine", "Dopamine , Bollywood" → "Dopamine, Bollywood")
- Fix obvious typos/misspellings (e.g. "Bollwood" → "Bollywood")
- Fix missing or wrong apostrophes (e.g. "Canadas" → "Canada's")
- Fix inconsistent capitalization (use Title Case for event names)
- Do NOT change the meaning, artist names you're unsure about, or remove intentional stylization
- If the title looks fine, return it unchanged

Respond with ONLY valid JSON:
{"is_indian": true/false, "reason": "one sentence explanation", "cleaned_title": "polished title"}"""


def classify_event(title: str, description: str, categories: list[str], languages: list[str], organizer: str) -> tuple[bool, str, str]:
    """Classify whether an event is Indian. Returns (is_indian, reason, cleaned_title)."""
    event_info = f"""Event Title: {title}
Description: {description[:500] if description else 'N/A'}
Organizer: {organizer or 'N/A'}"""

    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=250,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": event_info},
        ],
    )

    text = response.choices[0].message.content.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    text = text.strip()

    try:
        result = json.loads(text)
        return result.get("is_indian", False), result.get("reason", ""), result.get("cleaned_title", title)
    except json.JSONDecodeError:
        is_indian = '"is_indian": true' in text.lower() or '"is_indian":true' in text.lower()
        return is_indian, text, title
