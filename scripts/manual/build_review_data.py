import base64, io, json, sqlite3, sys, concurrent.futures as cf
from pathlib import Path
import requests
from PIL import Image
S = Path(sys.argv[1]); OUT = S / "review"
c = sqlite3.connect(S / "live.db")
rows = c.execute("""SELECT source, source_id, title, date, time_str, venue, city, price, event_url, image_url, image_urls,
                           is_indian, classification_reason, tier, score, score_json, profile_json, posted
                    FROM processed_events
                    WHERE date >= date('now') AND date < date('now','+15 days') ORDER BY date""").fetchall()
def b64img(img, w, q=72):
    img = img.convert("RGB"); img.thumbnail((w, w * 2))
    buf = io.BytesIO(); img.save(buf, "JPEG", quality=q, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
def thumb(url):
    if not url: return None
    try:
        r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"}); r.raise_for_status()
        return b64img(Image.open(io.BytesIO(r.content)), 360)
    except Exception:
        return None
def first_img(r):
    urls = [u for u in (r[10] or "").split(",") if u] or ([r[9]] if r[9] else [])
    return urls[0] if urls else None
with cf.ThreadPoolExecutor(8) as ex:
    thumbs = list(ex.map(lambda r: thumb(first_img(r)), rows))
out = []
for r, th in zip(rows, thumbs):
    sj = json.loads(r[15] or "{}"); pj = json.loads(r[16] or "{}")
    card = OUT / "out" / f"{r[3][:10].replace('-', '')}_{r[1]}_card.png"
    out.append(dict(
        id=f"{r[0]}_{r[1]}", source=r[0], title=r[2], date=r[3][:16], time=r[4] or "", venue=r[5] or "",
        city=r[6] or "", price=r[7] or "", url=r[8] or "", indian=bool(r[11]), reason=r[12] or "",
        tier=r[13] or "", score=r[14] or 0, points=sj.get("points", {}), prominence=pj.get("prominence"),
        prominence_reason=pj.get("prominence_reason", ""), category=pj.get("category", ""),
        display=pj.get("display_name", ""), subtitle=pj.get("subtitle", ""), series=pj.get("series"),
        headliners=[h["name"] for h in pj.get("headliners", [])],
        thumb=th, card=b64img(Image.open(card), 420, 70) if card.exists() else None,
    ))
slides = [b64img(Image.open(p), 540, 74) for p in sorted((OUT / "out").glob("roundup_*.png"))]
json.dump({"events": out, "roundup": {"label": "Nov 13–15", "slides": slides}}, open(OUT / "data.json", "w"))
print(len(out), "events,", sum(e["indian"] for e in out), "Indian,", sum(1 for e in out if e["thumb"]), "thumbs,",
      sum(1 for e in out if e["card"]), "cards;", round((OUT / "data.json").stat().st_size / 1e6, 1), "MB")
