"""Feed-mock templates, one per content pillar. Scratch: ported to image_generator/ once approved.

Every function takes plain dicts (no DB) and returns a PIL image 1080x1350.
Item dict keys: name, sub, why, date (datetime), time, venue, city, price, cat, thumb (PIL|None), pick(bool)
"""
import sys
sys.path.insert(0, "/home/user/indian-events-toronto")

from PIL import Image, ImageDraw

from image_generator.design import (
    W, H, cover, ellipsize, fade_to, fit, fit_block, font, grain, handle, hexc, palette,
    tracked, wrap,
)

SAFFRON = "#ff7a1a"
INK = "#16110c"
PAPER = "#f3ede2"
NIGHT = "#0e0c10"
INDIGO = "#141033"


def _dl(dt):
    return {"dow": dt.strftime("%a").upper(), "day": str(dt.day), "mon": dt.strftime("%b").upper()}


def _price(p):
    return p or ""


# ── ALERT: just announced / on sale / last tickets ─────────────────────────
def alert(photo, kicker, name, sub, when, venue, cta):
    img = Image.new("RGB", (W, H), hexc(NIGHT))
    ph = cover(photo, W, 860, ay=0.18)
    ph = grain(ph, 6)
    ph = fade_to(ph, NIGHT, 520, 860)
    img.paste(ph, (0, 110))
    d = ImageDraw.Draw(img)
    # signature saffron band
    d.rectangle([0, 0, W, 110], fill=hexc(SAFFRON))
    tracked(d, (60, 56), kicker, font("anton", 64), NIGHT, track=3, anchor="lm")
    tracked(d, (W - 60, 56), "TORONTO", font("inter-black", 26), NIGHT, track=6, anchor="rm")
    f, lines = fit_block(name.upper(), "anton", W - 120, max_lines=2, max_size=200, min_size=90)
    lh = int(f.size * 0.96)
    y = 1000 - lh * (len(lines) - 1)
    for ln in lines:
        d.text((54, y), ln, font=f, fill="#ffffff", anchor="ls")
        y += lh
    if sub:
        d.text((60, 1058), sub, font=fit(sub, "inter-semibold", W - 120, 40, 28), fill=hexc(SAFFRON), anchor="ls")
    d.line([(60, 1100), (W - 60, 1100)], fill=hexc("#3a3330"), width=2)
    d.text((60, 1160), when, font=fit(when, "anton", W - 120, 70, 44), fill="#ffffff", anchor="lm")
    d.text((60, 1226), venue, font=fit(venue, "inter-medium", W - 120, 36, 26), fill="#d8d0c8", anchor="lm")
    cf = font("inter-black", 28)
    cw = cf.getlength(cta) + 56
    d.rounded_rectangle([60, 1262, 60 + cw, 1316], radius=27, fill=hexc(SAFFRON))
    d.text((60 + cw / 2, 1289), cta, font=cf, fill=NIGHT, anchor="mm")
    handle(d, "#8a8299", x=W - 60, y=1289, anchor="rm")
    return img


# ── THIS WEEKEND: cover + list slides ──────────────────────────────────────
def weekend_cover(label, picks, total):
    img = Image.new("RGB", (W, H), hexc(PAPER))
    d = ImageDraw.Draw(img)
    tracked(d, (64, 90), "THIS WEEKEND IN THE GTA", font("inter-black", 28), INK, track=6, anchor="lm")
    d.rectangle([64, 120, 64 + 120, 128], fill=hexc(SAFFRON))
    hf = fit(label, "anton", W - 128, 300, 150)
    d.text((56, 440), label, font=hf, fill=INK, anchor="ls")
    tracked(d, (64, 530), "OUR PICKS", font("inter-bold", 24), "#8a7f70", track=5, anchor="lm")
    y = 600
    for it in picks[:4]:
        p = palette(it["cat"], it["name"])
        d.ellipse([64, y - 12, 88, y + 12], fill=hexc(p["bg"] if it["cat"] != "comedy" else "#e0b800"))
        nf = fit(it["name"], "serif", W - 230, 64, 40)
        d.text((112, y), ellipsize(it["name"], nf, W - 230), font=nf, fill=INK, anchor="lm")
        meta = f"{_dl(it['date'])['dow']} · {it['venue']}"
        d.text((112, y + 50), ellipsize(meta, font("inter-medium", 28), W - 200), font=font("inter-medium", 28), fill="#5a4f45", anchor="lm")
        y += 130
    more = total - min(4, len(picks))
    pill = f"+ {more} MORE · SWIPE" if more > 0 else "SWIPE"
    pf = font("inter-black", 28)
    pw = pf.getlength(pill) + 60
    d.rounded_rectangle([64, 1200, 64 + pw, 1264], radius=32, fill=hexc(INK))
    d.text((64 + pw / 2, 1232), pill, font=pf, fill=PAPER, anchor="mm")
    handle(d, "#8a7f70", x=W - 64, y=1232, anchor="rm")
    return img


