const resultNode = document.getElementById("result");
const historyPanel = document.getElementById("historyPanel");
const paramsForm = document.getElementById("paramsForm");
const urlForm = document.getElementById("urlForm");
const imagesInput = document.getElementById("imagesInput");
const districtSelect = document.getElementById("districtSelect");
const buildingTypeSelect = document.getElementById("buildingTypeSelect");
const rcSelect = document.getElementById("rcSelect");
const rcSearch = document.getElementById("rcSearch");
const latInput = document.getElementById("latInput");
const lonInput = document.getElementById("lonInput");
const debugPayloadNode = document.getElementById("debugPayload");

const authGuest = document.getElementById("authGuest");
const authUser = document.getElementById("authUser");
const accountBtn = document.getElementById("accountBtn");
const accountMenu = document.getElementById("accountMenu");
const openSignInBtn = document.getElementById("openSignIn");
const openSignUpBtn = document.getElementById("openSignUp");
const logoutBtn = document.getElementById("logoutBtn");
const historyBtn = document.getElementById("historyBtn");

const authModal = document.getElementById("authModal");
const authModalTitle = document.getElementById("authModalTitle");
const authEmailInput = document.getElementById("authEmail");
const authPasswordInput = document.getElementById("authPassword");
const authErrorNode = document.getElementById("authError");
const authSubmitBtn = document.getElementById("authSubmit");
const authCancelBtn = document.getElementById("authCancel");
let API_BASE = (window.__API_BASE_URL || "").replace(/\/+$/, "");

let selectedFiles = [];
let linkedImageUrls = [];
let rcOptions = ["Not selected"];
let map;
let marker;
let lastListingPrice = null;
let accessToken = localStorage.getItem("access_token") || "";
let currentUserEmail = localStorage.getItem("user_email") || "";
let authMode = "signin";

function updateDebugPayload(title, data) {
  if (!debugPayloadNode) return;
  debugPayloadNode.textContent = `${title}\n${JSON.stringify(data, null, 2)}`;
}

function showResultHtml(html, isError = false) {
  resultNode.classList.add("show");
  resultNode.style.color = isError ? "#8e1e1e" : "#0f2831";
  resultNode.innerHTML = html;
}

function formatMoney(value) {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(value || 0);
}

function fmtPct(value) {
  const n = Number(value || 0);
  return `${n > 0 ? "+" : ""}${n.toFixed(1)}%`;
}

function authHeaders() {
  return accessToken ? { Authorization: `Bearer ${accessToken}` } : {};
}

async function apiFetch(url, options = {}) {
  const fullUrl = `${API_BASE}${url}`;
  return fetch(fullUrl, { ...options, headers: { ...(options.headers || {}), ...authHeaders() } });
}

async function loadRuntimeConfig() {
  try {
    const res = await fetch("/runtime-config");
    if (!res.ok) return;
    const data = await res.json();
    const apiBase = String(data?.api_base_url || "").trim().replace(/\/+$/, "");
    if (apiBase) API_BASE = apiBase;
  } catch (_e) {}
}

function detailToText(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        if (typeof d === "string") return d;
        if (d && typeof d === "object") return d.msg || JSON.stringify(d);
        return String(d);
      })
      .join("; ");
  }
  if (detail && typeof detail === "object") return detail.msg || JSON.stringify(detail);
  return "Request failed";
}

function updateAuthUI() {
  const isLogged = Boolean(accessToken);
  authGuest.classList.toggle("hidden", isLogged);
  authUser.classList.toggle("hidden", !isLogged);
  if (isLogged) accountBtn.textContent = currentUserEmail || "Account";
}

function openAuthModal(mode) {
  authMode = mode;
  authModalTitle.textContent = mode === "signup" ? "Sign up" : "Sign in";
  authSubmitBtn.textContent = mode === "signup" ? "Create account" : "Sign in";
  authErrorNode.textContent = "";
  authModal.classList.remove("hidden");
}

function closeAuthModal() {
  authErrorNode.textContent = "";
  authModal.classList.add("hidden");
}

async function submitAuth() {
  const login = (authEmailInput.value || "").trim();
  const password = authPasswordInput.value || "";
  if (!login || !password) {
    authErrorNode.textContent = "Enter login and password.";
    return;
  }
  if (password.length < 6) {
    authErrorNode.textContent = "Password must be at least 6 characters.";
    return;
  }
  const endpoint = authMode === "signup" ? "/auth/register" : "/auth/login";
  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ login, password }),
  });
  const data = await res.json();
  if (!res.ok) {
    authErrorNode.textContent = detailToText(data.detail) || "Authentication failed.";
    return;
  }
  authErrorNode.textContent = "";
  accessToken = data.access_token;
  currentUserEmail = data.user?.email || login;
  localStorage.setItem("access_token", accessToken);
  localStorage.setItem("user_email", currentUserEmail);
  updateAuthUI();
  closeAuthModal();
  window.location.href = "/home";
}

