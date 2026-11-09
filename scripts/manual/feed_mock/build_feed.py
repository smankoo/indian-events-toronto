"""Render the feed mock: 12 posts (newest first) + 2 story frames, and write feed.json."""
import io, json, sqlite3, sys
from datetime import datetime
from pathlib import Path

import requests
from PIL import Image

S = Path(sys.argv[1]); F = S / "feed"; OUT = F / "out"; OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(F))
import templates as T

LIVE, HIST = sqlite3.connect(S / "live.db"), sqlite3.connect(S / "dev_events.db")
WHY = {**json.load(open(F / "why_hist.json")), **json.load(open(F / "why.json"))}
WHY.update({  # editor pass on the LLM drafts
    "2003345577551": "Diwali edition of a long-running Bollywood night",
    "401091": "Rohan Joshi's new hour, Getting There",
    "2003549153452": "Tamil and English stand-up about IT life",
})
_thumbs = {}
GTA_OUT = {"kitchener", "cambridge", "niagara falls", "guelph", "waterloo"}


def thumb(url):
    if not url:
        return None
    if url not in _thumbs:
        try:
            r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"}); r.raise_for_status()
            _thumbs[url] = Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception:
            _thumbs[url] = None
    return _thumbs[url]


def item(sid, db=LIVE, pick=False, name=None, why=None):
    r = db.execute("select title,date,time_str,venue,city,price,image_url,image_urls,profile_json from processed_events where source_id=?", (sid,)).fetchone()
    t, d, tm, v, c, pr, iu, ius, pj = r
    p = json.loads(pj or "{}")
    urls = [u for u in (ius or "").split(",") if u] or [iu]
    try:
        price = "FREE" if float((pr or "x").replace("CAD", "").strip()) == 0 else f"${float(pr.replace('CAD', '').strip()):.0f}"
    except ValueError:
        price = ""
    dt = datetime.fromisoformat(d)
    return dict(name=name or p.get("display_name") or t, sub=p.get("subtitle", ""), why=why if why is not None else WHY.get(sid, ""),
                date=dt, time=dt.strftime("%-I:%M %p").replace(":00", ""), venue=v, city=c, price=price,
                cat=p.get("category", "community"), thumb=thumb(urls[0]), pick=pick)


def save(img, name):
    path = OUT / f"{name}.jpg"
    img.convert("RGB").save(path, quality=88)
    return path.name


posts = []

# 1 ─ This weekend Nov 13–15 ─────────────────────────────────────────────────
afro = item("200030838146744", pick=True, name="AfroBollywood: 7 Years")
afro["venue"] = "815 Queen St W"
wk = [afro,
      item("2004405067514", pick=True, name="Qawwali Night & Dinner"),
      item("2003516232986", pick=True, name="Bharatanatyam for Diwali"),
      item("2003345577551", name="Bombay Nights: Diwali Edition"),
      item("100002004499154932", name="Diwali Hangover"),
      item("1981446814762", name="All Indian Comedy Show"),
      item("1996242177089", name="BSO Diwali Dhamaka Gala"),
      item("2003583714826", name="Kaapi & Kandeel")]
posts.append(dict(id="weekend-nov13", kind="This weekend", posted="Thu Nov 12", slides=[
    save(T.weekend_cover("NOV 13–15", wk, len(wk)), "p1_0"),
    save(T.list_slide("NOV 13–15 · OUR PICKS", wk[:4]), "p1_1"),
    save(T.list_slide("NOV 13–15 · ALSO GOOD", wk[4:]), "p1_2")],
    caption="""Your desi weekend, Nov 13–15 🪔

Diwali's still going. Our three picks:
• AfroBollywood turns 7 — Afro and South Asian sounds, Sat at 815 Queen W
• Live qawwali with dinner at Matka Biryani House, Sun in Mississauga
• Free Bharatanatyam for Diwali at Courtneypark Library, Sat afternoon (bring the kids)

Plus Bombay Nights' Diwali edition, Bollywood Pulse at Nomad, the All Indian Comedy Show and more. Swipe for all 8 →

Tickets for everything: link in bio. Save this for Friday.
#torontoevents #desitoronto #diwali2026"""))

