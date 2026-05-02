from pathlib import Path
from typing import List
import csv
import tempfile
import json
import shutil
import uuid
from threading import Lock

from fastapi import FastAPI, File, Form, HTTPException, Header, Request, Depends, Query
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import FileResponse
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from .core.config import settings
from .core.security import create_access_token, hash_password
from .db.models import User, PredictionHistory
from .db.schemas import RegisterRequest, LoginRequest, TokenOut, UserOut, HistoryOut
from .db.service import (
    authenticate_user,
    get_db,
    init_db,
    save_history,
    serialize_history,
    to_user_out,
)

from .ml.v2_infer import V2Estimator
from .services.krisha_ad import (
    build_model_payload_from_listing,
    download_images,
    fetch_listing,
    make_price_diff,
)


BACKEND_ROOT = Path(__file__).resolve().parent
REPO_ROOT = BACKEND_ROOT.parents[1]
FRONTEND_ROOT = REPO_ROOT / "apps" / "frontend"
DATA_IMAGES_DIR = REPO_ROOT / "data" / "images"
DATA_IMAGES_DIR.mkdir(parents=True, exist_ok=True)

_ESTIMATOR: V2Estimator | None = None
_ESTIMATOR_LOCK = Lock()
_ML_DISABLED_MESSAGE = "ML service is temporarily unavailable on this deployment. Run model inference locally via Cloudflare tunnel and connect frontend to that endpoint."


def get_estimator() -> V2Estimator:
    if not settings.ml_enabled:
        raise HTTPException(status_code=503, detail=_ML_DISABLED_MESSAGE)
    global _ESTIMATOR
    if _ESTIMATOR is not None:
        return _ESTIMATOR
    with _ESTIMATOR_LOCK:
        if _ESTIMATOR is None:
            try:
                _ESTIMATOR = V2Estimator(BACKEND_ROOT)
            except Exception as e:
                raise HTTPException(status_code=503, detail=f"{_ML_DISABLED_MESSAGE} Startup error: {e}") from e
    return _ESTIMATOR


def get_model_version() -> str:
    metadata_path = BACKEND_ROOT / "models" / "v2_metadata.json"
    try:
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
        return str(raw.get("version") or "unknown")
    except Exception:
        return "unknown"

