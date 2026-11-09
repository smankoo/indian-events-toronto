"""Draft one 'why go' line per event from its listing (LLM), for the feed mock."""
import json, sqlite3, sys, concurrent.futures as cf
import requests

DB, IDS, OUT = sys.argv[1], sys.argv[2].split(","), sys.argv[3]
STYLE = """You write one line for an Instagram roundup by @indian.events.toronto, a curated guide to desi events in the GTA.
The line tells a reader why this event is worth their evening. Rules:
- Max 62 characters. One sentence fragment, no full stop needed.
- Only facts in the listing below. Never invent performers, prices, sell-outs or history.
- Specific beats generic: name the thing that makes it different (the dance form, the 7th anniversary, the live qawwali, free entry, the city's first X).
- Warm, plain, a little wry. No exclamation marks, no emoji, no hype words (ultimate, biggest, epic, must-attend, unforgettable) unless quoted as the organiser's claim.
Return only the line."""




def line(sid):
    r = sqlite3.connect(DB).execute("select title, venue, city, price, description, profile_json from processed_events where source_id=?", (sid,)).fetchone()
    if not r:
        return sid, None
    t, v, city, price, desc, pj = r
    p = json.loads(pj or "{}")
    listing = f"Title: {t}\nVenue: {v}, {city}\nPrice: {price}\nHeadliners: {', '.join(h['name'] for h in p.get('headliners', []))}\nDescription: {(desc or '')[:1500]}"
    resp = requests.post("https://openrouter.ai/api/v1/chat/completions",
                         headers={"Authorization": "Bearer proxy-injected"},
                         json={"model": "google/gemini-3.8-flash", "temperature": 0.4,
                               "messages": [{"role": "system", "content": STYLE}, {"role": "user", "content": listing}]},
                         timeout=60)
    resp.raise_for_status()
    return sid, resp.json()["choices"][0]["message"]["content"].strip().strip('"')


c2 = None
with cf.ThreadPoolExecutor(6) as ex:
    res = dict(ex.map(line, IDS))
json.dump(res, open(OUT, "w"), ensure_ascii=False, indent=1)
for k, v in res.items():
    print(k, "|", v)