# 2 ─ Alert: Prateek Kuhad, this Monday (text alert; no licensed photo yet) ──
posts.append(dict(id="alert-prateek", kind="Alert", posted="Wed Nov 11", slides=[
    save(T.alert_text("THIS MONDAY", "Prateek Kuhad", "First Toronto show since 2022", "MON NOV 16 · 8 PM", "Massey Hall",
                      "TICKETS · LINK IN BIO", tint="#1b5e45"), "p2_0")],
    caption="""Prateek Kuhad plays Massey Hall this Monday, Nov 16 — his first Toronto show since 2022.

If cold/mess has been on repeat since 2019, this is the room to hear it in. Doors 7, show 8.

Tickets: link in bio.
#prateekkuhad #masseyhall #torontoconcerts"""))

# 3 ─ Alert: Jubin Nautiyal (photo alert) ───────────────────────────────────
posts.append(dict(id="alert-jubin", kind="Alert", posted="Mon Nov 9", slides=[
    save(T.alert(Image.open(F / "src" / "jubin_allevents.jpg"), "TICKETS ON SALE", "Jubin Nautiyal", "Live in concert",
                 "SUN NOV 29 · 8 PM", "The Theatre at Great Canadian, Etobicoke", "TICKETS · LINK IN BIO"), "p3_0")],
    caption="""Jubin Nautiyal is coming to Toronto 🎤

Sun Nov 29, 8 PM · The Theatre at Great Canadian, Etobicoke
The voice behind Raataan Lambiyan, live — his first GTA show since 2023.

Tickets are on sale now: link in bio. Tag who you're taking.
#jubinnautiyal #torontoconcerts #bollywood"""))

# 4 ─ Guide: desi comedy ─────────────────────────────────────────────────────
com_big = [item("401091", name="Rohan Joshi: Getting There"), item("402337", name="Vikas Kush Sharma: Halki Halki Fati!"),
           item("401897", name="Karunesh Talwar Live")]
vir = dict(name="Vir Das: I Say We Run", date=datetime(2027, 1, 16, 19), time="7 PM", venue="Meridian Hall", city="Toronto",
           price="", cat="comedy", why="")
com_reg = [item("1981446816768", name="All Indian Comedy Show (monthly)"), item("2003684881418", name="Mauj & Masti Vol 21"),
           item("2003479457991", name="Maple Machi's Tamil Stand-Up"), item("2003549153452", name="Tanglish Nights 2.0"),
           item("2004466826236", name="Tadka Comedy (Hindi/Urdu)"), item("2004206307016", name="Sanskari Comedy")]
fmt = lambda x: x["date"].strftime("%a %b %-d").upper()
cg_bg, cg_ink, cg_acc, cg_sub = "#ffd400", "#111111", "#111111", "#4d4300"
posts.append(dict(id="guide-comedy", kind="Guide", posted="Sun Nov 8", slides=[
    save(T.guide_cover("GUIDE · STAND-UP", "Desi comedy season", "Who's in town, Nov to Jan", "4 big names · 6 regular nights",
                       cg_bg, cg_ink, cg_acc, 1), "p4_0"),
    save(T.guide_list("THE BIG NAMES", [(fmt(x), [x]) for x in com_big + [vir]], cg_bg, cg_ink, cg_acc, cg_sub), "p4_1"),
    save(T.guide_list("REGULAR NIGHTS", [(fmt(x), [x]) for x in com_reg], cg_bg, cg_ink, cg_acc, cg_sub), "p4_2")],
    caption="""Desi comedy season is here 🎤

The big names: Rohan Joshi (Nov 29), Vikas Kush Sharma (Dec 6), Karunesh Talwar (Dec 20) and Vir Das at Meridian Hall (Jan 16).

And the rooms where the next ones are coming up — the monthly All Indian Comedy Show at Key's, Mauj & Masti, Tamil stand-up from Maple Machi's and Tanglish Nights, Hindi/Urdu nights in Mississauga.

Save this. Tickets: link in bio.
#desicomedy #torontocomedy"""))

# 5 ─ Coming up: big shows to book ───────────────────────────────────────────
jubin = item("210001986315233", name="Jubin Nautiyal")
jubin["venue"] = "The Theatre at Great Canadian"
prateek = dict(name="Prateek Kuhad", date=datetime(2026, 11, 16, 20), time="8 PM", venue="Massey Hall", city="Toronto",
               price="", cat="concert", why="First Toronto show since 2022", thumb=None)