app = FastAPI(title="PricePal Real Estate API", version="4.0")
cors_origins = [x.strip() for x in (settings.cors_origins or "*").split(",") if x.strip()]
if not cors_origins:
    cors_origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=("*" not in cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/assets", StaticFiles(directory=FRONTEND_ROOT / "assets"), name="assets")
app.mount("/data/images", StaticFiles(directory=DATA_IMAGES_DIR), name="data_images")


DISTRICTS = [
    "Алмалинский р-н",
    "Ауэзовский р-н",
    "Бостандыкский р-н",
    "Жетысуский р-н",
    "Медеуский р-н",
    "Наурызбайский р-н",
    "Турксибский р-н",
    "Алатауский р-н",
]
BUILDING_TYPES = ["монолитный", "кирпичный", "панельный", "иной"]
OBJECT_TYPES = ["flat", "house", "dacha", "commercial", "unknown"]
CONDITION_OPTIONS = ["fresh", "average", "needs", "unknown"]


def _resolve_user_from_authorization(authorization: str | None, db: Session) -> User | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
        sub = payload.get("sub")
        user_id = int(sub) if sub else None
    except (JWTError, ValueError):
        return None
    if not user_id:
        return None
    user = db.get(User, user_id)
    if not user or not user.is_active:
        return None
    return user


def _manual_prediction_payload(
    *,
    area: float,
    rooms: int,
    floor: int,
    floors_total: int,
    year_built: int,
    district: str,
    building_type: str,
    residential_complex: str | None,
    latitude: float | None,
    longitude: float | None,
    object_type: str | None,
    condition_norm: str | None,
    condition_source: str | None,
    condition_confidence: float | None,
) -> dict[str, object]:
    normalized_condition = (condition_norm or "").strip().lower() or "unknown"
    normalized_object_type = (object_type or "").strip().lower() or "flat"
    normalized_source = (condition_source or "").strip().lower()

    if not normalized_source:
        normalized_source = "manual" if normalized_condition != "unknown" else "unknown"
    if condition_confidence is None:
        condition_confidence = 1.0 if normalized_condition != "unknown" else 0.0

    return {
        "area": area,
        "rooms": rooms,
        "floor": floor,
        "floors_total": floors_total,
        "year_built": year_built,
        "district": district,
        "building_type": building_type,
        "residential_complex": residential_complex,
        "latitude": latitude,
        "longitude": longitude,
        "object_type": normalized_object_type,
        "condition_norm": normalized_condition,
        "condition_source": normalized_source,
        "condition_confidence": condition_confidence,
    }


@app.get("/")
def root():
    return RedirectResponse(url="/home")


@app.get("/home")
def home():
    return FileResponse(FRONTEND_ROOT / "index.html")

@app.get("/my-history")
def my_history_page():
    return FileResponse(FRONTEND_ROOT / "history.html")


@app.get("/health")
def health():
    return {"status": "ok", "model": get_model_version(), "ml_enabled": settings.ml_enabled}


@app.get("/runtime-config")
def runtime_config():
    return {"api_base_url": settings.external_ml_api_base or ""}


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.post("/auth/register", response_model=TokenOut)
def register(payload: RegisterRequest, db: Session = Depends(get_db)):
    login = payload.login.strip()
    if not login:
        raise HTTPException(status_code=422, detail="Login is required")
    existing = db.execute(select(User).where(User.email == login)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Login already exists")
    user = User(email=login, password_hash=hash_password(payload.password), role="user", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id), user.role)
    return TokenOut(access_token=token, user=to_user_out(user))


@app.post("/auth/login", response_model=TokenOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = authenticate_user(db, payload.login, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid login or password")
    token = create_access_token(str(user.id), user.role)
    return TokenOut(access_token=token, user=to_user_out(user))


@app.get("/auth/me", response_model=UserOut)
def me(authorization: str | None = Header(default=None), db: Session = Depends(get_db)):
    user = _resolve_user_from_authorization(authorization, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return to_user_out(user)


@app.get("/history", response_model=list[HistoryOut])
def my_history(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    user = _resolve_user_from_authorization(authorization, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    stmt = (
        select(PredictionHistory)
        .where(PredictionHistory.user_id == user.id)
        .order_by(PredictionHistory.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return [serialize_history(item) for item in rows]


@app.get("/history/{history_id}", response_model=HistoryOut)
def history_detail(
    history_id: int,
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    user = _resolve_user_from_authorization(authorization, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    item = db.get(PredictionHistory, history_id)
    if not item or item.user_id != user.id:
        raise HTTPException(status_code=404, detail="History item not found")
    return serialize_history(item)


def _load_rc_options() -> list[str]:
    names: set[str] = set()
    candidates = [
        REPO_ROOT / "data" / "rc_names" / "almaty_rc_names.csv",
        REPO_ROOT / "rc_names" / "almaty_rc_names.csv",
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
        "districts": DISTRICTS,
        "building_types": BUILDING_TYPES,
        "object_types": OBJECT_TYPES,
        "condition_options": CONDITION_OPTIONS,
        "residential_complexes": _load_rc_options(),
    }


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
    object_type: str = Form(default="flat"),
    condition_norm: str = Form(default="unknown"),
    condition_source: str | None = Form(default=None),
    condition_confidence: float | None = Form(default=None),
    images: List[bytes] = File(default=[]),
):
    est = get_estimator()
    x = _manual_prediction_payload(
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
        object_type=object_type,
        condition_norm=condition_norm,
        condition_source=condition_source,
        condition_confidence=condition_confidence,
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        paths: List[Path] = []

        for i, image_bytes in enumerate(images[: est.max_images]):
            p = td_path / f"{i:02d}.jpg"
            p.write_bytes(image_bytes)
            paths.append(p)

        out = est.predict(x, paths)

    return out


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
    object_type: str = Form(default="flat"),
    condition_norm: str = Form(default="unknown"),
    condition_source: str | None = Form(default=None),
    condition_confidence: float | None = Form(default=None),
    image_urls_json: str | None = Form(default=None),
    image_names_json: str | None = Form(default=None),
    images: List[bytes] = File(default=[]),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    est = get_estimator()
    user = _resolve_user_from_authorization(authorization, db)
    x = _manual_prediction_payload(
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
        object_type=object_type,
        condition_norm=condition_norm,
        condition_source=condition_source,
        condition_confidence=condition_confidence,
    )

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        paths: List[Path] = []

        for i, image_bytes in enumerate(images[: est.max_images]):
            p = td_path / f"{i:02d}.jpg"
            p.write_bytes(image_bytes)
            paths.append(p)

        manual_images_count = len(paths)
        remaining = max(est.max_images - manual_images_count, 0)
        linked_urls_used: List[str] = []
        if manual_images_count == 0 and remaining > 0 and image_urls_json:
            try:
                parsed = json.loads(image_urls_json)
            except Exception:
                parsed = []
            if isinstance(parsed, list):
                extra_urls = [str(u) for u in parsed if isinstance(u, str) and u.strip()]
                if extra_urls:
                    extra_paths = download_images(
                        image_urls=extra_urls,
                        out_dir=td_path / "linked_images",
                        max_images=remaining,
                    )
                    paths.extend(extra_paths)
                    linked_urls_used = extra_urls[: len(extra_paths)]

        out = est.explain(x, paths)
        out["debug_model_input"] = {
            "payload_to_model": x,
            "manual_images_count": manual_images_count,
            "linked_images_count": len(linked_urls_used),
            "linked_used_image_urls": linked_urls_used,
            "photo_source": "manual_upload" if manual_images_count > 0 else ("from_listing_url" if linked_urls_used else "none"),
            "total_images_used": len(paths),
        }
        if user:
            image_names: list[str] = []
            if image_names_json:
                try:
                    parsed_names = json.loads(image_names_json)
                    if isinstance(parsed_names, list):
                        image_names = [str(v) for v in parsed_names if str(v).strip()]
                except Exception:
                    image_names = []
            saved_image_urls: list[str] = []
            if manual_images_count > 0:
                history_dir = DATA_IMAGES_DIR / "history" / str(user.id)
                history_dir.mkdir(parents=True, exist_ok=True)
                for i, src in enumerate(paths[:manual_images_count]):
                    original = image_names[i] if i < len(image_names) else f"image_{i+1}.jpg"
                    suffix = Path(original).suffix.lower() or ".jpg"
                    safe_name = f"{uuid.uuid4().hex}{suffix}"
                    dst = history_dir / safe_name
                    try:
                        shutil.copy2(src, dst)
                        saved_image_urls.append(f"/data/images/history/{user.id}/{safe_name}")
                    except Exception:
                        continue
            save_history(
                db,
                user_id=user.id,
                mode="explain",
                request_payload={**x, "images_count": len(paths), "image_names": image_names, "saved_image_urls": saved_image_urls},
                response_payload=out,
                predicted_price=out.get("prediction", {}).get("price"),
                predicted_price_per_m2=out.get("prediction", {}).get("price_per_m2"),
                source_url=None,
            )
    return out


@app.post("/predict_by_url")
async def predict_by_url(
    url: str = Form(...),
    use_photos: bool = Form(default=True),
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    est = get_estimator()
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        session_images_dir = td_path / "images"

        try:
            rec = fetch_listing(url)
            x = build_model_payload_from_listing(rec)
            # Do not pass parsed renovation condition from listing text/tags.
            # Let visual branch (photos) drive renovation assessment.
            x["condition_norm"] = "unknown"
            x["condition_source"] = "unknown"
            x["condition_confidence"] = 0.0
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
        explanation = est.explain(x, image_paths)

        actual_price = rec.get("price")
        actual_ppm2 = rec.get("price_per_m2")
        pred_price = prediction.get("price")
        pred_ppm2 = prediction.get("price_per_m2")

        out = {
            "debug_model_input": {
                "payload_to_model": x,
                "use_photos": use_photos,
                "downloaded_images_count": len(image_paths),
                "used_image_urls": rec.get("image_urls", [])[: len(image_paths)],
            },
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
                "used_image_urls": rec.get("image_urls", [])[: len(image_paths)],
            },
            "prediction": prediction,
            "explain": explanation,
            "difference": {
                "price": make_price_diff(pred_price, actual_price),
                "price_per_m2": make_price_diff(pred_ppm2, actual_ppm2),
            },
        }

    user = _resolve_user_from_authorization(authorization, db)
    if user:
        save_history(
            db,
            user_id=user.id,
            mode="predict_by_url",
            request_payload={"url": url, "use_photos": use_photos},
            response_payload=out,
            predicted_price=prediction.get("price"),
            predicted_price_per_m2=prediction.get("price_per_m2"),
            source_url=rec.get("url") or url,
        )
    return out
