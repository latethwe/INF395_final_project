# KrishaVision: Multimodal Apartment Valuation Platform

## 1. Project Area
AI Systems / PropTech (Real Estate Analytics)

## 2. Problem Statement
Apartment listing prices are often subjective and inconsistent, making fair valuation difficult for buyers and sellers. Manual appraisal is slow and heavily dependent on expert judgment. Most simple calculators ignore visual apartment condition from photos, which strongly affects market value. This leads to pricing errors, weak negotiation confidence, and inefficient transactions.

## 3. Proposed Solution
KrishaVision is a multimodal valuation platform that combines:
- Tabular listing features (area, rooms, district, floor, total floors, year built, geo coordinates, residential complex)
- Visual features extracted from apartment photos via OpenCLIP

A CatBoost regressor predicts price per square meter and total apartment price. The system also provides:
- Explainability (positive/negative factor breakdown)
- Renovation-condition signal analysis from photos
- Comparable listings
- Automatic valuation by Krisha URL, including difference between listed and predicted price

## 4. Target Users
- Apartment buyers and sellers
- Real estate agents/brokers
- Real estate analysts and researchers

## 5. Technology Stack
- Frontend: HTML, CSS, JavaScript, Leaflet map
- Backend: FastAPI, Uvicorn
- ML/AI: CatBoost, OpenCLIP, PyTorch, NumPy, Pandas
- Storage: JSON/CSV/Parquet, local image folders
- Integrations: Krisha parsing, REST API
- Tools: Python, BeautifulSoup, requests, Jupyter, Git/GitHub

## 6. Key Features
1. Price prediction from apartment parameters + uploaded photos
2. Explain mode with positive/negative factor tables
3. Renovation/condition analysis from photos + practical signals
4. URL-based automatic valuation (parse listing, use photos, predict, compare listing vs model)

## 7. Current Project Structure
```text
apps/
  backend/
    app.py
    core/
    db/
    ml/
      v2_infer.py
    models/
      catboost_tabular_plus_clip_vitb32.cbm
      v2_metadata.json
    services/
      krisha_ad.py
  frontend/
    index.html
    assets/
      styles.css
      app.js
archive/
  ml_research/
data/
  index/
  images/   (runtime-generated)
```

## 8. How to Run
### 8.1 Requirements
- Python 3.10+
- macOS/Linux/Windows

### 8.2 Installation
```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

### 8.3 Environment
Create `.env` in project root:
```env
DATABASE_URL=sqlite:///./krisha_app.db
JWT_SECRET=change_me
JWT_ALG=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60
```

### 8.4 Start Backend
```bash
python -m uvicorn apps.backend.app:app --reload
```

Open:
- UI: http://127.0.0.1:8000/home
- API docs: http://127.0.0.1:8000/docs

## 9. Main API Endpoints
- `GET /home` - main web interface
- `GET /meta/options` - dropdown options (districts, building types, residential complexes)
- `POST /explain` - valuation + explanation from manual form
- `POST /predict_by_url` - automatic valuation by Krisha URL
- `GET /health` - service health check

## 10. Workflow
### A) URL-based flow
1. User pastes Krisha URL
2. Backend parses listing fields and photos
3. Model predicts valuation and explanation
4. UI auto-fills form and displays predicted vs listed price

### B) Manual flow
1. User sets apartment parameters + optional photos
2. System predicts price and renders explainability tables
3. UI shows renovation label, positive factors, and negative factors

## 11. Notes and Limitations
- `apps/backend/models/` files are required; without them inference endpoints fail.
- `data/images/` is runtime-only and auto-created on startup.
- `data/index/index.parquet` is used for comparable listings quality.
- External parsing quality depends on source page structure and accessibility.

## 12. Team Members
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

---
This repository contains the final integrated coursework prototype for multimodal apartment valuation.