function logout() {
  accessToken = "";
  currentUserEmail = "";
  localStorage.removeItem("access_token");
  localStorage.removeItem("user_email");
  accountMenu.classList.add("hidden");
  updateAuthUI();
  window.location.href = "/home";
}

function translateConditionLabel(v) {
  const s = String(v || "").toLowerCase();
  if (!s) return "—";
  if (s.includes("свеж") || s === "fresh") return "fresh renovation";
  if (s.includes("сред") || s === "average") return "average condition, likely cosmetic update needed";
  if (s.includes("треб") || s === "needs") return "needs renovation";
  return String(v);
}

function translateFeatureLabel(v) {
  const map = {
    "Фото (визуальные признаки)": "Photos (visual features)",
    "Возраст дома (лет)": "Building age (years)",
    "Площадь (м²)": "Area (m²)",
    "Относительный этаж": "Relative floor",
    "Этаж": "Floor",
    "Район": "District",
    "Тип дома": "Building type",
    "Комнат": "Rooms",
    "Этажность дома": "Total floors",
  };
  return map[String(v || "")] || String(v || "—");
}

function translateFeatureValue(feature, value) {
  const raw = String(value ?? "");
  const key = String(feature || "").toLowerCase();
  const districtMap = {
    "Алмалинский р-н": "Almaly District",
    "Ауэзовский р-н": "Auezov District",
    "Бостандыкский р-н": "Bostandyk District",
    "Жетысуский р-н": "Zhetysu District",
    "Медеуский р-н": "Medeu District",
    "Наурызбайский р-н": "Nauryzbay District",
    "Турксибский р-н": "Turksib District",
    "Алатауский р-н": "Alatau District",
  };
  const buildingMap = { "монолитный": "monolithic", "кирпичный": "brick", "панельный": "panel", "иной": "other" };
  if (key === "district" || key.includes("район")) return districtMap[raw] || raw;
  if (key === "building_type" || key.includes("тип дома")) return buildingMap[raw] || raw;
  return raw || "—";
}

function renderFactorTable(items, kind) {
  const rows = (items || [])
    .filter((x) => !String(x.feature || "").toLowerCase().includes("condition"))
    .slice(0, 6)
    .map((x) => `<tr><td>${translateFeatureLabel(x.feature_label || x.feature)}</td><td>${translateFeatureValue(x.feature, x.value)}</td><td class="${kind === "plus" ? "plus-cell" : "minus-cell"}">${fmtPct(x.impact_pct_ppm2)}</td><td>${formatMoney(x.impact_kzt_total || 0)} ₸</td></tr>`)
    .join("");
  return `<table class="factor-table"><thead><tr><th>Factor</th><th>Value</th><th>Impact</th><th>Contribution (₸)</th></tr></thead><tbody>${rows || '<tr><td colspan="4">No data</td></tr>'}</tbody></table>`;
}

function renderExplainResult(data, listingPrice = null) {
  const pred = data?.prediction || {};
  const why = data?.why_this_price || {};
  const renovation = data?.renovation || {};
  const listingPriceToShow = listingPrice ?? lastListingPrice;

  showResultHtml(`
    <div class="result-head-grid">
      <div class="result-card"><span>Estimated price</span><strong>${formatMoney(pred.price)} ₸</strong></div>
      <div class="result-card"><span>Price per m²</span><strong>${formatMoney(pred.price_per_m2)} ₸/m²</strong></div>
      <div class="result-card"><span>Listing price</span><strong>${listingPriceToShow == null ? "—" : `${formatMoney(listingPriceToShow)} ₸`}</strong></div>
      <div class="result-card"><span>Renovation</span><strong>${translateConditionLabel(renovation.condition_label || renovation.condition)}</strong></div>
    </div>
    <div class="factor-grid">
      <section><h4>Positive factors</h4>${renderFactorTable(why.top_positive || [], "plus")}</section>
      <section><h4>Negative factors</h4>${renderFactorTable(why.top_negative || [], "minus")}</section>
    </div>
  `);
}

function ensurePreviewContainers() {
  let localPreview = document.getElementById("localPhotoPreview");
  if (!localPreview) {
    localPreview = document.createElement("div");
    localPreview.id = "localPhotoPreview";
    localPreview.className = "image-preview-grid";
    paramsForm.appendChild(localPreview);
  }
}

