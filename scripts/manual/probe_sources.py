import json, re, sys, requests
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
      "Accept-Language": "en-CA,en;q=0.9"}
def ld_events(html):
    out = []
    for m in re.finditer(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try: d = json.loads(m.group(1).strip())
        except Exception: continue
        stack = d if isinstance(d, list) else [d]
        while stack:
            it = stack.pop()
            if isinstance(it, dict):
                t = it.get("@type")
                if t in ("Event", "MusicEvent", "ComedyEvent", "DanceEvent", "SocialEvent", "TheaterEvent", "Festival") or (isinstance(t, list) and "Event" in t):
                    out.append(it)
                for k in ("itemListElement", "item", "@graph", "subEvent"):
                    v = it.get(k)
                    if isinstance(v, list): stack.extend(v)
                    elif isinstance(v, dict): stack.append(v)
            elif isinstance(it, list): stack.extend(it)
    return out
for url in sys.argv[1:]:
    try:
        r = requests.get(url, headers=UA, timeout=30)
    except Exception as e:
        print(f"\n## {url}\n  ERROR {e}"); continue
    ev = ld_events(r.text)
    print(f"\n## {url}\n  HTTP {r.status_code}, {len(r.text)} bytes, {len(ev)} JSON-LD events")
    for e in ev[:12]:
        loc = e.get("location") or {}
        if isinstance(loc, list): loc = loc[0] if loc else {}
        addr = loc.get("address") or {}
        city = addr.get("addressLocality") if isinstance(addr, dict) else str(addr)[:30]
        print(f"   - {str(e.get('startDate',''))[:10]}  {str(e.get('name',''))[:70]}  | {loc.get('name','')[:30]} | {city}")
