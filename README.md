# NDVI Explorer — NASA Hackathon Project

A web application that lets users query real-time vegetation health data by entering GPS coordinates and a search radius. It fetches MODIS satellite imagery via Google Earth Engine (GEE), calculates the Normalized Difference Vegetation Index (NDVI), and renders a color-coded heatmap alongside key statistics.

**Authors:** Kevin HSU, Wesley WEN

---

## Project Structure

```
Nasa Hackathon/
├── Nasa Data/                  # Python Flask API (backend)
│   ├── ndvi_api.py             # Main Flask app — GEE integration, NDVI processing, heatmap generation
│   └── requirements.txt        # Python dependencies
│
└── Website/                    # Static frontend (plain HTML/CSS/JS, no build step)
    ├── index.html              # Home page — search form and results display
    ├── ndvi.html               # Informational page explaining NDVI
    ├── app.js                  # Calls the Flask API directly via fetch
    └── index.css               # Global stylesheet
```

---

## How It Works

```
User (Browser) — static Website/ (index.html + app.js)
     │  fetch GET /ndvi_heatmap?lat=…&lon=…&buffer_val=…&buffer_unit=…
     ▼
Nasa Data/ndvi_api.py  (Flask, port 4000; CORS enabled)
     │  Authenticates with Google Earth Engine via service account (once at startup)
     │  Queries MODIS/061/MOD13Q1 (±100 days around the requested date)
     │  Selects the best-quality mosaic image using qualityMosaic('NDVI')
     │  Downloads a GeoTIFF, reads it with Rasterio, generates a heatmap PNG
     ▼
Returns JSON: { status, mean_ndvi, closest_image_date, ndvi_heatmap_png_base64 }
     │
     ▼
app.js renders the result card with the heatmap image and stats
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | 3.10+ |
| Node.js | 18+ |
| Google Earth Engine account | with a GCP project enabled |
| GEE service account JSON key | for server-side auth |

---

## Setup & Running Locally

### 1. Flask API (`Nasa Data/`)

```bash
cd "Nasa Data"

# Install dependencies
pip install -r requirements.txt

# Authenticate with GEE (first-time local setup only)
earthengine authenticate

# Run the API server (port 4000)
python ndvi_api.py
```

The API reads GEE credentials from `/etc/secrets/GEE_CREDENTIALS_JSON` (Render deployment) or falls back to default application credentials for local development.

### 2. Static Website (`Website/`)

No install, no build step. Either open `Website/index.html` directly, or serve the folder:

```bash
cd Website
python3 -m http.server 8000
```

Open `http://localhost:8000` in your browser.

> **Note:** When opened on `localhost`/`127.0.0.1`, `app.js` automatically calls the local Flask API at `http://127.0.0.1:4000`, so start the Flask API first. Otherwise it uses the production API URL. Override with `?api=<url>` in the address bar.

---

## API Reference

### `GET /ndvi_heatmap`

Hosted at `https://ndvi-api-wtsg.onrender.com` (production) or `http://localhost:4000` (local).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `lat` | float | Yes | Latitude (-90 to 90) |
| `lon` | float | Yes | Longitude (-180 to 180) |
| `buffer_val` | int | No (default: 5) | Search radius value |
| `buffer_unit` | string | No (default: `K`) | `K` = kilometers, `M` = meters |
| `date` | string | No (default: today) | Target date `YYYY-MM-DD` |

**Success response (200):**

```json
{
  "status": "success",
  "query_date": "2024-06-15",
  "closest_image_date": "2024-06-09",
  "mean_ndvi": "0.6231",
  "ndvi_heatmap_png_base64": "data:image/png;base64,...",
  "buffer_radius": "5 K"
}
```

**Example request:**

```bash
curl "http://localhost:4000/ndvi_heatmap?lat=30.0&lon=120.0&buffer_val=10&buffer_unit=K"
```

---

## Cold Starts

Render's free tier spins down idle services, so the **first** `/ndvi_heatmap` request after a period of inactivity can take ~30–60s while the backend wakes up. The frontend shows a "waking the server" notice during this wait. The frontend itself is a static site and always loads instantly. A lightweight `GET /health` endpoint is available for uptime/warming checks.

---

## NDVI Scale Reference

| Value | Interpretation |
|-------|----------------|
| < 0 | Water bodies or bare land |
| 0.0 – 0.2 | Bare soil / urban |
| 0.2 – 0.4 | Sparse grassland / shrubs |
| 0.4 – 0.6 | Moderate vegetation |
| > 0.6 | Dense forest / healthy crops |

NDVI is calculated from MODIS band reflectances and scaled by a factor of 0.0001. Values below -0.1 are treated as NoData (water/cloud) and excluded from the heatmap.

---

## Deployment

**Backend — `Nasa Data/` (Render, Python web service):**

1. Start command: `gunicorn ndvi_api:app`.
2. Add a **Secret File** at `/etc/secrets/GEE_CREDENTIALS_JSON` containing your GEE service account JSON key.
3. Set `GEE_PROJECT_ID` as an environment variable (defaults to `nasa-hackathon-474108`).

**Frontend — `Website/` (static host, e.g. Cloudflare Pages / Vercel):**

1. Point the project at the `Website/` directory with **no build command** (output = `Website/`).
2. Update `PROD_API_URL` in `Website/app.js` to your deployed backend URL.

The frontend calls the backend directly from the browser, so the backend must have CORS enabled (it does — `flask-cors` is configured in `ndvi_api.py`).

## How to Use
Please view our demonstration powerpoint: https://docs.google.com/presentation/d/1VnsoueaX8pcoyEZgrUpVgF3KNwPTTwMMijMTJ-iNEOU/edit?usp=sharing