function renderLocalPhotoPreview(files) {
  const host = document.getElementById("localPhotoPreview");
  if (!host) return;
  host.innerHTML = "";
  files.slice(0, 10).forEach((file, idx) => {
    const item = document.createElement("div");
    item.className = "preview-item";
    item.innerHTML = `<img src="${URL.createObjectURL(file)}" alt="${file.name}" class="preview-thumb" />`;
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "preview-remove";
    removeBtn.textContent = "×";
    removeBtn.addEventListener("click", () => {
      selectedFiles.splice(idx, 1);
      renderLocalPhotoPreview(selectedFiles);
    });
    item.appendChild(removeBtn);
    host.appendChild(item);
  });
}

function renderUsedPhotos(urls = []) {
  const host = document.getElementById("localPhotoPreview");
  if (!host) return;
  if (!urls.length) {
    host.innerHTML = "";
    return;
  }
  host.innerHTML = `<p class="used-photo-title">Photos used by the model</p><div class="image-preview-grid">${urls.map((u) => `<a href="${u}" target="_blank" rel="noreferrer"><img class="preview-thumb" src="${u}" alt="used-photo"/></a>`).join("")}</div>`;
}

function ensureSelectHasValue(selectEl, value) {
  if (!selectEl || value == null || value === "") return;
  const str = String(value);
  if (!Array.from(selectEl.options).some((o) => o.value === str)) {
    const opt = document.createElement("option");
    opt.value = str;
    opt.textContent = str;
    selectEl.appendChild(opt);
  }
  selectEl.value = str;
}

function setRcOptions(filtered) {
  rcSelect.innerHTML = "";
  for (const v of filtered) {
    const opt = document.createElement("option");
    opt.value = v === "Not selected" ? "" : v;
    opt.textContent = v;
    rcSelect.appendChild(opt);
  }
}

function filterRcOptions(query) {
  const q = (query || "").trim().toLowerCase();
  setRcOptions(!q ? rcOptions : [rcOptions[0], ...rcOptions.slice(1).filter((x) => x.toLowerCase().includes(q))]);
}

function syncMarkerFromInputs() {
  const lat = Number(latInput.value);
  const lon = Number(lonInput.value);
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || !marker || !map) return;
  marker.setLatLng([lat, lon]);
  map.panTo([lat, lon]);
}

function initMap() {
  const lat = Number(latInput.value) || 43.238949;
  const lon = Number(lonInput.value) || 76.889709;
  map = L.map("map", { zoomControl: true }).setView([lat, lon], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { attribution: "&copy; OpenStreetMap" }).addTo(map);
  marker = L.marker([lat, lon]).addTo(map);
  map.on("click", (e) => {
    latInput.value = String(Number(e.latlng.lat.toFixed(6)));
    lonInput.value = String(Number(e.latlng.lng.toFixed(6)));
    syncMarkerFromInputs();
  });
  latInput.addEventListener("change", syncMarkerFromInputs);
  lonInput.addEventListener("change", syncMarkerFromInputs);
}

function applyListingToForm(listing = {}) {
  const setValue = (name, value) => {
    if (value == null || value === "") return;
    const el = paramsForm.elements[name];
    if (el) el.value = String(value);
  };
  const setCoordValue = (name, value) => {
    const num = Number(value);
    if (!Number.isFinite(num)) return;
    const el = paramsForm.elements[name];
    if (el) el.value = String(Number(num.toFixed(6)));
  };

  setValue("area", listing.area);
  setValue("rooms", listing.rooms);
  setValue("floor", listing.floor);
  setValue("floors_total", listing.floors_total);
  setValue("year_built", listing.year_built);
  setCoordValue("latitude", listing.latitude);
  setCoordValue("longitude", listing.longitude);
  ensureSelectHasValue(districtSelect, listing.district);
  ensureSelectHasValue(buildingTypeSelect, listing.building_type);
  ensureSelectHasValue(rcSelect, listing.residential_complex);
  syncMarkerFromInputs();
}

function districtDisplayName(v) {
  return ({
    "Алмалинский р-н": "Almaly District",
    "Ауэзовский р-н": "Auezov District",
    "Бостандыкский р-н": "Bostandyk District",
    "Жетысуский р-н": "Zhetysu District",
    "Медеуский р-н": "Medeu District",
    "Наурызбайский р-н": "Nauryzbay District",
    "Турксибский р-н": "Turksib District",
    "Алатауский р-н": "Alatau District",
  }[v] || v);
}
function buildingTypeDisplayName(v) {
  return ({ "монолитный": "monolithic", "кирпичный": "brick", "панельный": "panel", "иной": "other" }[v] || v);
}

async function loadOptions() {
  try {
    const res = await apiFetch("/meta/options");
    if (!res.ok) return;
    const data = await res.json();
    districtSelect.innerHTML = "";
    for (const v of data.districts || []) districtSelect.insertAdjacentHTML("beforeend", `<option value="${v}">${districtDisplayName(v)}</option>`);
    buildingTypeSelect.innerHTML = "";
    for (const v of data.building_types || []) buildingTypeSelect.insertAdjacentHTML("beforeend", `<option value="${v}">${buildingTypeDisplayName(v)}</option>`);
    rcOptions = ["Not selected", ...(data.residential_complexes || [])];
    setRcOptions(rcOptions);
  } catch (_e) {
    showResultHtml("Failed to load options", true);
  }
}

