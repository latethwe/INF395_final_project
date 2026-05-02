const resultNode = document.getElementById("result");
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

let selectedFiles = [];
let linkedImageUrls = [];
let rcOptions = ["Not selected"];
let map;
let marker;
let lastListingPrice = null;

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
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)}%`;
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
  const s = String(v || "");
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
    "Первый этаж": "First floor",
    "Последний этаж": "Top floor",
  };
  return map[s] || s;
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

  const buildingTypeMap = {
    "монолитный": "monolithic",
    "кирпичный": "brick",
    "панельный": "panel",
    "иной": "other",
  };

  if (key === "district" || key.includes("район")) return districtMap[raw] || raw;
  if (key === "building_type" || key.includes("тип дома")) return buildingTypeMap[raw] || raw;
  return raw || "—";
}

function districtDisplayName(v) {
  return (
    {
      "Алмалинский р-н": "Almaly District",
      "Ауэзовский р-н": "Auezov District",
      "Бостандыкский р-н": "Bostandyk District",
      "Жетысуский р-н": "Zhetysu District",
      "Медеуский р-н": "Medeu District",
      "Наурызбайский р-н": "Nauryzbay District",
      "Турксибский р-н": "Turksib District",
      "Алатауский р-н": "Alatau District",
    }[v] || v
  );
}

function buildingTypeDisplayName(v) {
  return (
    {
      "монолитный": "monolithic",
      "кирпичный": "brick",
      "панельный": "panel",
      "иной": "other",
    }[v] || v
  );
}

function renderFactorTable(items, kind) {
  const rows = (items || [])
    .filter((x) => !String(x.feature || "").toLowerCase().includes("condition"))
    .slice(0, 6)
    .map((x) => {
      const feature = translateFeatureLabel(x.feature_label || x.feature || "—");
      const value = translateFeatureValue(x.feature, x.value);
      const pct = fmtPct(x.impact_pct_ppm2);
      const kzt = `${formatMoney(x.impact_kzt_total || 0)} ₸`;
      return `<tr><td>${feature}</td><td>${value}</td><td class="${kind === "plus" ? "plus-cell" : "minus-cell"}">${pct}</td><td>${kzt}</td></tr>`;
    })
    .join("");

  return `
    <table class="factor-table">
      <thead><tr><th>Factor</th><th>Value</th><th>Impact</th><th>Contribution (₸)</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="4">No data</td></tr>`}</tbody>
    </table>
  `;
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
  if (!files.length) return;

  files.slice(0, 10).forEach((file, idx) => {
    const item = document.createElement("div");
    item.className = "preview-item";
    const img = document.createElement("img");
    img.src = URL.createObjectURL(file);
    img.alt = file.name;
    img.className = "preview-thumb";
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "preview-remove";
    removeBtn.textContent = "×";
    removeBtn.addEventListener("click", () => {
      selectedFiles.splice(idx, 1);
      renderLocalPhotoPreview(selectedFiles);
    });
    item.appendChild(img);
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

  host.innerHTML = `
    <p class="used-photo-title">Photos used by the model</p>
    <div class="image-preview-grid">
      ${urls.map((u) => `<a href="${u}" target="_blank" rel="noreferrer"><img class="preview-thumb" src="${u}" alt="used-photo"/></a>`).join("")}
    </div>
  `;
}

function ensureSelectHasValue(selectEl, value) {
  if (!selectEl || value == null || value === "") return;
  const str = String(value);
  const hasValue = Array.from(selectEl.options).some((o) => o.value === str);
  if (!hasValue) {
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
  if (!q) {
    setRcOptions(rcOptions);
    return;
  }
  const filtered = [rcOptions[0], ...rcOptions.slice(1).filter((x) => x.toLowerCase().includes(q))];
  setRcOptions(filtered);
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
    const newLat = Number(e.latlng.lat.toFixed(6));
    const newLon = Number(e.latlng.lng.toFixed(6));
    latInput.value = String(newLat);
    lonInput.value = String(newLon);
    marker.setLatLng([newLat, newLon]);
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
    if (value == null || value === "") return;
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

function renderExplainResult(data, listingPrice = null) {
  const prediction = data?.prediction || {};
  const why = data?.why_this_price || {};
  const renovation = data?.renovation || {};
  const currentBuildingType = paramsForm.elements.building_type?.value || "—";

  const plusItems = [...(why.top_positive || [])].filter((x) => !String(x.feature || "").toLowerCase().includes("condition"));
  const minusItems = [...(why.top_negative || [])].filter((x) => !String(x.feature || "").toLowerCase().includes("condition"));
  const hasBuildingType = plusItems.some((x) => x.feature === "building_type") || minusItems.some((x) => x.feature === "building_type");
  if (!hasBuildingType) {
    plusItems.push({ feature: "building_type", feature_label: "Building type", value: currentBuildingType, impact_pct_ppm2: 0, impact_kzt_total: 0 });
  }

  const listingPriceToShow = listingPrice ?? lastListingPrice;

  showResultHtml(`
    <div class="result-head-grid">
      <div class="result-card"><span>Estimated price</span><strong>${formatMoney(prediction.price)} ₸</strong></div>
      <div class="result-card"><span>Price per m²</span><strong>${formatMoney(prediction.price_per_m2)} ₸/m²</strong></div>
      <div class="result-card"><span>Listing price</span><strong>${listingPriceToShow == null ? "—" : `${formatMoney(listingPriceToShow)} ₸`}</strong></div>
      <div class="result-card"><span>Renovation</span><strong>${translateConditionLabel(renovation.condition_label || renovation.condition || "—")}</strong></div>
    </div>
    <div class="factor-grid">
      <section><h4>Positive factors</h4>${renderFactorTable(plusItems, "plus")}</section>
      <section><h4>Negative factors</h4>${renderFactorTable(minusItems, "minus")}</section>
    </div>
  `);
}

async function loadOptions() {
  try {
    const res = await fetch("/meta/options");
    if (!res.ok) return;
    const data = await res.json();

    districtSelect.innerHTML = "";
    for (const v of data.districts || []) {
      districtSelect.insertAdjacentHTML("beforeend", `<option value="${v}">${districtDisplayName(v)}</option>`);
    }

    buildingTypeSelect.innerHTML = `<option value="монолитный">${buildingTypeDisplayName("монолитный")}</option>`;
    for (const v of data.building_types || []) {
      buildingTypeSelect.insertAdjacentHTML("beforeend", `<option value="${v}">${buildingTypeDisplayName(v)}</option>`);
    }

    rcOptions = ["Not selected", ...(data.residential_complexes || [])];
    setRcOptions(rcOptions);
  } catch (_) {
    showResultHtml("Failed to load options", true);
  }
}

imagesInput.addEventListener("change", () => {
  const incoming = Array.from(imagesInput.files || []);
  if (!incoming.length) return;
  linkedImageUrls = [];
  const merged = [...selectedFiles, ...incoming];
  selectedFiles = merged.slice(0, 10);
  imagesInput.value = "";
  renderLocalPhotoPreview(selectedFiles);
});

rcSearch.addEventListener("input", (e) => {
  filterRcOptions(e.target.value);
});

paramsForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(paramsForm);
  if (selectedFiles.length > 0) lastListingPrice = null;

  const files = selectedFiles.slice(0, 10);
  if (files.length > 0) linkedImageUrls = [];
  fd.delete("images");
  for (const file of files) fd.append("images", file);

  const useManualPhotos = files.length > 0;
  if (!useManualPhotos && linkedImageUrls.length) fd.append("image_urls_json", JSON.stringify(linkedImageUrls));

  fd.set("object_type", "flat");
  fd.set("condition_norm", "unknown");

  updateDebugPayload("POST /explain (manual calculation)", {
    area: fd.get("area"), rooms: fd.get("rooms"), floor: fd.get("floor"), floors_total: fd.get("floors_total"),
    year_built: fd.get("year_built"), district: fd.get("district"), building_type: fd.get("building_type"),
    residential_complex: fd.get("residential_complex"), latitude: fd.get("latitude"), longitude: fd.get("longitude"),
    object_type: fd.get("object_type"), condition_norm: fd.get("condition_norm"),
    photo_source: useManualPhotos ? "manual_upload" : linkedImageUrls.length ? "from_listing_url" : "none",
    images_count: files.length, image_urls_json_count: useManualPhotos ? 0 : linkedImageUrls.length,
  });

  showResultHtml("Calculating price and generating explanation...");

  try {
    const res = await fetch("/explain", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) {
      showResultHtml(data.detail || "Calculation error", true);
      return;
    }
    const debugModel = data.debug_model_input || {};
    updateDebugPayload("POST /explain + payload_to_model", {
      request_to_api: {
        area: fd.get("area"), rooms: fd.get("rooms"), floor: fd.get("floor"), floors_total: fd.get("floors_total"),
        year_built: fd.get("year_built"), district: fd.get("district"), building_type: fd.get("building_type"),
        residential_complex: fd.get("residential_complex"), latitude: fd.get("latitude"), longitude: fd.get("longitude"),
        object_type: fd.get("object_type"), condition_norm: fd.get("condition_norm"),
      },
      photo_source: debugModel.photo_source || "unknown",
      manual_images_count: debugModel.manual_images_count ?? files.length,
      linked_images_count: debugModel.linked_images_count ?? 0,
      linked_used_image_urls: debugModel.linked_used_image_urls || [],
      total_images_used: debugModel.total_images_used ?? files.length,
    });
    renderExplainResult(data);
  } catch (_err) {
    showResultHtml("Server unavailable", true);
  }
});

urlForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(urlForm);
  fd.append("use_photos", "true");

  updateDebugPayload("POST /predict_by_url (Find button only)", {
    url: fd.get("url"),
    use_photos: fd.get("use_photos"),
  });

  showResultHtml("Parsing URL, filling fields, and calculating...");

  try {
    const res = await fetch("/predict_by_url", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) {
      showResultHtml(data.detail || "URL processing error", true);
      return;
    }

    const listing = data.listing || {};
    const explain = data.explain || null;
    const debugModel = data.debug_model_input || {};

    linkedImageUrls = Array.isArray(listing.used_image_urls) ? listing.used_image_urls : [];
    lastListingPrice = listing.price ?? null;
    selectedFiles = [];

    updateDebugPayload("POST /predict_by_url + payload_to_model (Find result)", {
      request_to_api: { url: fd.get("url"), use_photos: fd.get("use_photos") },
      payload_to_model: debugModel.payload_to_model || null,
      downloaded_images_count: debugModel.downloaded_images_count ?? 0,
      used_image_urls: debugModel.used_image_urls || [],
    });

    applyListingToForm(listing);
    renderUsedPhotos(linkedImageUrls);
    if (explain) {
      renderExplainResult(explain, listing.price ?? null);
    }
  } catch (_err) {
    showResultHtml("Server unavailable", true);
  }
});

ensurePreviewContainers();
loadOptions();
initMap();
