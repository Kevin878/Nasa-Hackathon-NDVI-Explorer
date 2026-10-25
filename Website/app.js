// --- Backend API configuration ---
// Local dev (page opened on localhost) talks to the local Flask server;
// anything else uses the deployed Render API. Override by setting
// window.API_BASE_URL before this script, or appending ?api=<url> to the URL.
const PROD_API_URL = "https://ndvi-api-wtsg.onrender.com";
const LOCAL_API_URL = "http://127.0.0.1:4000";

function resolveApiBase() {
  const fromQuery = new URLSearchParams(location.search).get("api");
  if (fromQuery) return fromQuery.replace(/\/$/, "");
  if (window.API_BASE_URL) return window.API_BASE_URL.replace(/\/$/, "");
  const isLocal = ["localhost", "127.0.0.1"].includes(location.hostname);
  return isLocal ? LOCAL_API_URL : PROD_API_URL;
}

const API_BASE_URL = resolveApiBase();

// --- Elements ---
const form = document.getElementById("search-form");
const submitBtn = document.getElementById("submit-btn");
const errorBox = document.getElementById("error-box");
const statusNote = document.getElementById("status-note");
const resultCard = document.getElementById("result-card");

function setError(message) {
  if (!message) {
    errorBox.hidden = true;
    errorBox.textContent = "";
    return;
  }
  errorBox.textContent = message;
  errorBox.hidden = false;
}

function setStatus(message) {
  if (!message) {
    statusNote.hidden = true;
    statusNote.textContent = "";
    return;
  }
  statusNote.textContent = message;
  statusNote.hidden = false;
}

function renderResult(data, query) {
  document.getElementById("meta-coord").textContent = `${query.lat}, ${query.lon}`;
  const unitLabel = query.unit === "K" ? "公里" : "公尺";
  document.getElementById("meta-range").textContent = `${query.range} ${unitLabel}`;

  const ndvi = data.mean_ndvi;
  document.getElementById("meta-ndvi").textContent =
    ndvi === null || ndvi === undefined || ndvi === "" ? "暫無資料" : Number(ndvi).toFixed(3);

  const datePill = document.getElementById("image-date-pill");
  if (data.closest_image_date) {
    document.getElementById("image-date").textContent = data.closest_image_date;
    datePill.hidden = false;
  } else {
    datePill.hidden = true;
  }

  document.getElementById("result-image").src = data.ndvi_heatmap_png_base64 || "";
  resultCard.hidden = false;
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  setError(null);
  resultCard.hidden = true;

  const query = {
    lat: document.getElementById("lat").value,
    lon: document.getElementById("lon").value,
    range: document.getElementById("range").value,
    unit: document.getElementById("unit").value,
  };

  const params = new URLSearchParams({
    lat: query.lat,
    lon: query.lon,
    buffer_val: query.range,
    buffer_unit: query.unit,
  });

  submitBtn.disabled = true;
  submitBtn.textContent = "查詢中…（Searching）";
  // Render free tier spins down when idle — the first request may wake the server.
  setStatus("正在喚醒伺服器並運算衛星影像，首次查詢可能需要 30-60 秒，請稍候…");

  try {
    const res = await fetch(`${API_BASE_URL}/ndvi_heatmap?${params.toString()}`);
    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      throw new Error(data.description || `NDVI 服務回傳錯誤（${res.status}）`);
    }

    setStatus(null);
    renderResult(data, query);
  } catch (err) {
    setStatus(null);
    const offline = err instanceof TypeError; // fetch network/DNS failure
    setError(
      offline
        ? "無法連線到 NDVI 服務，請確認後端是否已啟動，或稍後再試。"
        : err.message
    );
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "查詢植生狀況（Search NDVI）";
  }
});