cu = [prateek, jubin, com_big[0], com_big[2], item("100002004410352321", name="Tashan: The Finale"), dict(vir, why="The I Say We Run tour", thumb=None)]
posts.append(dict(id="coming-up", kind="Coming up", posted="Sun Nov 1", slides=[
    save(T.coming_cover("NOV–JAN", cu), "p5_0"),
    save(T.list_slide("BIG SHOWS · BOOK NOW", cu[:3], show_dow=False), "p5_1"),
    save(T.list_slide("BIG SHOWS · BOOK NOW", cu[3:], show_dow=False), "p5_2")],
    caption="""The big desi shows coming to Toronto, Nov to Jan — book these before they sell out 🎟️

Nov 16 · Prateek Kuhad, Massey Hall
Nov 29 · Jubin Nautiyal, Great Canadian
Nov 29 · Rohan Joshi, Isabel Bader
Dec 20 · Karunesh Talwar, Isabel Bader
Dec 26 · Tashan: The Finale, Phoenix
Jan 16 · Vir Das, Meridian Hall

Save this post. We'll post again when anything new is announced.
#torontoconcerts #desitoronto"""))

# 6 ─ Alert: Vir Das ─────────────────────────────────────────────────────────
posts.append(dict(id="alert-virdas", kind="Alert", posted="Fri Oct 30", slides=[
    save(T.alert_text("ON SALE NOW", "Vir Das", "I Say We Run — world tour", "SAT JAN 16, 2027 · 7 PM", "Meridian Hall",
                      "TICKETS · LINK IN BIO", tint="#7a5a00"), "p6_0")],
    caption="""Vir Das is bringing I Say We Run to Meridian Hall 🎤

Sat Jan 16, 2027 · 7 PM. Tickets are on sale now — link in bio.
#virdas #torontocomedy"""))

# 7 ─ Feature: Karunesh Talwar ───────────────────────────────────────────────
R = Path("/home/user/indian-events-toronto/output")
posts.append(dict(id="feature-karunesh", kind="Feature", posted="Wed Oct 28", slides=[save(Image.open(R / "20261220_401897_headliner.png"), "p7_0")],
    caption="""Karunesh Talwar, live at Isabel Bader Theatre 🎤

Sun Dec 20, 7 PM. One of the sharpest voices in Indian stand-up, back in Toronto with a new hour.

Tickets from $40: link in bio.
#karuneshtalwar #torontocomedy"""))

# 8 ─ This weekend Oct 24–25 (Diwali) ────────────────────────────────────────
dw = [item("401967", HIST, pick=True, name="Malaika Arora at Diwali Festival of Lights"),
      item("400574", HIST, pick=True, name="Kinjal Dave: Post-Navratri Garba"),
      item("401456", HIST, name="Harmeet Singh Kohli: Family Remote"),
      item("402468", HIST, name="Diwali Dhamaka Season 5")]
posts.append(dict(id="weekend-oct24", kind="This weekend", posted="Thu Oct 22", slides=[
    save(T.weekend_cover("OCT 24–25", dw, len(dw)), "p8_0"),
    save(T.list_slide("OCT 24–25 · OUR PICKS", dw), "p8_1")],
    caption="""Diwali weekend in the GTA, Oct 24–25 🪔

• Malaika Arora at the Diwali Festival of Lights — free, Nathan Phillips Square, Sat & Sun
• Kinjal Dave's post-Navratri garba at Enercare Centre, Sat
• Harmeet Singh Kohli's family stand-up, Sat in Mississauga
• Diwali Dhamaka Season 5, free, in Brampton

Swipe for details. Tickets: link in bio.
#diwali2026 #torontoevents"""))

# 9 ─ Feature: Malaika Arora ─────────────────────────────────────────────────
posts.append(dict(id="feature-malaika", kind="Feature", posted="Thu Oct 15", slides=[save(Image.open(R / "20261024_401967_headliner.png"), "p9_0")],
    caption="""Malaika Arora headlines the Diwali Festival of Lights at Nathan Phillips Square ✨

Sat Oct 24 & Sun Oct 25, from noon. Free entry.
#diwali2026 #nathanphillipssquare"""))

