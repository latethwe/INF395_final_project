const API_BASE = "";

const healthStatus = document.getElementById("healthStatus");
const predictForm = document.getElementById("predictForm");
const urlForm = document.getElementById("urlForm");
const imagesInput = document.getElementById("imagesInput");
const usePhotosInput = document.getElementById("usePhotosInput");
const preview = document.getElementById("preview");
const errorBox = document.getElementById("errorBox");
const rawJson = document.getElementById("rawJson");
const resultCards = document.getElementById("resultCards");
const comparables = document.getElementById("comparables");
const latInput = document.getElementById("latInput");
const lonInput = document.getElementById("lonInput");
const districtSearch = document.getElementById("districtSearch");
const districtSelect = document.getElementById("districtSelect");
const buildingTypeSearch = document.getElementById("buildingTypeSearch");
const buildingTypeSelect = document.getElementById("buildingTypeSelect");
const rcSearch = document.getElementById("rcSearch");
const rcSelect = document.getElementById("rcSelect");
const explainSummary = document.getElementById("explainSummary");
const plusTableWrap = document.getElementById("plusTableWrap");
const minusTableWrap = document.getElementById("minusTableWrap");
const renoRecs = document.getElementById("renoRecs");
const renoSummary = document.getElementById("renoSummary");
const renoSignals = document.getElementById("renoSignals");
const engToggle = document.getElementById("engToggle");
const engWrap = document.getElementById("engWrap");
const diagBox = document.getElementById("diagBox");

let districtOptions = [];
let buildingTypeOptions = [];
let rcOptions = [];
let lastEndpoint = "—";
let lastDurationMs = null;

function fmtMoney(x) {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return "—";
  return `${Math.round(Number(x)).toLocaleString("ru-RU")} ₸`;
}

function fmtPpm2(x) {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return "—";
  return `${Math.round(Number(x)).toLocaleString("ru-RU")} ₸/м²`;
}

