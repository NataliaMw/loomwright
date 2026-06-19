# Ouroboros — pitch deck

`index.html` is the deck. It's two things from one source:

- **Live / present mode** — open `index.html`. Real slides: arrow keys / space / wheel / swipe
  flip one slide at a time, dots jump, `f` toggles fullscreen. The hero ring animates
  (generate → check → revise → ship) and the transcript plays itself in on slide 8.
- **`ouroboros-deck.pdf`** — 11 landscape pages at exactly 16:9 (960×540pt), for the
  lablab.ai slide-deck upload. Animations freeze to clean still frames.

`cover.png` is the title slide (the golden ouroboros cover, 1920×1080). Self-contained —
no CDN, no build step, works double-clicked.

## Regenerate the PDF

```bash
python3 -m http.server 8911 -d . &
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --headless=new --disable-gpu --no-sandbox \
  --print-to-pdf="ouroboros-deck.pdf" --no-pdf-header-footer \
  --virtual-time-budget=7000 \
  "http://localhost:8911/index.html?print=1"
```

`?print=1` expands every slide and freezes the animations before printing.
