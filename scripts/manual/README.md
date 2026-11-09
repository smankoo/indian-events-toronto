# Manual review loop (temporary)

Run by hand while we learn what the pipeline should do; nothing here is wired into
the workflows yet. Work on a copy of the database (`EVENTS_DB=...`).

1. `sweep_sources.py <dir-with-probe_sources.py> sweep.json` — search Eventbrite and AllEvents
   for desi keywords; dedupe; keep upcoming events.
2. `fetch_candidates.py sweep.json 14` — read each event page (JSON-LD), keep GTA events not
   already in the DB, classify them, save them.
3. `main.py --profile` then `main.py --score` — headliners/category/series, then tiers.
4. Render card previews and the weekend roundup (`image_generator/poster.py`).
5. `build_review_data.py <workdir>` + `review_template.html` → the "Post Review Queue" page,
   where each proposal gets a verdict (feature / card / roundup / skip) and edits. Decisions
   live in the page's database (`decisions/<source>_<id>`) and are read back by Claude.