function fmtPct(x) {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return "—";
  const v = Number(x);
  return `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
}

function showError(msg) {
  errorBox.classList.remove("hidden");
  errorBox.textContent = msg;
}

function clearError() {
  errorBox.classList.add("hidden");
  errorBox.textContent = "";
}

function metricCard(label, value, delta = "") {
  return `<div class="card">
    <div class="k">${label}</div>
    <div class="v">${value}</div>
    <div class="${delta.startsWith("+") ? "delta-pos" : "delta-neg"}">${delta || ""}</div>
  </div>`;
}

function toText(v) {
  if (v === null || v === undefined) return "";
  if (typeof v === "number") return Number(v).toFixed(2).replace(/\.00$/, "");
  return String(v);
}

function impactsToTable(items = []) {
  if (!items.length) return `<div class="muted" style="padding:10px;">Нет данных</div>`;
  const rows = items
    .map((it) => {
      const factor = toText(it.feature_label || it.feature || "");
      const value = toText(it.value);
      const pct = it.impact_pct_ppm2 != null ? `${Number(it.impact_pct_ppm2).toFixed(1)}%` : "—";
      const kzt = it.impact_kzt_total != null ? fmtMoney(it.impact_kzt_total) : "—";
      const reason = toText(it.reason || "");
      return `<tr><td>${factor}</td><td>${value}</td><td>${pct}</td><td>${kzt}</td><td>${reason}</td></tr>`;
    })
    .join("");
  return `<table>
    <thead><tr><th>Фактор</th><th>Значение</th><th>Влияние %</th><th>Влияние ₸</th><th>Причина</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function resolveComparableImageSrc(imageValue) {
  if (!imageValue || typeof imageValue !== "string") return null;
  if (imageValue.startsWith("http://") || imageValue.startsWith("https://")) return imageValue;
  if (imageValue.startsWith("/data/images/")) return imageValue;
  if (imageValue.startsWith("data/images/")) return "/" + imageValue;
  const mark = "/data/images/";
  const i = imageValue.indexOf(mark);
  if (i >= 0) return imageValue.slice(i);
  return null;
}

function setInputValue(name, value) {
  const el = predictForm.elements[name];
  if (!el) return;
  if (value === null || value === undefined || value === "") return;
  el.value = String(value);
}

function ensureSelectHasValue(selectEl, value, label = null) {
  if (!selectEl || value === null || value === undefined || value === "") return;
  const str = String(value);
  const has = Array.from(selectEl.options).some((o) => o.value === str);
  if (!has) {
    const opt = document.createElement("option");
    opt.value = str;
    opt.textContent = label || str;
    selectEl.appendChild(opt);
  }
  selectEl.value = str;
}

function applyListingToForm(listing = {}) {
  setInputValue("area", listing.area);
  setInputValue("rooms", listing.rooms);
  setInputValue("floor", listing.floor);
  setInputValue("floors_total", listing.floors_total);
  setInputValue("year_built", listing.year_built);

  ensureSelectHasValue(districtSelect, listing.district);
  ensureSelectHasValue(buildingTypeSelect, listing.building_type);
  ensureSelectHasValue(rcSelect, listing.residential_complex, listing.residential_complex || "Не выбрано");

  if (listing.latitude !== null && listing.latitude !== undefined && listing.longitude !== null && listing.longitude !== undefined) {
    const lat = Number(listing.latitude);
    const lon = Number(listing.longitude);
    if (Number.isFinite(lat) && Number.isFinite(lon)) {
      latInput.value = lat.toFixed(6);
      lonInput.value = lon.toFixed(6);
      marker.setLatLng([lat, lon]);
      map.setView([lat, lon], Math.max(map.getZoom(), 13));
    }
  }
}

function renderComparables(items = []) {
  comparables.innerHTML = "";
  if (!items.length) {
    comparables.innerHTML = `<p class="muted">Похожие объявления не найдены.</p>`;
    return;
  }
  for (const it of items.slice(0, 3)) {
    const img = resolveComparableImageSrc(it.image);
    const url = it.url || "#";
    const el = document.createElement("article");
    el.className = "comp";
    el.innerHTML = `
      ${img ? `<img src="${img}" alt="Comparable photo" />` : `<div class="img-miss">Нет фото</div>`}
      <div class="meta">
        <strong>${fmtMoney(it.price)}</strong>
        <span>${fmtPpm2(it.price_per_m2)}</span>
        <span>Площадь: ${it.area ?? "—"} м²</span>
        <span>Комнат: ${it.rooms ?? "—"}</span>
        <span>Район: ${it.district ?? "—"}</span>
        <span>ЖК: ${it.residential_complex ?? "—"}</span>
        ${it.distance_km != null ? `<span>Дистанция: ${Number(it.distance_km).toFixed(2)} км</span>` : ""}
        <a href="${url}" target="_blank" rel="noreferrer">Открыть объявление</a>
      </div>
    `;
    comparables.appendChild(el);
  }
}

function renderPrediction(out) {
  const pred = out?.prediction || out || {};
  const ppm2 = pred.price_per_m2;
  const price = pred.price;
  const area = pred.area ?? Number(predictForm.elements.area.value || 0);

  resultCards.innerHTML = [
    metricCard("Цена модели", fmtMoney(price)),
    metricCard("₸/м² модели", fmtPpm2(ppm2)),
    metricCard("Площадь", `${Number(area || 0).toFixed(1)} м²`),
    metricCard("Модель", "v2 + CLIP"),
  ].join("");

  renderComparables(pred.comparables || out.comparables || []);
  const summary = out?.why_this_price?.summary || {};
  explainSummary.textContent =
    out?.why_this_price
      ? `Главный плюс: ${summary.biggest_plus || "—"} | Главный минус: ${summary.biggest_minus || "—"}`
      : 'Для таблицы факторов нажми "Оценить + Explain".';
  plusTableWrap.innerHTML = impactsToTable(out?.why_this_price?.top_positive || []);
  minusTableWrap.innerHTML = impactsToTable(out?.why_this_price?.top_negative || []);
  renderRecommendations(out?.recommendations || [], out);
  renderRenovation(out?.renovation || null);
  renderDiagnostics(out);
  rawJson.textContent = JSON.stringify(out, null, 2);
}

function renderByUrl(out) {
  const listing = out?.listing || {};
  const pred = out?.prediction || {};
  const priceDiff = out?.difference?.price || {};
  const ppm2Diff = out?.difference?.price_per_m2 || {};

  resultCards.innerHTML = [
    metricCard("Цена в объявлении", fmtMoney(listing.price)),
    metricCard("Цена модели", fmtMoney(pred.price), fmtPct(priceDiff.diff_pct)),
    metricCard("Разница, ₸", fmtMoney(priceDiff.diff), fmtPct(priceDiff.diff_pct)),
    metricCard("Разница, ₸/м²", fmtPpm2(ppm2Diff.diff), fmtPct(ppm2Diff.diff_pct)),
  ].join("");

  renderComparables(pred.comparables || []);
  applyListingToForm(listing);
  explainSummary.textContent = "По оценке по ссылке explain-факторы не запрашиваются.";
  plusTableWrap.innerHTML = `<div class="muted" style="padding:10px;">Запусти режим explain в левой форме.</div>`;
  minusTableWrap.innerHTML = `<div class="muted" style="padding:10px;">Запусти режим explain в левой форме.</div>`;
  renderRecommendations([], out);
  renderRenovation(null);
  renderDiagnostics(out);
  rawJson.textContent = JSON.stringify(out, null, 2);
}

function renderRecommendations(items = [], out = null) {
  if (!items.length) {
    const noPhotos = usePhotosInput && !usePhotosInput.checked;
    const reason = out?.renovation
      ? "Модель не увидела явных сигналов для рекомендаций."
      : noPhotos
      ? "Рекомендации пустые: фото выключены."
      : "Нет рекомендаций (или не запрошен explain).";
    renoRecs.innerHTML = `<div class="muted">${reason}</div>`;
    return;
  }
  renoRecs.innerHTML = items
    .map((r) => {
      const title = toText(r.title || "Рекомендация");
      const why = toText(r.why || "");
      const pr = toText(r.priority || "");
      const up = Array.isArray(r.expected_uplift_pct) && r.expected_uplift_pct.length === 2
        ? `Эффект: ~${r.expected_uplift_pct[0]}–${r.expected_uplift_pct[1]}%`
        : "";
      const meta = [pr, up].filter(Boolean).join(" • ");
      return `<article class="rec-item">
        <strong>${title}</strong>
        ${meta ? `<div class="meta">${meta}</div>` : ""}
        ${why ? `<div>${why}</div>` : ""}
      </article>`;
    })
    .join("");
}

function renderRenovation(renovation) {
  if (!renovation) {
    renoSummary.innerHTML = `
      ${metricCard("Оценка", "—")}
      ${metricCard("Уверенность", "—")}
      ${metricCard("Комментарий", "Нет данных")}
    `;
    renoSignals.innerHTML = "Запусти режим explain, чтобы увидеть анализ фото.";
    return;
  }

  renoSummary.innerHTML = `
    ${metricCard("Оценка", toText(renovation.condition_label || renovation.condition || "—"))}
    ${metricCard("Уверенность", renovation.confidence != null ? Number(renovation.confidence).toFixed(2) : "—")}
    ${metricCard("Комментарий", toText(renovation.confidence_note || "—"))}
  `;

  const signals = Array.isArray(renovation.signals) ? renovation.signals : [];
  const notes = Array.isArray(renovation.notes) ? renovation.notes : [];
  if (!signals.length && !notes.length) {
    renoSignals.innerHTML = "Сигналы по фото не выделены.";
    return;
  }

  const sigHtml = signals.length
    ? `<strong>Сигналы:</strong><ul class="signal-list">${signals
        .map((s) => {
          const lbl = toText(s.label || s.tag || "signal");
          const conf = s.confidence != null ? ` (${Number(s.confidence).toFixed(2)})` : "";
          const low = s.low_confidence ? " [низкая уверенность]" : "";
          return `<li>${lbl}${conf}${low}</li>`;
        })
        .join("")}</ul>`
    : "";

  const notesHtml = notes.length ? `<strong>Notes:</strong><ul class="signal-list">${notes.map((n) => `<li>${toText(n)}</li>`).join("")}</ul>` : "";
  renoSignals.innerHTML = [sigHtml, notesHtml].filter(Boolean).join("<br/>");
}

function renderDiagnostics(out) {
  const size = JSON.stringify(out || {}).length;
  const comps = (out?.prediction?.comparables || out?.comparables || []).length || 0;
  diagBox.innerHTML = `
    endpoint: <strong>${lastEndpoint}</strong><br/>
    response_time: <strong>${lastDurationMs != null ? `${lastDurationMs} ms` : "—"}</strong><br/>
    response_size: <strong>${size.toLocaleString("ru-RU")} bytes</strong><br/>
    comparables: <strong>${comps}</strong>
  `;
}

async function apiHealth() {
  try {
    const r = await fetch(`${API_BASE}/health`);
    const j = await r.json();
    healthStatus.textContent = `API: ok (${j.model})`;
  } catch (_e) {
    healthStatus.textContent = "API: offline";
  }
}

function setSelectOptions(selectEl, options, allowEmpty = false, emptyLabel = "Не выбрано") {
  const current = selectEl.value;
  const list = allowEmpty ? ["", ...options] : options;
  selectEl.innerHTML = list
    .map((x) => `<option value="${x}">${x || emptyLabel}</option>`)
    .join("");
  if (list.includes(current)) {
    selectEl.value = current;
  } else if (list.length) {
    selectEl.value = list[0];
  }
}

function filterAndSet(searchEl, selectEl, source, allowEmpty = false) {
  const q = String(searchEl.value || "").trim().toLowerCase();
  const filtered = q ? source.filter((x) => x.toLowerCase().includes(q)) : source.slice();
  setSelectOptions(selectEl, filtered, allowEmpty);
}

async function loadMetaOptions() {
  try {
    const r = await fetch(`${API_BASE}/meta/options`);
    if (!r.ok) throw new Error("meta/options failed");
    const j = await r.json();
    districtOptions = Array.isArray(j.districts) ? j.districts : [];
    buildingTypeOptions = Array.isArray(j.building_types) ? j.building_types : [];
    rcOptions = Array.isArray(j.residential_complexes) ? j.residential_complexes : [];
  } catch (_e) {
    districtOptions = [
      "Алмалинский р-н",
      "Ауэзовский р-н",
      "Бостандыкский р-н",
      "Жетысуский р-н",
      "Медеуский р-н",
      "Наурызбайский р-н",
      "Турксибский р-н",
      "Алатауский р-н",
    ];
    buildingTypeOptions = ["монолитный", "кирпичный", "панельный", "иной"];
    rcOptions = [];
  }
  setSelectOptions(districtSelect, districtOptions);
  setSelectOptions(buildingTypeSelect, buildingTypeOptions);
  setSelectOptions(rcSelect, rcOptions, true);
  if (!rcOptions.length) {
    rcSearch.placeholder = "ЖК список пуст (проверь rc_names/almaty_rc_names.csv)";
  }
}

predictForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError();
  const submitter = e.submitter;
  const mode = submitter?.dataset?.mode || "predict";
  const endpoint = mode === "explain" ? "/explain" : "/predict";

  const fd = new FormData();
  for (const k of [
    "area",
    "rooms",
    "floor",
    "floors_total",
    "year_built",
    "district",
    "building_type",
    "residential_complex",
    "latitude",
    "longitude",
  ]) {
    const v = predictForm.elements[k].value;
    if (v !== "") fd.append(k, v);
  }

  const usePhotos = Boolean(usePhotosInput?.checked);
  if (usePhotos) {
    for (const f of Array.from(imagesInput.files || []).slice(0, 10)) {
      fd.append("images", f, f.name);
    }
  }

  try {
    submitter.disabled = true;
    submitter.textContent = "Выполняется...";
    const t0 = performance.now();
    const r = await fetch(`${API_BASE}${endpoint}`, { method: "POST", body: fd });
    const body = await r.text();
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}\n${body}`);
    const out = JSON.parse(body);
    lastEndpoint = endpoint;
    lastDurationMs = Math.round(performance.now() - t0);
    renderPrediction(out);
  } catch (err) {
    showError(String(err.message || err));
  } finally {
    submitter.disabled = false;
    submitter.textContent = mode === "explain" ? "Оценить + Explain" : "Оценить";
  }
});

urlForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearError();
  const btn = urlForm.querySelector("button");
  const fd = new FormData(urlForm);
  const urlUsePhotos = urlForm.querySelector('input[name="use_photos"]');
  fd.set("use_photos", urlUsePhotos && urlUsePhotos.checked ? "true" : "false");
  try {
    btn.disabled = true;
    btn.textContent = "Парсинг...";
    const t0 = performance.now();
    const r = await fetch(`${API_BASE}/predict_by_url`, { method: "POST", body: fd });
    const body = await r.text();
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}\n${body}`);
    const out = JSON.parse(body);
    lastEndpoint = "/predict_by_url";
    lastDurationMs = Math.round(performance.now() - t0);
    renderByUrl(out);
  } catch (err) {
    showError(String(err.message || err));
  } finally {
    btn.disabled = false;
    btn.textContent = "Оценить по ссылке";
  }
});

