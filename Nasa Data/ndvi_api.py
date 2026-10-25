import ee
import numpy as np
import rasterio
import requests
from io import BytesIO
import datetime
import base64
from flask import Flask, jsonify, request
from flask_cors import CORS
import traceback
import os
import json
from google.oauth2 import service_account

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

plt.rcParams['axes.unicode_minus'] = False

# --- Configuration ---
GEE_PROJECT_ID = os.environ.get('GEE_PROJECT_ID', 'nasa-hackathon-474108')
MODIS_SCALE = 250  # MODIS/061/MOD13Q1 native resolution (metres)
GEE_SECRET_FILE_PATH = os.environ.get(
    'GEE_CREDENTIALS_PATH', '/etc/secrets/GEE_CREDENTIALS_JSON'
)  # Render Secret File path
GEE_SCOPES = ['https://www.googleapis.com/auth/cloud-platform']

# --- Flask app + CORS (static frontend lives on a different origin) ---
app = Flask(__name__)
CORS(app)


# --- GEE initialization (run once at startup, not per request) ---
def init_gee():
    """Authenticate and initialize Earth Engine a single time for the process.

    Prefers a service-account key mounted as a Render Secret File; falls back to
    default application credentials for local development (after
    `earthengine authenticate`).
    """
    if os.path.exists(GEE_SECRET_FILE_PATH):
        with open(GEE_SECRET_FILE_PATH, 'r') as f:
            credentials_info = json.load(f)
        service_account_email = credentials_info.get('client_email', 'UNKNOWN_EMAIL')
        print(f"GEE: initializing with service account {service_account_email}")
        credentials = service_account.Credentials.from_service_account_info(
            info=credentials_info, scopes=GEE_SCOPES
        )
        ee.Initialize(credentials=credentials, project=GEE_PROJECT_ID)
    else:
        print("GEE: secret file not found, using default credentials (local dev).")
        ee.Initialize(project=GEE_PROJECT_ID)
    print("GEE initialized successfully.")


# Initialize at import time so gunicorn workers are ready before the first request.
try:
    init_gee()
except Exception as e:  # noqa: BLE001 - surface init failure in logs, retry lazily later
    print(f"GEE initialization failed at startup: {e}")


def ensure_gee():
    """Lazily (re)initialize GEE if the client isn't ready yet."""
    if not ee.data.is_initialized():
        init_gee()


# --- Heatmap rendering ---
def generate_heatmap_base64(ndvi_array):
    """Render an NDVI numpy array as an RdYlGn heatmap PNG, returned as a data URI."""
    if ndvi_array is None or ndvi_array.size == 0:
        return None

    ndvi_array = np.clip(ndvi_array, -1.0, 1.0)

    fig, ax = plt.subplots(figsize=(6, 6))
    cax = ax.imshow(ndvi_array, cmap='RdYlGn', vmin=-1, vmax=1)
    ax.set_xticks([])
    ax.set_yticks([])
    cbar = fig.colorbar(cax, orientation='horizontal', fraction=0.046, pad=0.04)
    cbar.set_label('Normalized Difference Vegetation Index (NDVI)', fontsize=10)

    buf = BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0, dpi=100)
    plt.close(fig)

    buf.seek(0)
    base64_img = base64.b64encode(buf.read()).decode('utf-8')
    return f"data:image/png;base64,{base64_img}"


