import json, re, sys, time, requests
sys.path.insert(0, sys.argv[1])
from probe import ld_events, UA
KW = ["bollywood","desi","punjabi","indian","bhangra","garba","diwali","south-asian","hindi","sufi","qawwali",
      "tamil","telugu","gujarati","ghazal","bharatanatyam","kathak","desi-comedy","hindi-comedy","malayalam"]
seen = {}
def add(src, e):
    name = re.sub(r"\s+", " ", str(e.get("name",""))).strip()
    date = str(e.get("startDate",""))[:10]
    loc = e.get("location") or {}
    if isinstance(loc, list): loc = loc[0] if loc else {}
    addr = loc.get("address") or {}
    city = addr.get("addressLocality","") if isinstance(addr, dict) else ""
    key = (re.sub(r"[^a-z0-9]","",name.lower())[:40], date)
    rec = seen.setdefault(key, {"name": name, "date": date, "venue": loc.get("name",""), "city": city,
                                "url": e.get("url",""), "sources": set()})
    rec["sources"].add(src)
for kw in KW:
    for page in (1, 2):
        for src, url in (("eventbrite", f"https://www.eventbrite.ca/d/canada--toronto/{kw}/?page={page}"),
                         ("allevents", f"https://allevents.in/toronto/{kw}" if page == 1 else None)):
            if not url: continue
            try:
                r = requests.get(url, headers=UA, timeout=30)
                for e in ld_events(r.text): add(src, e)
            except Exception as ex:
                print("ERR", url, ex)
            time.sleep(0.7)
import datetime
today = datetime.date.today().isoformat()
up = [v for v in seen.values() if v["date"] >= today]
json.dump([{**v, "sources": sorted(v["sources"])} for v in up], open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
from collections import Counter
print("unique upcoming:", len(up))
print("by source:", Counter(s for v in up for s in v["sources"]))
print("next 30 days:", sum(1 for v in up if v["date"] <= (datetime.date.today()+datetime.timedelta(days=30)).isoformat()))
print("cities:", Counter(v["city"] for v in up).most_common(12))