function renderHistory(rows) {
  historyPanel.style.display = "block";
  if (!rows.length) {
    historyPanel.innerHTML = "<strong>My History</strong><div style='margin-top:8px;'>No records yet.</div>";
    return;
  }
  historyPanel.innerHTML = `<strong>My History</strong>${rows
    .map((h) => {
      const req = h.request_payload || {};
      return `<article style="padding:10px;border:1px solid #d3dde3;border-radius:10px;margin-top:8px;background:#fff;">
        <div><strong>${h.mode}</strong> • ${new Date(h.created_at).toLocaleString()}</div>
        <div>Price: ${formatMoney(h.predicted_price || 0)} ₸ | Price/m²: ${formatMoney(h.predicted_price_per_m2 || 0)} ₸</div>
        <div>Params: area=${req.area ?? "—"}, rooms=${req.rooms ?? "—"}, floor=${req.floor ?? "—"}, district=${req.district ?? "—"}</div>
        <div>Photos used: ${req.images_count ?? 0}</div>
      </article>`;
    })
    .join("")}`;
}

async function loadHistory() {
  if (!accessToken) {
    showResultHtml("Sign in to view history", true);
    return;
  }
  const res = await apiFetch("/history");
  const data = await res.json();
  if (!res.ok) {
    showResultHtml(data.detail || "Failed to load history", true);
    return;
  }
  renderHistory(data || []);
}

imagesInput.addEventListener("change", () => {
  const incoming = Array.from(imagesInput.files || []);
  if (!incoming.length) return;
  linkedImageUrls = [];
  selectedFiles = [...selectedFiles, ...incoming].slice(0, 10);
  imagesInput.value = "";
  renderLocalPhotoPreview(selectedFiles);
});

rcSearch.addEventListener("input", (e) => filterRcOptions(e.target.value));

paramsForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (selectedFiles.length > 0) lastListingPrice = null;

  const fd = new FormData(paramsForm);
  const files = selectedFiles.slice(0, 10);
  if (files.length > 0) linkedImageUrls = [];
  fd.delete("images");
  for (const file of files) fd.append("images", file);
  if (files.length) {
    fd.append("image_names_json", JSON.stringify(files.map((f) => f.name)));
  }
  if (!files.length && linkedImageUrls.length) fd.append("image_urls_json", JSON.stringify(linkedImageUrls));
  fd.set("object_type", "flat");
  fd.set("condition_norm", "unknown");

  showResultHtml("Calculating price and generating explanation...");
  try {
    const res = await apiFetch("/explain", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) {
      showResultHtml(data.detail || "Calculation error", true);
      return;
    }
    renderExplainResult(data);
  } catch (_e) {
    showResultHtml("Server unavailable", true);
  }
});

urlForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(urlForm);
  fd.append("use_photos", "true");

  showResultHtml("Parsing URL, filling fields, and calculating...");
  try {
    const res = await apiFetch("/predict_by_url", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) {
      showResultHtml(data.detail || "URL processing error", true);
      return;
    }

    const listing = data.listing || {};
    linkedImageUrls = Array.isArray(listing.used_image_urls) ? listing.used_image_urls : [];
    lastListingPrice = listing.price ?? null;
    selectedFiles = [];

    applyListingToForm(listing);
    renderUsedPhotos(linkedImageUrls);
    if (data.explain) renderExplainResult(data.explain, listing.price ?? null);
  } catch (_e) {
    showResultHtml("Server unavailable", true);
  }
});

openSignInBtn.addEventListener("click", () => openAuthModal("signin"));
openSignUpBtn.addEventListener("click", () => openAuthModal("signup"));
authSubmitBtn.addEventListener("click", submitAuth);
authCancelBtn.addEventListener("click", closeAuthModal);
logoutBtn.addEventListener("click", logout);
historyBtn.addEventListener("click", async () => {
  accountMenu.classList.add("hidden");
  window.location.href = "/my-history";
});
accountBtn.addEventListener("click", () => accountMenu.classList.toggle("hidden"));

document.addEventListener("click", (e) => {
  if (!accountMenu.contains(e.target) && e.target !== accountBtn) accountMenu.classList.add("hidden");
});

authModal.addEventListener("click", (e) => {
  if (e.target === authModal) closeAuthModal();
});

ensurePreviewContainers();
updateAuthUI();

async function initApp() {
  await loadRuntimeConfig();
  await loadOptions();
  initMap();
}

initApp();