# --- Core GEE data processing ---
def process_ndvi_for_location(lat, lon, date_str, buffer_val, buffer_unit):
    """Fetch NDVI for a location/date window from MODIS and return
    (mean_ndvi, ndvi_array, image_date).

    On a recoverable data error, ndvi_array is None and image_date holds a
    human-readable error message.
    """
    ensure_gee()

    buffer_val_m = buffer_val * 1000 if buffer_unit == 'K' else buffer_val

    point = ee.Geometry.Point(lon, lat)
    region = point.buffer(buffer_val_m)

    gee_target_date = ee.Date(date_str)
    date_start = gee_target_date.advance(-100, 'day')
    date_end = gee_target_date.advance(100, 'day')

    collection = ee.ImageCollection('MODIS/061/MOD13Q1') \
        .filterBounds(region) \
        .filterDate(date_start, date_end) \
        .select('NDVI')

    image_count = collection.size().getInfo()
    if image_count == 0:
        return None, None, f"找不到 {date_str} ±100 天內的 MODIS/MOD13Q1 影像。"

    # Pick the highest-NDVI (best quality) pixels across the window.
    image = collection.qualityMosaic('NDVI').clip(region)
    ndvi_band = image.select('NDVI').divide(10000.0)  # MODIS NDVI scale factor

    image_date = date_str
    image_date_ms = image.get('system:time_start').getInfo()
    if image_date_ms is not None:
        try:
            image_date = datetime.datetime.fromtimestamp(
                image_date_ms / 1000
            ).strftime('%Y-%m-%d')
        except (TypeError, ValueError):
            pass

    mean_ndvi = ndvi_band.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=region,
        scale=MODIS_SCALE,
        maxPixels=1e9,
    ).getInfo().get('NDVI')

    # Download the NDVI raster as GeoTIFF for the heatmap.
    download_params = {
        'region': region.bounds().getInfo()['coordinates'],
        'scale': MODIS_SCALE,
        'format': 'GeoTIFF',
    }
    try:
        download_url = ndvi_band.getDownloadURL(download_params)
        response = requests.get(download_url, timeout=60)
        response.raise_for_status()
        with rasterio.open(BytesIO(response.content)) as src:
            ndvi_array = src.read(1)
        # Treat water / NoData (< -0.1) as NaN so it drops out of the heatmap.
        ndvi_array[ndvi_array < -0.1] = np.nan
    except requests.exceptions.RequestException as e:
        print(f"Error during image download: {e}")
        return mean_ndvi, None, f"影像下載失敗 (Earth Engine): {e}"
    except Exception as e:  # noqa: BLE001
        print(f"Error processing downloaded image: {e}")
        return mean_ndvi, None, f"處理下載影像失敗 (Rasterio): {e}"

    return mean_ndvi, ndvi_array, image_date


# --- JSON error responses (so the static frontend can parse failures) ---
class ApiError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@app.errorhandler(ApiError)
def handle_api_error(err):
    return jsonify({"status": "error", "description": err.message}), err.status_code


# --- API endpoints ---
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "gee_initialized": ee.data.is_initialized()})


@app.route('/ndvi_heatmap', methods=['GET'])
def get_ndvi_heatmap():
    try:
        lat = float(request.args.get('lat'))
        lon = float(request.args.get('lon'))
        date = request.args.get('date', datetime.date.today().strftime('%Y-%m-%d'))
        buffer_val = int(request.args.get('buffer_val', 5))
        buffer_unit = request.args.get('buffer_unit', 'K')
    except (ValueError, TypeError):
        raise ApiError(400, "經緯度 (lat, lon) 和半徑值 (buffer_val) 必須是有效數字。")

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ApiError(400, "經緯度範圍無效。")
    if buffer_unit not in ('M', 'K'):
        raise ApiError(400, "單位 (buffer_unit) 必須是 'M' 或 'K'。")
    if buffer_val <= 0:
        raise ApiError(400, "半徑值 (buffer_val) 必須大於 0。")

    if (buffer_unit == 'K' and buffer_val > 50) or (buffer_unit == 'M' and buffer_val > 50000):
        print("警告: 緩衝區值過大，可能導致請求超時。")

    try:
        mean_ndvi, heatmap_data, image_date = process_ndvi_for_location(
            lat, lon, date, buffer_val, buffer_unit
        )
    except Exception as e:  # noqa: BLE001
        print("--- Internal Server Error Traceback ---")
        traceback.print_exc()
        raise ApiError(500, f"Internal Server Error during GEE processing: {e}")

    if heatmap_data is None:
        # image_date carries the error message in this case.
        raise ApiError(404, image_date)

    return jsonify({
        "status": "success",
        "query_date": date,
        "closest_image_date": image_date,
        "mean_ndvi": f"{mean_ndvi:.4f}" if mean_ndvi is not None else None,
        "ndvi_heatmap_png_base64": generate_heatmap_base64(heatmap_data),
        "buffer_radius": f"{buffer_val} {buffer_unit}",
    })


# --- Local development server (ignored by gunicorn on Render) ---
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=4000, debug=True)
