# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

NDVI Explorer — takes GPS coordinates + a search radius and returns a color-coded vegetation-health (NDVI) heatmap with statistics, sourced from MODIS satellite imagery via Google Earth Engine (GEE).

Two independently-deployed pieces:

- **`Website/`** — a **static site** (plain HTML/CSS/JS, no build step, no server). The browser calls the backend API directly with `fetch`. Deploy to any static host (Cloudflare Pages / Vercel / GitHub Pages).
- **`Nasa Data/`** — Flask API backend (Python). Does all GEE/NDVI work and renders the heatmap. Deploy to a persistent Python host (Render free tier).

> History: the frontend used to be an Express 5 + EJS server that *proxied* to the backend over a hardcoded `http://127.0.0.1:4000`. That broke in production (separate hosts can't reach each other over localhost) and the Node service also cold-started on Render's free tier. It was replaced by this static site, which the browser serves instantly and which talks to the backend's public HTTPS URL directly.

Note: `Website/` and `Nasa Data/` each contain their own `.git` directory and show up as "modified content" in the parent repo's `git status`, but there is **no `.gitmodules`** — they are nested repos, not registered submodules. Commit inside each subdirectory for its own history.

## Commands

### Backend — `Nasa Data/`
```bash
cd "Nasa Data"
pip install -r requirements.txt
earthengine authenticate      # first-time local GEE auth only
python ndvi_api.py            # dev server on port 4000 (debug=True)
gunicorn ndvi_api:app         # production start command (as on Render)
```

### Frontend — `Website/`
No install, no build. Open `index.html` directly, or serve the folder:
```bash
cd Website
python3 -m http.server 8000   # then visit http://localhost:8000
```
There is no linter and no test suite anywhere in the repo.

## Architecture & data flow

```
Browser (static Website/) ──fetch GET /ndvi_heatmap?lat&lon&buffer_val&buffer_unit──▶
                                              Nasa Data/ndvi_api.py (Flask :4000)
                                                 → GEE initialized once at startup
                                                 → MODIS/061/MOD13Q1, date ±100 days
                                                 → qualityMosaic('NDVI').clip(region)
                                                 → reduceRegion → mean_ndvi
                                                 → getDownloadURL (GeoTIFF) → rasterio → numpy
                                                 → matplotlib RdYlGn heatmap → base64 PNG
                                                       │ JSON {status, mean_ndvi, closest_image_date, ndvi_heatmap_png_base64, ...}
                                                       ▼
                                            app.js renders the result card
```

Key things to know before editing:

- **Frontend → backend URL resolution** lives in `Website/app.js` (`resolveApiBase`): `localhost`/`127.0.0.1` → `http://127.0.0.1:4000`, otherwise the production URL `https://ndvi-api-wtsg.onrender.com`. Overridable via `?api=<url>` in the query string or `window.API_BASE_URL`. **When the backend's deployed URL changes, update `PROD_API_URL` here.**
- **CORS is required and enabled** — the static frontend is a different origin from the API, so `ndvi_api.py` applies `CORS(app)` (flask-cors). Removing it breaks the browser call.
- **GEE is initialized once** at import time via `init_gee()` (not per request as it used to be); `ensure_gee()` re-inits lazily if the client isn't ready. Credentials come from a service-account key at `/etc/secrets/GEE_CREDENTIALS_JSON` (Render Secret File), falling back to default application credentials locally. `GEE_PROJECT_ID`, the secret path, etc. are read from env vars with sensible defaults at the top of the file.
- **Errors are JSON**, not HTML. `ndvi_api.py` raises `ApiError(status, message)`; an `@app.errorhandler` returns `{"status":"error","description": ...}`. `app.js` reads `data.description`. Don't reintroduce Flask's `abort()` (returns HTML the frontend can't parse).
- **Heatmaps are inline base64 data URIs** (`data:image/png;base64,...`) in the JSON, set directly as an `<img src>`.
- **Form field vs. API param names**: the form uses `range`/`unit`; `app.js` maps them to the API's `buffer_val`/`buffer_unit`. `buffer_unit` is `'K'` (km) or `'M'` (m); the API converts to metres for GEE.
- **Cold-start UX**: Render free tier spins down when idle, so the first `/ndvi_heatmap` call can take ~30-60s. `app.js` shows a "waking the server" status note while waiting — keep that feedback if you touch the submit flow. `GET /health` is a lightweight endpoint for warming/uptime checks.
- Data source is **MODIS**, not Landsat — any UI copy mentioning Landsat is stale wording, not a logic signal.

## Deployment

- **Backend** (Render, free tier): Python web service, start command `gunicorn ndvi_api:app`, with a Secret File at `/etc/secrets/GEE_CREDENTIALS_JSON` containing the GEE service-account key. Set `GEE_PROJECT_ID` as an env var if it differs from the default.
- **Frontend** (static host, e.g. Cloudflare Pages): point the project at the `Website/` directory with **no build command** and output directory = `Website/`. It's just static files. Instant load, no cold start.
