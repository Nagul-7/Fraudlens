# FraudLens dashboard (Phase 5)

React + Vite + Leaflet console for the FraudLens prediction API.

## Run

The API must be running first:

```bash
# terminal 1 - from the repo root
source venv/bin/activate
uvicorn api.main:app --port 8000

# terminal 2 - here
npm install
npm run dev          # http://localhost:5173
```

Vite proxies `/api/*` to `http://127.0.0.1:8000`, so the browser stays on one
origin and there are no CORS surprises during a demo.

Node 20 is expected. This machine has it at `~/.local/opt/node20/bin`, so if
`node` is not on your PATH:

```bash
export PATH=$HOME/.local/opt/node20/bin:$PATH
```

## Screenshots

`node scripts/screenshot.mjs ./shots` drives a real browser (advance the clock,
open a district) and writes 1920x1080 PNGs. Both servers must be running.

## Layout

```
src/
  App.jsx                  state, data loading, layout
  api.js                   fetch wrapper; every failure becomes a readable Error
  risk.js                  the risk colour ramp and number formatting
  components/
    TopBar.jsx             clock, Advance 6h, self-grading result (the centrepiece)
    MapView.jsx            Leaflet district choropleth
    Legend.jsx             risk scale
    FilterPanel.jsx        state / category / threshold / top-K, and the watchlist
    DistrictPanel.jsx      drill-down on click
    Sparkline.jsx          30-day risk history
    ErrorBoundary.jsx      catches render errors so the page never goes blank
```