# 10 ─ Guide: Diwali in the GTA ──────────────────────────────────────────────
dg = [item("401967", HIST, name="Diwali Festival of Lights (free)"), item("402468", HIST, name="Diwali Dhamaka Season 5 (free)"),
      item("402511", HIST, name="Diwali Gala: Light It Up"),
      item("100002004499154932", name="Diwali Hangover by Bollywood Pulse"), item("2003345577551", name="Bombay Nights: Diwali Edition"),
      item("2003516232986", name="Bharatanatyam for Diwali (free)"), item("1996242177089", name="BSO Diwali Dhamaka Gala"),
      item("2003583714826", name="Kaapi & Kandeel craft social")]
dbg, dink, dacc, dsub = "#3a0d12", "#fff1dc", "#ffb627", "#e3c9a8"
posts.append(dict(id="guide-diwali", kind="Guide", posted="Mon Oct 5", slides=[
    save(T.guide_cover("GUIDE · FESTIVAL", "Diwali 2026 in the GTA", "Melas, galas, parties and puja-ready plans", f"{len(dg)} celebrations · Oct 24 to Nov 15",
                       dbg, dink, dacc, 0), "p10_0"),
    save(T.guide_list("DIWALI 2026 · PART 1", [(fmt(x), [x]) for x in dg[:5]], dbg, dink, dacc, dsub), "p10_1"),
    save(T.guide_list("DIWALI 2026 · PART 2", [(fmt(x), [x]) for x in dg[5:]], dbg, dink, dacc, dsub), "p10_2")],
    caption="""Every Diwali celebration in the GTA, in one post 🪔

From Malaika Arora at City Hall to free Bharatanatyam in Mississauga and the after-parties. Swipe, save, and send to the group chat.
#diwali2026 #torontodiwali"""))

# 11 ─ Feature: Falguni Pathak ───────────────────────────────────────────────
posts.append(dict(id="feature-falguni", kind="Feature", posted="Tue Aug 25", slides=[save(Image.open(R / "20260905_400142_headliner.png"), "p11_0")],
    caption="""The Dandiya Queen is coming 💃

Falguni Pathak, Dandiya Dhoom 2026 — Sat Sep 5, Pearson Convention Centre, Brampton. Tickets from $45: link in bio.
#falgunipathak #garba #dandiya"""))

# 12 ─ Guide: garba season ───────────────────────────────────────────────────
garba_ids = ["400571", "400142", "400573", "400551", "400570", "401136", "400057", "400549", "401139", "400982",
             "401557", "400550", "402063", "400971", "401216", "400337", "400574"]
gi = [item(x, HIST) for x in garba_ids]
for g in gi:
    g["name"] = g["name"] if len(g["name"]) < 34 else g["name"][:33] + "…"
gbg, gink, gacc, gsub = "#5c0a35", "#fff4e0", "#ffc23d", "#f2c6d8"
chunks = [gi[:6], gi[6:12], gi[12:]]
posts.append(dict(id="guide-garba", kind="Guide", posted="Thu Aug 20", slides=[
    save(T.guide_cover("GUIDE · GARBA SEASON", "Garba season 2026", "Every garba & dandiya night in the GTA", f"{len(gi)} nights · Sep 4 to Oct 24",
                       gbg, gink, gacc, 2), "p12_0")] + [
    save(T.guide_list(f"GARBA 2026 · {i + 1} OF {len(chunks)}", [(fmt(x), [x]) for x in ch], gbg, gink, gacc, gsub), f"p12_{i + 1}")
    for i, ch in enumerate(chunks)],
    caption="""Garba season 2026: every garba and dandiya night in the GTA 💃

Falguni Pathak, Kinjal Dave, Geeta Rabari, Kirtidan Gadhvi, Atul Purohit and more — plus the $10 community nights. Save this; we'll keep it updated in our Garba highlight.
#garba #navratri2026 #dandiya"""))

# Stories
stories = [save(T.story_countdown(Image.open(F / "src" / "jubin_allevents.jpg"), 3, "Jubin Nautiyal", "SUN NOV 29 · 8 PM", "The Theatre at Great Canadian"), "s1")]

json.dump({"posts": posts, "stories": stories}, open(F / "feed.json", "w"), ensure_ascii=False, indent=1, default=str)
print(len(posts), "posts;", sum(len(p["slides"]) for p in posts), "slides")
