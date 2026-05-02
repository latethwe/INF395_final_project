const listNode = document.getElementById('historyList');
const modeFilter = document.getElementById('modeFilter');
const token = localStorage.getItem('access_token') || '';
let API_BASE = (window.__API_BASE_URL || '').replace(/\/+$/, '');
let allRows = [];

function resolveMediaUrl(url) {
  const raw = String(url || '').trim();
  if (!raw) return '';
  if (/^https?:\/\//i.test(raw)) return raw;
  if (raw.startsWith('/')) return `${API_BASE}${raw}`;
  return `${API_BASE}/${raw}`;
}

async function loadRuntimeConfig() {
  try {
    const res = await fetch('/runtime-config');
    if (!res.ok) return;
    const data = await res.json();
    const apiBase = String(data?.api_base_url || '').trim().replace(/\/+$/, '');
    if (apiBase) API_BASE = apiBase;
  } catch (_e) {}
}

function fmtMoney(v) {
  return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(v || 0)} ₸`;
}

function esc(s) {
  return String(s ?? '').replace(/[&<>\"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function districtDisplay(v) {
  const map = {
    'Алмалинский р-н': 'Almaly District',
    'Ауэзовский р-н': 'Auezov District',
    'Бостандыкский р-н': 'Bostandyk District',
    'Жетысуский р-н': 'Zhetysu District',
    'Медеуский р-н': 'Medeu District',
    'Наурызбайский р-н': 'Nauryzbay District',
    'Турксибский р-н': 'Turksib District',
    'Алатауский р-н': 'Alatau District',
  };
  return map[v] || v || '—';
}

function buildingTypeDisplay(v) {
  const map = { монолитный: 'monolithic', кирпичный: 'brick', панельный: 'panel', иной: 'other' };
  return map[v] || v || '—';
}

function renovationDisplay(v) {
  const s = String(v || '').toLowerCase();
  if (s.includes('свеж') || s === 'fresh') return 'fresh renovation';
  if (s.includes('сред') || s === 'average') return 'average condition';
  if (s.includes('треб') || s === 'needs') return 'needs renovation';
  return v || '—';
}

function factorRows(items = []) {
  const rows = items
    .filter((x) => !String(x.feature || '').toLowerCase().includes('condition'))
    .slice(0, 6)
    .map((x) => {
      const labelMap = {
        'Фото (визуальные признаки)': 'Photos (visual features)',
        'Возраст дома (лет)': 'Building age (years)',
        'Площадь (м²)': 'Area (m²)',
        'Относительный этаж': 'Relative floor',
        'Этажность дома': 'Total floors',
        'Этаж': 'Floor',
        'Район': 'District',
        'Тип дома': 'Building type',
        Комнат: 'Rooms',
      };
      const name = esc(labelMap[x.feature_label] || x.feature_label || x.feature || '—');
      let valRaw = x.value ?? '—';
      if ((x.feature === 'district' || x.feature_label === 'Район') && typeof valRaw === 'string') valRaw = districtDisplay(valRaw);
      if ((x.feature === 'building_type' || x.feature_label === 'Тип дома') && typeof valRaw === 'string')
        valRaw = buildingTypeDisplay(valRaw);
      const val = esc(valRaw);
      const pct = `${Number(x.impact_pct_ppm2 || 0).toFixed(1)}%`;
      const kzt = fmtMoney(x.impact_kzt_total || 0);
      return `<tr><td>${name}</td><td>${val}</td><td>${pct}</td><td>${kzt}</td></tr>`;
    })
    .join('');
  return rows || '<tr><td colspan="4">No factors</td></tr>';
}

function detailHtml(row) {
  const req = row.request_payload || {};
  const resp = row.response_payload || {};
  const explainPayload = resp.explain || resp;
  const pred = explainPayload.prediction || resp.prediction || {};
  const listing = resp.listing || {};
  const reno = explainPayload.renovation || resp.renovation || {};
  const why = explainPayload.why_this_price || resp.why_this_price || {};
  const usedUrls =
    (resp.debug_model_input && resp.debug_model_input.used_image_urls) ||
    (resp.debug_model_input && resp.debug_model_input.linked_used_image_urls) ||
    [];
  const imageNames = Array.isArray(req.image_names) ? req.image_names : [];
  const savedImageUrls = Array.isArray(req.saved_image_urls) ? req.saved_image_urls : [];

  const paramsBlock = `
    <div class="result-head-grid" style="margin-top:10px;">
      <div class="result-card"><span>Area</span><strong>${esc(req.area ?? listing.area ?? '—')}</strong></div>
      <div class="result-card"><span>Rooms</span><strong>${esc(req.rooms ?? listing.rooms ?? '—')}</strong></div>
      <div class="result-card"><span>Floor</span><strong>${esc(req.floor ?? listing.floor ?? '—')} / ${esc(req.floors_total ?? listing.floors_total ?? '—')}</strong></div>
      <div class="result-card"><span>Year built</span><strong>${esc(req.year_built ?? listing.year_built ?? '—')}</strong></div>
      <div class="result-card"><span>District</span><strong>${esc(districtDisplay(req.district ?? listing.district))}</strong></div>
      <div class="result-card"><span>Building type</span><strong>${esc(buildingTypeDisplay(req.building_type ?? listing.building_type))}</strong></div>
      <div class="result-card"><span>Residential complex</span><strong>${esc(req.residential_complex ?? listing.residential_complex ?? '—')}</strong></div>
      <div class="result-card"><span>Coordinates</span><strong>${esc(req.latitude ?? listing.latitude ?? '—')}, ${esc(req.longitude ?? listing.longitude ?? '—')}</strong></div>
    </div>
  `;

  const photosBlock = usedUrls.length
    ? `<div style="margin-top:10px;"><strong>Photos used</strong><div class="image-preview-grid">${usedUrls
        .map((u) => {
          const media = resolveMediaUrl(u);
          return `<a href="${media}" target="_blank" rel="noreferrer"><img class="preview-thumb" src="${media}" alt="photo"/></a>`;
        })
        .join('')}</div></div>`
    : savedImageUrls.length
    ? `<div style="margin-top:10px;"><strong>Uploaded photos</strong><div class="image-preview-grid">${savedImageUrls
        .map((u) => {
          const media = resolveMediaUrl(u);
          return `<a href="${media}" target="_blank" rel="noreferrer"><img class="preview-thumb" src="${media}" alt="photo"/></a>`;
        })
        .join('')}</div></div>`
    : `<div style="margin-top:10px;"><strong>Uploaded image names:</strong> ${imageNames.length ? esc(imageNames.join(', ')) : '—'}</div>`;

  return `
    <div style="margin-top:10px;">
      <div class="result-head-grid">
        <div class="result-card"><span>Mode</span><strong>${esc(row.mode)}</strong></div>
        <div class="result-card"><span>Predicted price</span><strong>${fmtMoney(row.predicted_price || pred.price || 0)}</strong></div>
        <div class="result-card"><span>Predicted price/m²</span><strong>${fmtMoney(row.predicted_price_per_m2 || pred.price_per_m2 || 0)}</strong></div>
        <div class="result-card"><span>Renovation</span><strong>${esc(renovationDisplay(reno.condition_label || reno.condition))}</strong></div>
      </div>
      ${row.source_url ? `<div style="margin-top:8px;"><strong>Source URL:</strong> <a href="${esc(row.source_url)}" target="_blank">open listing</a></div>` : ''}
      ${paramsBlock}
      ${photosBlock}
      <div class="factor-grid" style="margin-top:10px;">
        <section>
          <h4>Positive factors</h4>
          <table class="factor-table"><thead><tr><th>Factor</th><th>Value</th><th>Impact</th><th>Contribution</th></tr></thead><tbody>${factorRows(
            why.top_positive || []
          )}</tbody></table>
        </section>
        <section>
          <h4>Negative factors</h4>
          <table class="factor-table"><thead><tr><th>Factor</th><th>Value</th><th>Impact</th><th>Contribution</th></tr></thead><tbody>${factorRows(
            why.top_negative || []
          )}</tbody></table>
        </section>
      </div>
      <details style="margin-top:10px;"><summary>Raw JSON</summary><pre>${esc(JSON.stringify(row, null, 2))}</pre></details>
    </div>
  `;
}

function renderHistoryList(rows) {
  if (!rows.length) {
    listNode.innerHTML = 'No history records yet.';
    return;
  }

  listNode.innerHTML = rows
    .map(
      (h) => `
        <article style="padding:12px;border:1px solid #d3dde3;border-radius:10px;background:#fff;margin-top:10px;">
          <div><strong>${esc(h.mode)}</strong> • ${new Date(h.created_at).toLocaleString()}</div>
          <div>Predicted: ${fmtMoney(h.predicted_price)} | ${fmtMoney(h.predicted_price_per_m2)} /m²</div>
          <button type="button" class="small-cta" data-id="${h.id}" style="margin-top:8px;">View details</button>
          <section id="detail-${h.id}"></section>
        </article>
      `
    )
    .join('');

  listNode.querySelectorAll('button[data-id]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-id');
      const panel = document.getElementById(`detail-${id}`);
      if (panel.dataset.loaded === '1') {
        panel.innerHTML = panel.innerHTML ? '' : panel.dataset.cached || '';
        return;
      }
      const detailRes = await fetch(`${API_BASE}/history/${id}`, { headers: { Authorization: `Bearer ${token}` } });
      const row = await detailRes.json();
      if (!detailRes.ok) return;
      const html = detailHtml(row);
      panel.dataset.loaded = '1';
      panel.dataset.cached = html;
      panel.innerHTML = html;
    });
  });
}

function applyFilters() {
  const mode = modeFilter.value;
  const filtered = allRows.filter((h) => {
    const isUrl = h.mode === 'predict_by_url';
    const isManual = h.mode === 'explain';
    if (mode === 'url' && !isUrl) return false;
    if (mode === 'manual' && !isManual) return false;
    return true;
  });
  renderHistoryList(filtered);
}

async function loadHistory() {
  if (!token) {
    listNode.innerHTML = 'Sign in first on the home page to view history.';
    return;
  }

  const res = await fetch(`${API_BASE}/history`, { headers: { Authorization: `Bearer ${token}` } });
  const rows = await res.json();
  if (!res.ok) {
    listNode.innerHTML = esc(rows.detail || 'Failed to load history');
    return;
  }
  allRows = Array.isArray(rows) ? rows : [];
  applyFilters();
}

modeFilter.addEventListener('change', applyFilters);
async function initHistoryPage() {
  await loadRuntimeConfig();
  await loadHistory();
}
initHistoryPage();
