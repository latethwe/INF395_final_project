from pathlib import Path
from typing import List, Optional
import os
import tempfile

from fastapi import FastAPI, UploadFile, File, Form

from .v2_infer import V2Estimator

PROJECT_ROOT = Path(os.environ.get("KRISHA_ROOT", "/Users/zhasik/Desktop/krisha"))
est = V2Estimator(PROJECT_ROOT)

app = FastAPI(title="Krisha Price Estimator", version="2.1")


@app.get("/health")
def health():
    return {"status": "ok", "model": est.meta.get("version", "unknown")}


def build_payload(
    area: float,
    rooms: int,
    floor: int,
    floors_total: int,
    year_built: int,
    district: str,
    building_type: str,
):
    return {
        "area": float(area),
        "rooms": int(rooms),
        "floor": int(floor),
        "floors_total": int(floors_total),
        "year_built": int(year_built),
        "district": str(district),
        "building_type": str(building_type),
    }


@app.post("/predict_tabular")
async def predict_tabular(
    area: float = Form(...),
    rooms: int = Form(...),
    floor: int = Form(...),
    floors_total: int = Form(...),
    year_built: int = Form(...),
    district: str = Form(...),
    building_type: str = Form(...),
):
    payload = build_payload(area, rooms, floor, floors_total, year_built, district, building_type)
    # tabular-only: пустой список изображений
    return est.predict(payload, image_files=[])


@app.post("/predict")
async def predict(
    area: float = Form(...),
    rooms: int = Form(...),
    floor: int = Form(...),
    floors_total: int = Form(...),
    year_built: int = Form(...),
    district: str = Form(...),
    building_type: str = Form(...),
    images: Optional[List[UploadFile]] = File(None),  # <-- фото НЕ обязательны
):
    payload = build_payload(area, rooms, floor, floors_total, year_built, district, building_type)

    tmp_paths: List[Path] = []
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)

        if images:
            # берём максимум 7
            for i, f in enumerate(images[:7]):
                # разрешаем webp/jpg/png — Pillow откроет
                filename = f.filename or f"image_{i:02d}"
                p = td_path / f"{i:02d}_{filename}"
                p.write_bytes(await f.read())
                tmp_paths.append(p)

        return est.predict(payload, image_files=tmp_paths)
