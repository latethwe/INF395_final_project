# KrishaVision — Multimodal Apartment Valuation Platform

Predicts apartment price, price per m², and renovation condition in Almaty — from tabular parameters **and listing photos**.

Adding image features on top of a tabular baseline cut **price MAE by 8.0%** and **price-per-m² MAE by 11.1%** on a time-based test split.

**Stack:** CatBoost · OpenCLIP ViT-B-32 · FastAPI · PostgreSQL · deployed on Railway

---

## Demo

<!-- Put a 15-25s screen recording at docs/demo.gif before pushing. Without the file this image will render broken. -->
![KrishaVision demo](docs/demo.gif)

Paste a Krisha listing URL → fields auto-fill → the model returns price, price per m², renovation condition inferred from the photos, and a breakdown of which factors pushed the price up or down.

📹 [Full walkthrough and screenshots (Google Drive)](https://drive.google.com/drive/folders/1TG7KZbHpzIwhDitHvP5e9ONlmAKc3JfK?usp=sharing)

---

## Results

Two models, same data, same **time-based split** (train on older listings, test on newer ones — no random shuffling, no look-ahead).

**Test set**

| Metric | v1 — tabular only | v2 — tabular + CLIP | Change |
|---|---|---|---|
| MAE, price | 6,930,742 ₸ | **6,375,421 ₸** | **−8.0%** |
| MAE, price per m² | 87,248 ₸ | **77,579 ₸** | **−11.1%** |
| RMSE, price | 23,141,869 ₸ | 22,812,403 ₸ | −1.4% |
| RMSE, price per m² | 231,086 ₸ | 226,940 ₸ | −1.8% |

**Validation set**

| Metric | v1 — tabular only | v2 — tabular + CLIP | Change |
|---|---|---|---|
| MAE, price | 7,563,377 ₸ | 7,360,420 ₸ | −2.7% |
| MAE, price per m² | 90,439 ₸ | 85,894 ₸ | −5.0% |

**How to read this.** MAE drops substantially while RMSE barely moves. Photos improve the *typical* valuation — they tell the model whether a flat is freshly renovated or falling apart, which tabular fields never captured. They do **not** fix the tail: luxury and non-standard properties still produce large errors, and those dominate RMSE. Honest conclusion: visual features are worth their cost for the mass market, not for outliers.

Raw metrics live in `apps/backend/models/v2_metadata.json` and `archive/ml_research/models/v1_metadata.json` — the numbers above are copied from those files, not from a notebook run.

---

## Data

- **~25,000 listings**, **~200,000 photos** (7–10 per listing), collected from Krisha with a custom scraping pipeline (collect IDs → fetch details → download images).
- Split by `collected_at`: older listings train, newer listings test. This mirrors how the model would actually be used — predicting on listings it has never seen, posted after everything it learned from.
- Renovation labels in listings are sparse and often contradict the photos (a flat described as "new renovation" showing a worn interior). The model learns condition from the images themselves and flags the mismatch.

---

## Method

**Target:** `log_price_per_m2` (log-transformed, then converted back to price for display).

**Tabular features:** area, rooms, floor, floors_total, floor_ratio, is_first, is_last, building_age, latitude, longitude, has_geo, has_residential_complex, condition_confidence, district, building_type, residential_complex, object_type, condition_norm, condition_source.

**Visual features:** OpenCLIP `ViT-B-32` (`laion2b_s34b_b79k`). Up to 10 photos per listing, each embedding L2-normalized, then mean-pooled and normalized again. The pooled vector is concatenated with the tabular features.

**Model:** CatBoost regressor, `catboost_tabular_plus_clip_vitb32.cbm`.

**Explainability:** per-factor positive/negative contributions to the predicted price (location, condition, area, floor, and so on), surfaced in the UI.

---

## Problem

Listing prices in Almaty are inconsistent and largely subjective. Manual appraisal is slow and expert-dependent, while online calculators ignore the single most visible driver of value: the actual state of the apartment. Two flats with identical area, district, and floor can differ by millions of tenge — and the only evidence of that difference is in the photos.

## Target users

Buyers and sellers · real estate agents · analysts and researchers

---

## Key features

1. Manual valuation from apartment parameters + uploaded photos
2. Valuation straight from a Krisha listing URL (`/predict_by_url`) with auto-filled fields
3. Factor-based explanation of the predicted price (positive / negative contributions)
4. Renovation condition inferred from photos (fresh / average / needs work) with a confidence score
5. Auth (login/password) and a personal valuation history page

## Tech stack

- **Frontend:** HTML, CSS, JavaScript, Leaflet
- **Backend:** FastAPI, Uvicorn
- **ML:** CatBoost, OpenCLIP, PyTorch
- **Data:** PostgreSQL (Neon), Parquet/CSV/JSON
- **Integrations:** Krisha parsing, REST API

---

## Repository structure

```text
apps/
  backend/
    app.py
    core/          # config, security
    db/            # models, schemas, session
    ml/            # v2_infer.py
    models/        # catboost_tabular_plus_clip_vitb32.cbm, v2_metadata.json
    services/      # krisha_ad.py
  frontend/
    index.html
    history.html
    assets/
archive/
  ml_research/     # v1 baseline model + metadata
data/
  index/
  images/          # runtime-generated
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

Dev/research extras:

```bash
pip install -r requirements-dev.txt
```

## Environment variables

Create `.env` from `.env.example`.

```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
JWT_SECRET=replace_with_strong_secret
JWT_ALG=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

Optional:

```env
CORS_ORIGINS=*
ML_ENABLED=true
EXTERNAL_ML_API_BASE=
HF_TOKEN=
```

## Run locally

```bash
python -m uvicorn apps.backend.app:app --reload
```

- UI: `http://127.0.0.1:8000/home`
- History: `http://127.0.0.1:8000/my-history`
- API docs: `http://127.0.0.1:8000/docs`

## API endpoints

| Endpoint | Purpose |
|---|---|
| `GET /home` | Web UI |
| `GET /my-history` | History page |
| `GET /meta/options` | Dropdown options |
| `POST /explain` | Manual valuation + explanation |
| `POST /predict_by_url` | URL parsing + valuation |
| `GET /history`, `GET /history/{id}` | User history |
| `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | Auth |
| `GET /health`, `GET /runtime-config` | Service info |

## Deployment

**A) Single host.** Frontend + backend on one Railway service. `ML_ENABLED=true` if memory allows, otherwise `false` to keep the service light.

**B) Hybrid (used in production).** Free-tier Railway cannot hold the CLIP + CatBoost stack in memory, so inference is split out:

- Railway hosts the UI, auth, history, and backend shell (`ML_ENABLED=false`)
- ML inference runs on a separate machine, exposed through a Cloudflare Tunnel
- Railway points at it via `EXTERNAL_ML_API_BASE=https://<tunnel-url>`
- The frontend reads `/runtime-config` and routes inference requests accordingly

## Limitations

- `apps/backend/models/*` must be present for local ML inference.
- `data/images/` is runtime-only and not tracked in git.
- Parsing depends on the structure of the source listing page and will break if it changes.
- Free-tier hosting will OOM if the full ML stack is loaded in-process — hence the hybrid mode above.
- Visual features improve typical error, not tail error (see Results).