def list_slide(heading, items, accent=SAFFRON, bg=PAPER, ink=INK, sub_ink="#5a4f45", rule="#d6cdbd", per=4, show_dow=True):
    img = Image.new("RGB", (W, H), hexc(bg))
    d = ImageDraw.Draw(img)
    M = 56
    tracked(d, (M, 76), heading, font("inter-black", 26), ink, track=5, anchor="lm")
    d.rectangle([M, 102, M + 90, 108], fill=hexc(accent))
    y, rh = 136, 286
    for it in items[:per]:
        p = palette(it["cat"], it["name"])
        tx = M
        if it.get("thumb") is not None:
            img.paste(cover(it["thumb"], 200, 250, ay=0.2), (M, y + 14))
            tx = M + 228
        else:
            d.rectangle([M, y + 14, M + 200, y + 264], fill=hexc(p["bg"]))
            dd = _dl(it["date"])
            d.text((M + 100, y + 120), dd["day"], font=font("anton", 110), fill=hexc(p["ink"]), anchor="mm")
            d.text((M + 100, y + 200), dd["mon"], font=font("inter-black", 30), fill=hexc(p["ink"]), anchor="mm")
            tx = M + 228
        wmax = W - tx - M
        lab = p["label"]
        lab_col = "#9a7d00" if it["cat"] == "comedy" else (p["bg"] if p["bg"] not in ("#111111",) else "#555555")
        tracked(d, (tx, y + 36), lab, font("inter-bold", 19), hexc(lab_col) if bg == PAPER else hexc(accent), track=4, anchor="lm")
        if it.get("pick"):
            d.text((W - M, y + 36), "OUR PICK", font=font("inter-black", 20), fill=hexc("#c2185b") if bg == PAPER else hexc(accent), anchor="rm")
        nf = font("inter-black", 36)
        lines = wrap(it["name"], nf, wmax)
        if len(lines) > 2:
            lines = [lines[0], ellipsize(" ".join(lines[1:]), nf, wmax)]
        ly = y + 82
        for ln in lines:
            d.text((tx, ly), ln, font=nf, fill=ink, anchor="lm")
            ly += 42
        if it.get("why"):
            wf = font("inter-medium", 27)
            wl = wrap(it["why"], wf, wmax)[:2]
            for ln in wl:
                d.text((tx, ly + 4), ln, font=wf, fill=sub_ink, anchor="lm")
                ly += 33
        dd = _dl(it["date"])
        when = (f"{dd['dow']} {dd['day']} {dd['mon']}" if show_dow else f"{dd['day']} {dd['mon']}") + (f" · {it['time']}" if it.get("time") else "")
        where = ", ".join(x for x in (it["venue"], it.get("city")) if x)
        mf = font("inter-semibold", 26)
        line = when + "  ·  " + where
        d.text((tx, y + 250), ellipsize(line, mf, wmax - 90), font=mf, fill=ink, anchor="lm")
        if it.get("price"):
            d.text((W - M, y + 250), it["price"], font=font("inter-black", 26), fill=ink, anchor="rm")
        y += rh
        d.line([(M, y + 4), (W - M, y + 4)], fill=hexc(rule), width=2)
    d.text((M, H - 50), "Tickets & links: link in bio", font=font("inter-semibold", 26), fill=hexc(sub_ink), anchor="lm")
    handle(d, hexc(sub_ink), x=W - M, y=H - 50, anchor="rm")
    return img


