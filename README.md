# KrishaVision: Multimodal Apartment Valuation Platform

## 1. Project Area
AI Systems / PropTech (Real Estate Analytics)

## 2. Problem Statement
Apartment listing prices are often subjective and inconsistent. Manual appraisal is slow and depends on expert judgment, while many online calculators ignore apartment photo quality/renovation state. This causes pricing errors and weak negotiation confidence.

## 3. Proposed Solution
KrishaVision combines:
- tabular features (area, rooms, district, floor, total floors, year built, coordinates, residential complex)
- visual signals from apartment photos (OpenCLIP)

The platform predicts:
- total price
- price per m²
- renovation condition from photos (fresh / average / needs) with confidence

And provides:
- factor-based explanation (positive/negative contributions)
- renovation signal
- URL-based auto-fill and valuation from Krisha listing links
- user auth + personal valuation history

## 4. Target Users
- Apartment buyers and sellers
- Real estate agents/brokers
- Real estate analysts and researchers

## 5. Technology Stack
- Frontend: HTML, CSS, JavaScript, Leaflet
- Backend: FastAPI, Uvicorn
- ML/AI: CatBoost, OpenCLIP, PyTorch
- Data/Storage: PostgreSQL (Neon), Parquet/CSV/JSON, local runtime images
- Integrations: Krisha parsing, REST API

## 6. Key Features
1. Manual valuation from apartment parameters + uploaded photos
2. URL valuation (`/predict_by_url`) with auto-filled fields
3. Explainability tables (positive/negative factors)
4. Renovation state signal from visual features
5. User login/password auth and My History page with detailed record view

## 7. Repository Structure
```text
apps/
  backend/
    app.py
    core/
    db/
    ml/
    models/
    services/
  frontend/
    index.html
    history.html
    assets/
archive/
  ml_research/
data/
  index/
  images/   (runtime-generated)
```

## 8. Installation
### 8.1 Runtime (deployment)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

### 8.2 Dev/Research extras
```bash
pip install -r requirements-dev.txt
```

## 9. Environment Variables
Create `.env` from `.env.example`.

Minimum required:
```env
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST/DBNAME?sslmode=require
JWT_SECRET=replace_with_strong_secret
JWT_ALG=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

Optional deployment controls:
```env
CORS_ORIGINS=*
ML_ENABLED=true
EXTERNAL_ML_API_BASE=
HF_TOKEN=
```

## 10. Run Locally
```bash
python -m uvicorn apps.backend.app:app --reload
```

Open:
- UI: `http://127.0.0.1:8000/home`
- History: `http://127.0.0.1:8000/my-history`
- API docs: `http://127.0.0.1:8000/docs`

## 11. API Endpoints (Core)
- `GET /home` - web UI
- `GET /my-history` - history page
- `GET /meta/options` - dropdown options
- `POST /explain` - manual valuation + explanation
- `POST /predict_by_url` - URL parsing + valuation
- `GET /history` / `GET /history/{id}` - user history
- `POST /auth/register` / `POST /auth/login` / `GET /auth/me`
- `GET /health`
- `GET /runtime-config`

## 12. Deployment Modes
### A) Single-host deployment (recommended for demo)
Frontend + backend on one Railway service:
- `ML_ENABLED=true` if memory allows
- or `ML_ENABLED=false` to keep service lightweight

### B) Hybrid mode (stable on low-memory cloud)
- Railway hosts UI/auth/history/backend shell
- ML runs locally
- Local ML is exposed via Cloudflare tunnel
- Railway sets `EXTERNAL_ML_API_BASE=https://<tunnel-url>` and `ML_ENABLED=false`

The frontend reads `/runtime-config` and automatically routes inference requests to `EXTERNAL_ML_API_BASE`.

## 13. Notes and Limitations
- `apps/backend/models/*` must exist for local ML inference mode.
- `data/images/` is runtime-only (not for git).
- Parsing robustness depends on source listing page structure.
- Free-tier hosting may fail with OOM for full ML loading.

## 14. Team Members
1. Zhassulan Tursynbay - ML Engineer / Backend Developer  
   Student ID: 230103029  
   Email: 230103029@sdu.edu.kz

2. Nuriya Sultanseitova - Frontend / UX Integration  
   Student ID: 230103360  
   Email: 230103360@sdu.edu.kz

3. Nursultan Zhanbulat - Data Engineering / Web Parsing  
   Student ID: 230103251  
   Email: 230103251@sdu.edu.kz

4. Iliyas Malibekov - QA / Deployment  
   Student ID: 230103344  
   Email: 230103344@sdu.edu.kz
