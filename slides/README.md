# Ouroboros — pitch deck

`index.html` is the deck — **13 slides**, one cinematic gold identity matching the cover.
Two things from one source:

- **Live / present mode** — open `index.html`, press `f` for fullscreen. Arrow keys / space /
  wheel / swipe flip one slide at a time; dots jump. The hero ring animates slowly
  (generate → check → revise → ship). Slide 10 shows the real `demo.py` outcome as a
  revision-bounce diagram (rev 0 ❌ → rev 1 ✅), captured live.
- **`ouroboros-deck.pdf`** — 13 landscape pages at exactly 16:9 (960×540pt), for the
  lablab.ai slide-deck upload. Animations freeze to clean still frames.

## Assets
- `cover.png` — title slide (the golden ouroboros, 1920×1080).
- `band-agents.jpeg`, `band-convo.jpeg` — **real** Band UI screenshots (the 6 registered
  agents + a live room conversation) embedded as evidence on slides 6 and 9.
- `RECORDING_CHECKLIST.md` — beat-by-beat shot list for capturing the ≤5-min MP4, synced
  to these slides and to `../../VIDEO_SCRIPT.md`.

Self-contained — no CDN, no build step, works double-clicked.

## Slide order
1 Cover · 2 Hero (ring) · 3 The shift · 4 The gap · 5 What it is · 6 The band (real screenshot) ·
7 Two loops · 8 Band is load-bearing · 9 Proof (real screenshot) · 10 Watch it run (replay) ·
11 The bug · 12 Why it wins · 13 Close.

## Regenerate the PDF

```bash
python3 -m http.server 8911 -d . &
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --no-sandbox \
  --print-to-pdf="ouroboros-deck.pdf" --no-pdf-header-footer \
  --virtual-time-budget=9000 \
  "http://localhost:8911/index.html?print=1"
```

`?print=1` expands every slide and freezes the animations (and renders the full replay) before printing.