# ── COMING UP: big shows to book ───────────────────────────────────────────
def coming_cover(range_label, items):
    img = Image.new("RGB", (W, H), hexc(INDIGO))
    d = ImageDraw.Draw(img)
    tracked(d, (64, 90), f"COMING UP · {range_label}", font("inter-black", 28), hexc(SAFFRON), track=6, anchor="lm")
    d.text((58, 300), "BIG SHOWS", font=font("anton", 190), fill="#ffffff", anchor="ls")
    d.text((58, 480), "TO BOOK NOW", font=font("anton", 190), fill="#ffffff", anchor="ls")
    y = 590
    for it in items[:6]:
        dd = _dl(it["date"])
        d.text((64, y), f"{dd['mon']} {dd['day']}", font=font("anton", 54), fill=hexc(SAFFRON), anchor="lm")
        nf = fit(it["name"], "inter-black", W - 330, 44, 28)
        d.text((290, y - 2), ellipsize(it["name"], nf, W - 330), font=nf, fill="#ffffff", anchor="lm")
        d.text((290, y + 38), ellipsize(it["venue"], font("inter-medium", 26), W - 330), font=font("inter-medium", 26), fill="#b9b3d6", anchor="lm")
        y += 104
    handle(d, "#8a84b0", y=H - 40)
    return img


# ── GUIDE: festival or niche ───────────────────────────────────────────────
def guide_cover(kicker, title, subtitle, stat, bg, ink, acc, rings_seed=0):
    img = Image.new("RGB", (W, H), hexc(bg))
    rings = Image.new("RGB", (W, H), hexc(bg))
    rd = ImageDraw.Draw(rings)
    cx, cy = [(W + 60, -80), (-100, 300), (W + 20, 700)][rings_seed % 3]
    for i, r in enumerate(range(120, 1600, 64)):
        rd.ellipse([cx - r, cy - r, cx + r, cy + r], outline=hexc(acc), width=4 if i % 4 == 0 else 1)
    img = Image.blend(img, rings, 0.45)
    d = ImageDraw.Draw(img)
    tracked(d, (64, 90), kicker, font("inter-black", 28), hexc(acc), track=6, anchor="lm")
    size = 240
    while True:  # largest title that stays clear of the kicker (top edge >= 150)
        f, lines = fit_block(title.upper(), "anton", W - 128, max_lines=3, max_size=size, min_size=110)
        lh = int(f.size * 0.95)
        if 760 - lh * (len(lines) - 1) - int(f.size * 0.8) >= 150 or f.size <= 110:
            break
        size = f.size - 8
    y = 760 - lh * (len(lines) - 1)
    for ln in lines:
        d.text((56, y), ln, font=f, fill=hexc(ink), anchor="ls")
        y += lh
    sf, sl = fit_block(subtitle, "serif-italic", W - 128, max_lines=2, max_size=64, min_size=40)
    y2 = 860
    for ln in sl:
        d.text((64, y2), ln, font=sf, fill=hexc(acc), anchor="ls")
        y2 += int(sf.size * 1.15)
    d.line([(64, 1110), (W - 64, 1110)], fill=hexc(ink), width=2)
    d.text((64, 1180), stat, font=fit(stat, "inter-black", W - 128, 44, 30), fill=hexc(ink), anchor="lm")
    d.text((64, 1236), "Swipe for the full list · save this post", font=font("inter-medium", 30), fill=hexc(ink), anchor="lm")
    handle(d, hexc(ink), y=H - 40)
    return img


def guide_list(heading, groups, bg, ink, acc, sub_ink):
    """groups: [(date_label, [items])] — compact rows, up to ~9 rows a slide."""
    img = Image.new("RGB", (W, H), hexc(bg))
    d = ImageDraw.Draw(img)
    M = 60
    tracked(d, (M, 76), heading, font("inter-black", 26), hexc(acc), track=5, anchor="lm")
    y = 140
    for label, items in groups:
        d.text((M, y), label, font=font("anton", 46), fill=hexc(acc), anchor="lm")
        y += 54
        for it in items:
            nf = font("inter-black", 33)
            d.text((M, y), ellipsize(it["name"], nf, W - 2 * M - 120), font=nf, fill=hexc(ink), anchor="lm")
            if it.get("price"):
                d.text((W - M, y), it["price"], font=font("inter-black", 28), fill=hexc(ink), anchor="rm")
            meta = " · ".join(x for x in (it.get("time"), it["venue"], it.get("city")) if x)
            d.text((M, y + 38), ellipsize(meta, font("inter-medium", 26), W - 2 * M), font=font("inter-medium", 26), fill=hexc(sub_ink), anchor="lm")
            y += 92
        y += 14
    d.text((M, H - 50), "Tickets & links: link in bio", font=font("inter-semibold", 26), fill=hexc(sub_ink), anchor="lm")
    handle(d, hexc(sub_ink), x=W - M, y=H - 50, anchor="rm")
    return img


