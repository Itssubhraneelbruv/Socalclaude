# SoCal Claude Impact Lab

2026-08-08

# tracking burnout in employees


### UX

tabs:
physiological
psychological
self-reported
environmental

## Tech Stack

- **React 18** (via CDN, no build step)
- **Babel Standalone** (in-browser JSX transform)
- **Claude Sonnet 4.6** (AI sentiment analysis pipeline)
- **Python `http.server`** (local dev server, managed via `uv`)

## Dev Notes

**Run locally:**
```bash
cd burnout-dashboard
uv run python -m http.server 8080
```
Then open http://localhost:8080

No build step — `burnout-dashboard/index.html` is self-contained. React and Babel load from CDN.
