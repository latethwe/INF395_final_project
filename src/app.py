from pathlib import Path
from typing import List
import tempfile
import shutil

from fastapi import FastAPI, UploadFile, File, Form

from .v2_infer import V2Estimator


PROJECT_ROOT = Path(__file__).resolve().parents[1]
est = V2Estimator(PROJECT_ROOT)

app = FastAPI(title="Krisha Price Estimator v2", version="2.0")


@app.get("/health")
def health():
    return {"status": "ok", "model": est.meta["version"]}


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
