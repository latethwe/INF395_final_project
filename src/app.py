from pathlib import Path
from typing import List
import tempfile
import shutil
import csv

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .v2_infer import V2Estimator
from .krisha_ad import (
    fetch_listing,
    download_images,
    build_model_payload_from_listing,
    make_price_diff,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
est = V2Estimator(PROJECT_ROOT)

app = FastAPI(title="Krisha Price Estimator v2", version="2.0")
app.mount("/ui", StaticFiles(directory=PROJECT_ROOT / "frontend", html=True), name="ui")
app.mount("/data/images", StaticFiles(directory=PROJECT_ROOT / "data" / "images"), name="data_images")


@app.get("/")
def root():
    return RedirectResponse(url="/ui")


@app.get("/health")
def health():
    return {"status": "ok", "model": est.meta["version"]}


def _load_rc_options() -> list[str]:
    names: set[str] = set()
    candidates = [
        PROJECT_ROOT / "data" / "rc_names" / "almaty_rc_names.csv",
        PROJECT_ROOT / "rc_names" / "almaty_rc_names.csv",
    ]
    for csv_path in candidates:
        if not csv_path.exists():
            continue
        try:
            with csv_path.open(encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    v = str((row or {}).get("name") or "").strip()
                    if v:
                        names.add(v)
        except Exception:
            continue
    return sorted(names, key=lambda x: x.lower())


@app.get("/meta/options")
def meta_options():
    return {
        "districts": [
            "Алмалинский р-н",
            "Ауэзовский р-н",
            "Бостандыкский р-н",
            "Жетысуский р-н",
            "Медеуский р-н",
            "Наурызбайский р-н",
            "Турксибский р-н",
            "Алатауский р-н",
        ],
        "building_types": ["монолитный", "кирпичный", "панельный", "иной"],
        "residential_complexes": _load_rc_options(),
    }


def _save_uploads_to_tmp(images: List[UploadFile], max_images: int) -> List[Path]:
    """
    Saves uploaded images to a temporary directory and returns list of Paths.
    IMPORTANT: caller must keep the TemporaryDirectory alive while using the paths.
    We'll return both tempdir handle + paths in the endpoints below.
    """
    raise NotImplementedError  # see endpoints below


@app.post("/predict")
async def predict(
    area: float = Form(...),
    rooms: int = Form(...),
    floor: int = Form(...),
    floors_total: int = Form(...),
    year_built: int = Form(...),
    district: str = Form(...),
    building_type: str = Form(...),
    residential_complex: str | None = Form(default=None),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    images: List[UploadFile] = File(default=[]),
):
    x = dict(
        area=area,
        rooms=rooms,
        floor=floor,
        floors_total=floors_total,
        year_built=year_built,
        district=district,
        building_type=building_type,
        residential_complex=residential_complex,
        latitude=latitude,
        longitude=longitude,
    )

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        paths: List[Path] = []

        for i, f in enumerate(images[: est.max_images]):
            # Make safe-ish filename
            suffix = Path(f.filename or "").suffix or ".jpg"
            p = td / f"{i:02d}{suffix}"

            with p.open("wb") as out:
                shutil.copyfileobj(f.file, out)

            paths.append(p)

        return est.predict(x, paths)


@app.post("/explain")
async def explain(
    area: float = Form(...),
    rooms: int = Form(...),
    floor: int = Form(...),
    floors_total: int = Form(...),
    year_built: int = Form(...),
    district: str = Form(...),
    building_type: str = Form(...),
    residential_complex: str | None = Form(default=None),
    latitude: float | None = Form(default=None),
    longitude: float | None = Form(default=None),
    images: List[UploadFile] = File(default=[]),
):
    x = dict(
        area=area,
        rooms=rooms,
        floor=floor,
        floors_total=floors_total,
        year_built=year_built,
        district=district,
        building_type=building_type,
        residential_complex=residential_complex,
        latitude=latitude,
        longitude=longitude,
    )

    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        paths: List[Path] = []

        for i, f in enumerate(images[: est.max_images]):
            suffix = Path(f.filename or "").suffix or ".jpg"
            p = td / f"{i:02d}{suffix}"

            with p.open("wb") as out:
                shutil.copyfileobj(f.file, out)

            paths.append(p)

        return est.explain(x, paths)


@app.post("/predict_by_url")
async def predict_by_url(url: str = Form(...), use_photos: bool = Form(default=True)):
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        session_images_dir = td_path / "images"

        try:
            rec = fetch_listing(url)
            x = build_model_payload_from_listing(rec)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Ошибка парсинга объявления: {e}")

        image_paths: List[Path] = []
        if use_photos:
            image_paths = download_images(
                image_urls=rec.get("image_urls", []),
                out_dir=session_images_dir,
                max_images=est.max_images,
            )

        prediction = est.predict(x, image_paths)

        actual_price = rec.get("price")
        actual_ppm2 = rec.get("price_per_m2")
        pred_price = prediction.get("price")
        pred_ppm2 = prediction.get("price_per_m2")

        return {
            "listing": {
                "ad_id": rec.get("ad_id"),
                "url": rec.get("url"),
                "price": actual_price,
                "price_per_m2": actual_ppm2,
                "area": rec.get("area"),
                "rooms": rec.get("rooms"),
                "district": rec.get("district"),
                "building_type": rec.get("building_type"),
                "residential_complex": rec.get("residential_complex"),
                "year_built": rec.get("year_built"),
                "floor": rec.get("floor"),
                "floors_total": rec.get("floors_total"),
                "latitude": rec.get("latitude"),
                "longitude": rec.get("longitude"),
                "description": rec.get("description"),
                "object_type": rec.get("object_type"),
                "condition_raw": rec.get("condition_raw"),
                "condition_norm": rec.get("condition_norm"),
                "condition_source": rec.get("condition_source"),
                "condition_confidence": rec.get("condition_confidence"),
                "collected_at": rec.get("collected_at"),
                "image_urls_count": len(rec.get("image_urls", [])),
                "images_downloaded_count": len(image_paths),
            },
            "prediction": prediction,
            "difference": {
                "price": make_price_diff(pred_price, actual_price),
                "price_per_m2": make_price_diff(pred_ppm2, actual_ppm2),
            },
        }