# ── STORY frames (1080x1920) ───────────────────────────────────────────────
def story_countdown(photo, days, name, when, venue):
    SW, SH = 1080, 1920
    img = Image.new("RGB", (SW, SH), hexc(NIGHT))
    ph = cover(photo, SW, 1300, ay=0.15)
    ph = fade_to(ph, NIGHT, 800, 1300)
    img.paste(ph, (0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 160, SW, 260], fill=hexc(SAFFRON))
    tracked(d, (SW // 2, 210), f"{days} DAYS TO GO" if days != 1 else "TOMORROW", font("anton", 72), NIGHT, track=4, anchor="mm")
    f, lines = fit_block(name.upper(), "anton", SW - 120, max_lines=2, max_size=190, min_size=90)
    y = 1400
    for ln in lines:
        d.text((SW // 2, y), ln, font=f, fill="#ffffff", anchor="ms")
        y += int(f.size * 0.96)
    d.text((SW // 2, y + 30), when, font=font("anton", 64), fill=hexc(SAFFRON), anchor="ms")
    d.text((SW // 2, y + 100), venue, font=font("inter-medium", 40), fill="#d8d0c8", anchor="ms")
    d.rounded_rectangle([SW // 2 - 230, SH - 300, SW // 2 + 230, SH - 210], radius=45, fill="#ffffff")
    d.text((SW // 2, SH - 255), "GET TICKETS", font=font("inter-black", 36), fill=NIGHT, anchor="mm")
    return img


def alert_text(kicker, name, sub, when, venue, cta, tint="#7a2410"):
    """Alert without a photo: same saffron band, name set big over a tinted ring field."""
    img = Image.new("RGB", (W, H), hexc(NIGHT))
    rings = Image.new("RGB", (W, H), hexc(NIGHT))
    rd = ImageDraw.Draw(rings)
    for i, r in enumerate(range(100, 1700, 56)):
        rd.ellipse([W - 80 - r, 520 - r, W - 80 + r, 520 + r], outline=hexc(tint), width=5 if i % 3 == 0 else 2)
    img = Image.blend(img, rings, 0.55)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 110], fill=hexc(SAFFRON))
    tracked(d, (60, 56), kicker, font("anton", 64), NIGHT, track=3, anchor="lm")
    tracked(d, (W - 60, 56), "TORONTO", font("inter-black", 26), NIGHT, track=6, anchor="rm")
    f, lines = fit_block(name.upper(), "anton", W - 120, max_lines=3, max_size=260, min_size=110)
    lh = int(f.size * 0.95)
    y = 960 - lh * (len(lines) - 1)
    for ln in lines:
        d.text((52, y), ln, font=f, fill="#ffffff", anchor="ls")
        y += lh
    if sub:
        d.text((60, 1040), sub, font=fit(sub, "serif-italic", W - 120, 56, 34), fill=hexc(SAFFRON), anchor="ls")
    d.line([(60, 1100), (W - 60, 1100)], fill=hexc("#3a3330"), width=2)
    d.text((60, 1160), when, font=fit(when, "anton", W - 120, 70, 44), fill="#ffffff", anchor="lm")
    d.text((60, 1226), venue, font=fit(venue, "inter-medium", W - 120, 36, 26), fill="#d8d0c8", anchor="lm")
    cf = font("inter-black", 28)
    cw = cf.getlength(cta) + 56
    d.rounded_rectangle([60, 1262, 60 + cw, 1316], radius=27, fill=hexc(SAFFRON))
    d.text((60 + cw / 2, 1289), cta, font=cf, fill=NIGHT, anchor="mm")
    handle(d, "#8a8299", x=W - 60, y=1289, anchor="rm")
    return img