imagesInput.addEventListener("change", () => {
  preview.innerHTML = "";
  const files = Array.from(imagesInput.files || []).slice(0, 10);
  for (const f of files) {
    const img = document.createElement("img");
    img.src = URL.createObjectURL(f);
    img.alt = f.name;
    preview.appendChild(img);
  }
});

districtSearch.addEventListener("input", () => filterAndSet(districtSearch, districtSelect, districtOptions));
buildingTypeSearch.addEventListener("input", () =>
  filterAndSet(buildingTypeSearch, buildingTypeSelect, buildingTypeOptions),
);
rcSearch.addEventListener("input", () => filterAndSet(rcSearch, rcSelect, rcOptions, true));
engToggle.addEventListener("change", () => {
  if (engToggle.checked) {
    engWrap.classList.remove("hidden");
  } else {
    engWrap.classList.add("hidden");
  }
});

const map = L.map("map").setView([43.238949, 76.889709], 12);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap contributors",
}).addTo(map);
let marker = L.marker([43.238949, 76.889709]).addTo(map);

map.on("click", (e) => {
  const { lat, lng } = e.latlng;
  latInput.value = lat.toFixed(6);
  lonInput.value = lng.toFixed(6);
  marker.setLatLng([lat, lng]);
});

apiHealth();
loadMetaOptions();
renderRecommendations([], null);
renderRenovation(null);
renderDiagnostics({});
