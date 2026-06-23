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
├── Call API/
│   └── ten_min.py              # Keep-alive script — pings the deployed API every 10 minutes
│
└── Website/                    # Node.js frontend server
    ├── server.js               # Express server — proxies requests to the Flask API
    ├── package.json
    ├── public/
    │   └── index.css           # Global stylesheet
    └── views/
        ├── index.ejs           # Home page — search form and results display
        ├── ndvi.ejs            # Informational page explaining NDVI
        └── partials/
            ├── header.ejs      # Shared navigation header
            └── footer.ejs      # Shared footer
```

---

## How It Works

```
User (Browser)
     │  POST /search (lat, lon, radius, unit)
     ▼
Website/server.js  (Express, port 3000)
     │  GET /ndvi_heatmap?lat=…&lon=…&buffer_val=…&buffer_unit=…
     ▼
Nasa Data/ndvi_api.py  (Flask, port 4000)
     │  Authenticates with Google Earth Engine via service account
     │  Queries MODIS/061/MOD13Q1 (±100 days around the requested date)
     │  Selects the best-quality mosaic image using qualityMosaic('NDVI')
     │  Downloads a GeoTIFF, reads it with Rasterio, generates a heatmap PNG
     ▼
Returns JSON: { mean_ndvi, closest_image_date, ndvi_heatmap_png_base64 }
     │
     ▼
index.ejs renders the result card with the heatmap image and stats
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

### 2. Express Website (`Website/`)

```bash
cd Website

# Install dependencies
npm install

# Start the frontend server (port 3000)
node server.js
```

Open `http://localhost:3000` in your browser.

> **Note:** The Express server expects the Flask API to be running at `http://127.0.0.1:4000`. Start the Flask API first.

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

## Keep-Alive Script (`Call API/ten_min.py`)

Render's free tier spins down idle services. This script keeps the deployed API warm by sending a ping request every 10 minutes to a rotating set of coordinates.

```bash
python "Call API/ten_min.py"
```

It uses exponential backoff (up to 3 retries) on failure and logs results to stdout.

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

## Deployment (Render)

1. Deploy `Nasa Data/` as a **Python web service** with start command `gunicorn ndvi_api:app`.
2. Add a **Secret File** at `/etc/secrets/GEE_CREDENTIALS_JSON` containing your GEE service account JSON key.
3. Set the `GEE_PROJECT_ID` variable in `ndvi_api.py` to your GCP project ID.
4. Run `Call API/ten_min.py` locally (or on a separate free instance) to prevent cold starts.
