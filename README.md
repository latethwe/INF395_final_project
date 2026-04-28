# KrishaVision

Photo-Enhanced Multimodal Apartment Valuation System
A multimodal real estate valuation system: tabular features + listing photos (CLIP) + CatBoost.

The project supports:
- collecting and refreshing a Krisha listings dataset;
- the new data schema (`condition_*`, `description`, `object_type`, `collected_at`);
- time-based split and evaluation;
- baseline (tabular) and multimodal (tabular + CLIP) training;
- FastAPI service + web UI.

## 1. Tech Stack

- Python
- PyTorch + OpenCLIP
- CatBoost
- Pandas / NumPy / PyArrow
- FastAPI / Uvicorn
- Streamlit

## 2. Installation

```bash
cd /path/to/(project)
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

GPU check:

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no-gpu')"
```

## 3. Project Structure

```text
scripts/      # data collection, indexing, split, eval
src/          # API, inference, listing parser
notebooks/    # data checks, embeddings, training
data/         # raw_ads, images, index, processed
models/       # trained models and metadata
frontend/     # built-in FastAPI UI
```

## 4. Data Schema (New)

Key fields in `data/raw_ads/*.json` and `data/index/index.parquet`:
- base: `ad_id`, `url`, `price`, `area`, `price_per_m2`, `rooms`, `district`, `building_type`, `year_built`, `floor`, `floors_total`, `latitude`, `longitude`, `image_urls`
- new: `description`, `object_type`, `condition_raw`, `condition_norm`, `condition_source`, `condition_confidence`, `collected_at`

Condition normalization:
- `condition_norm in {fresh, average, needs, unknown}`
- source: `condition_source in {listing_tag, description, null}`

## 5. Full Run Order (From Scratch)

### 5.1 Data Collection

```bash
source .venv/bin/activate
python scripts/01_collect_ids.py
python scripts/02_fetch_details.py
python scripts/03_download_images.py
python scripts/04_build_index.py
```

What each step does:
- `01_collect_ids.py` — collects listing `ad_id`s;
- `02_fetch_details.py` — parses listings up to `TARGET_OK=25000`, min photos = 4, stores new schema;
- `03_download_images.py` — downloads up to 10 photos per listing;
- `04_build_index.py` — builds `data/index/index.parquet`.

### 5.2 Data Validation

Open and run all cells:
- `notebooks/data_check.ipynb`

### 5.3 Time-Based Split

```bash
python scripts/06_time_split.py --parquet data/index/index.parquet --out-dir data/processed --train-ratio 0.8 --val-ratio 0.1
```

Outputs:
- `data/processed/train_ad_ids.csv`
- `data/processed/val_ad_ids.csv`
- `data/processed/test_ad_ids.csv`

### 5.4 CLIP Embeddings

Open and run all cells:
- `notebooks/clip_embeddings_cpu.ipynb`

Outputs:
- `data/processed/clip_vitb32_ad_ids.npy`
- `data/processed/clip_vitb32_ad_emb.npy`

> The notebook automatically uses `cuda` when available.

### 5.5 Baseline Training (Tabular)

Open and run all cells:
- `notebooks/catboost_baseline.ipynb`

Outputs:
- `models/catboost_tabular_baseline.cbm`
- `models/v1_metadata.json`

### 5.6 Multimodal Training (Tabular + CLIP)

Open and run all cells:
- `notebooks/train_tabular_plus_clip.ipynb`

Outputs:
- `models/catboost_tabular_plus_clip_vitb32.cbm`
- `models/v2_metadata.json`

### 5.7 Time-Based Evaluation

```bash
python scripts/07_evaluate_time_based.py --parquet data/index/index.parquet --splits-dir data/processed --out-json data/processed/time_eval_metrics.json
```

Output:
- `data/processed/time_eval_metrics.json`

## 6. Run API and UI

### FastAPI

```bash
uvicorn src.app:app --reload
```

- API: `http://127.0.0.1:8000`
- UI: `http://127.0.0.1:8000/ui`

### Streamlit (Optional)

```bash
streamlit run src/streamlit.py
```

## 7. Re-runs and Duplicates

- `scripts/02_fetch_details.py` is resume-friendly and does not create duplicate files per `ad_id` (`raw_ads/<ad_id>.json`).
- `scripts/03_download_images.py` does not rewrite already downloaded image files.
- `scripts/04_build_index.py` rebuilds `index.parquet` from current data.

## 8. GPU and CLIP Model Choice

Current default: `ViT-B-32` (fast and stable baseline).

Recommended approach:
1. Lock baseline metrics with `ViT-B-32`.
2. Run an isolated experiment with a heavier model (for example `ViT-L-14`) on the same split.
3. Switch only if quality gains are stable and justify extra runtime/VRAM.

## 9. Useful Files

- `scripts/02_fetch_details.py` — new parsing schema
- `scripts/06_time_split.py` — time split
- `scripts/07_evaluate_time_based.py` — evaluation
- `src/v2_infer.py` — inference and explainability
- `src/krisha_ad.py` — parse listing by URL
- `src/app.py` — API
