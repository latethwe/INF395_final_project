import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import math

import numpy as np
import pandas as pd
from PIL import Image

from catboost import CatBoostRegressor, Pool

import torch
import torch.nn.functional as F
import open_clip


@dataclass
class FeatureImpact:
    feature: str
    value: Any
    impact: float  # in log(price_per_m2) space
    unit: str = "log_ppm2"
    reason: Optional[str] = None


class V2Estimator:
    """
    v2:
      - CatBoostRegressor predicts log(price_per_m2)
      - price = exp(pred_log) * area
      - images -> CLIP image embeddings mean-agg -> clip_XXX features

    Added:
      - explain(): local SHAP values (CatBoost) + renovation review via CLIP zero-shot prompts
    """

    def __init__(self, project_root: Path, meta_file: str = "v2_metadata.json"):
        self.project_root = Path(project_root)

        meta_path = self.project_root / "models" / meta_file
        self.meta = json.loads(meta_path.read_text(encoding="utf-8"))

        # Load CatBoost model
        model_path = self.project_root / "models" / self.meta["model_file"]
        self.model = CatBoostRegressor()
        self.model.load_model(str(model_path))

        # CLIP config
        clip_cfg = self.meta["clip"]
        self.clip_model_name = clip_cfg["model_name"]
        self.clip_pretrained = clip_cfg["pretrained"]
        self.max_images = int(clip_cfg["max_images"])
        self.normalize_per_image = bool(clip_cfg["normalize_per_image"])
        self.normalize_agg = bool(clip_cfg["normalize_agg"])

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.clip_model, _, self.preprocess = open_clip.create_model_and_transforms(
            self.clip_model_name, pretrained=self.clip_pretrained, device=self.device
        )
        self.clip_model.eval()
        self.tokenizer = open_clip.get_tokenizer(self.clip_model_name)

        # Features
        self.features_num = self.meta["features_num"]
        self.features_cat = self.meta["features_cat"]
        self.features = self.features_num + self.features_cat
        self.current_year = int(self.meta["current_year"])

        # Determine native CLIP embedding dim
        with torch.no_grad():
            dummy = torch.zeros(1, 3, 224, 224, device=self.device)
            z = self.clip_model.encode_image(dummy)
            self.clip_native_dim = int(z.shape[-1])

        # Create embedding column names expected by the CatBoost model.
        model_feature_names = list(getattr(self.model, "feature_names_", []) or [])
        self.emb_cols = [c for c in model_feature_names if c.startswith("clip_")]
        if not self.emb_cols:
            self.emb_cols = [f"clip_{i:03d}" for i in range(self.clip_native_dim)]
        self.model_emb_dim = len(self.emb_cols)

        # Precompute CatBoost cat feature indices for pools
        # (CatBoost wants indices in the provided data order)
        all_cols = self.features + self.emb_cols
        self.cat_feature_indices = [all_cols.index(c) for c in self.features_cat if c in all_cols]

        # Human reasons for UI
        self._feature_reasons = {
            "area": "площадь напрямую масштабирует стоимость",
            "rooms": "кол-во комнат влияет на сегмент спроса",
            "floor": "этаж может влиять на комфорт и ликвидность",
            "floors_total": "этажность дома влияет на тип/класс",
            "floor_ratio": "относительный этаж (низ/середина/верх)",
            "is_first": "первый этаж часто дешевле из-за шума/безопасности",
            "is_last": "последний этаж может быть минусом из-за крыши/лифта",
            "building_age": "возраст дома влияет на коммуникации/состояние",
            "district": "район влияет на спрос и инфраструктуру",
            "building_type": "тип дома влияет на восприятие качества и ликвидность",
            # clip_*** не перечисляем все — объяснять будем агрегатно в UI
        }

        # Zero-shot renovation prompts (RU) — можно расширять
        self._reno_condition_prompts = [
            ("fresh", "квартира со свежим современным ремонтом, новая отделка"),
            ("average", "квартира со средним состоянием, обычная отделка, местами устаревшая"),
            ("needs", "квартира требует ремонта, устаревшая отделка, износ"),
        ]

        # Signals -> prompt and recommendation mapping
        self._reno_signal_prompts = [
            ("kitchen_outdated", "устаревшая кухня, старая мебель и отделка кухни"),
            ("bathroom_outdated", "устаревший санузел, старая плитка и сантехника"),
            ("low_light", "темное помещение, мало естественного света, недостаточное освещение"),
            ("clutter", "захламленное помещение, много вещей, визуальный шум"),
            ("worn_floor", "изношенный пол, старый ламинат или паркет с дефектами"),
            ("old_windows", "старые окна, деревянные рамы, слабая герметичность"),
        ]

        # Similar listings cache (loaded once)
        self._comparables_df = self._load_comparables_df()

    # -------------------------
    # Core feature building
    # -------------------------
    def _encode_images(self, image_paths: List[Path]) -> np.ndarray:
        tensors = []
        for p in image_paths[: self.max_images]:
            try:
                img = Image.open(p).convert("RGB")
                tensors.append(self.preprocess(img))
            except Exception:
                continue

        if not tensors:
            return np.zeros((self.clip_native_dim,), dtype=np.float32)

        imgs = torch.stack(tensors, dim=0).to(self.device)

        with torch.no_grad():
            feats = self.clip_model.encode_image(imgs)  # [k, dim]
            if self.normalize_per_image:
                feats = F.normalize(feats, dim=-1)
            feats = feats.cpu().numpy().astype(np.float32)

        emb = feats.mean(axis=0)
        if self.normalize_agg:
            emb = emb / (np.linalg.norm(emb) + 1e-12)
        return emb.astype(np.float32)

    def _to_model_embedding(self, emb: np.ndarray) -> np.ndarray:
        v = np.asarray(emb, dtype=np.float32).reshape(-1)
        if v.shape[0] >= self.model_emb_dim:
            return v[: self.model_emb_dim]
        out = np.zeros((self.model_emb_dim,), dtype=np.float32)
        out[: v.shape[0]] = v
        return out

    def _make_tabular_row(self, x: Dict[str, Any]) -> Dict[str, Any]:
        def _cat(v: Any) -> str:
            if v is None:
                return "unknown"
            s = str(v).strip()
            if not s or s.lower() in {"nan", "none", "null"}:
                return "unknown"
            return s

        def _num(v: Any) -> Optional[float]:
            if v is None:
                return None
            try:
                z = float(v)
            except Exception:
                return None
            if not np.isfinite(z):
                return None
            return z

        area = float(x["area"])
        rooms = int(x["rooms"])
        floor = int(x["floor"])
        floors_total = int(x["floors_total"])
        year_built = int(x["year_built"])

        district = _cat(x.get("district"))
        building_type = _cat(x.get("building_type"))
        residential_complex = _cat(x.get("residential_complex"))

        lat = _num(x.get("latitude"))
        lon = _num(x.get("longitude"))
        has_geo = int(lat is not None and lon is not None)
        if lat is None:
            lat = 43.238949
        if lon is None:
            lon = 76.889709
        has_residential_complex = int(residential_complex != "unknown")

        floor_ratio = floor / floors_total if floors_total else 0.0
        floor_ratio = max(0.0, min(1.0, floor_ratio))

        is_first = int(floor == 1)
        is_last = int(floor == floors_total)
        building_age = self.current_year - year_built

        return {
            "area": area,
            "rooms": rooms,
            "floor": floor,
            "floors_total": floors_total,
            "floor_ratio": floor_ratio,
            "is_first": is_first,
            "is_last": is_last,
            "building_age": building_age,
            "latitude": float(lat),
            "longitude": float(lon),
            "has_geo": has_geo,
            "has_residential_complex": has_residential_complex,
            "district": district,
            "building_type": building_type,
            "residential_complex": residential_complex,
        }

    def _build_row_and_df(
        self,
        x: Dict[str, Any],
        image_files: List[Path],
    ) -> Tuple[Dict[str, Any], pd.DataFrame, np.ndarray]:
        tab = self._make_tabular_row(x)
        emb = self._encode_images(image_files)
        emb_for_model = self._to_model_embedding(emb)
        row = {**tab, **{c: float(v) for c, v in zip(self.emb_cols, emb_for_model)}}

        # Ensure expected schema and safe cat values for CatBoost
        for c in self.features_num:
            if c not in row:
                row[c] = 0.0
        for c in self.features_cat:
            v = row.get(c)
            if v is None:
                row[c] = "unknown"
            else:
                s = str(v).strip()
                row[c] = s if s and s.lower() not in {"nan", "none", "null"} else "unknown"

        X = pd.DataFrame([row], columns=self.features + self.emb_cols)
        return row, X, emb

    # -------------------------
    # Prediction (unchanged behavior)
    # -------------------------
    def _to_scalar(self, v: Any, default: float = 0.0) -> float:
        """
        Safely convert model outputs like scalar / [x] / [[x]] to float.
        """
        try:
            arr = np.asarray(v, dtype=np.float64)
            if arr.size == 0:
                return float(default)
            return float(arr.reshape(-1)[0])
        except Exception:
            try:
                return float(v)
            except Exception:
                return float(default)

    def predict(
        self,
        x: Dict[str, Any],
        image_files: List[Path],
    ) -> Dict[str, Any]:
        _, X, _ = self._build_row_and_df(x, image_files)

        pred_log = self._to_scalar(self.model.predict(X))
        ppm2 = float(np.exp(pred_log))
        price = float(ppm2 * float(X.loc[0, "area"]))

        return {
            "pred_log_price_per_m2": pred_log,
            "price_per_m2": ppm2,
            "price": price,
            "comparables": self._find_similar_ads(x, top_k=3),
        }


    def _impact_to_human(self, impact_log: float, ppm2: float, area: float) -> Dict[str, float]:
        """
        Примерная интерпретация вклада impact_log (в log(price_per_m2)) в:
        - проценты изменения price_per_m2
        - тенге/м2
        - тенге по всей квартире
        """
        pct = (float(np.exp(impact_log)) - 1.0) * 100.0
        kzt_ppm2 = (pct / 100.0) * float(ppm2)
        kzt_total = kzt_ppm2 * float(area)
        return {
            "impact_log": float(impact_log),
            "impact_pct_ppm2": float(pct),
            "impact_kzt_ppm2": float(kzt_ppm2),
            "impact_kzt_total": float(kzt_total),
        }


    def _fmt_feature(self, name: str) -> str:
        """Человеческие названия для UI."""
        mapping = {
            "district": "Район",
            "building_type": "Тип дома",
            "building_age": "Возраст дома (лет)",
            "year_built": "Год постройки",
            "floor": "Этаж",
            "floors_total": "Этажность дома",
            "floor_ratio": "Относительный этаж",
            "rooms": "Комнат",
            "area": "Площадь (м²)",
            "is_first": "Первый этаж",
            "is_last": "Последний этаж",
            "images": "Фото (визуальные признаки)",
        }
        return mapping.get(name, name)

    # -------------------------
    # Explainability: CatBoost local SHAP + renovation review (CLIP zero-shot)
    # -------------------------
    def explain(
        self,
        x: Dict[str, Any],
        image_files: List[Path],
        top_n: int = 6,
        signal_threshold: float = 0.55,
    ) -> Dict[str, Any]:
        """
        Human-friendly explanation:
        - Aggregates all clip_* shap into a single "images" contribution
        - Shows contributions in log space + % + KZT
        - If no photos were provided: do NOT estimate renovation, and label images as "no photos"
        """
        n_photos = min(len(image_files), self.max_images)

        row, X, emb = self._build_row_and_df(x, image_files)

        # --- Predict
        pred_log = self._to_scalar(self.model.predict(X))
        ppm2 = float(np.exp(pred_log))
        area = float(X.loc[0, "area"])
        price = float(ppm2 * area)

        # --- SHAP values (CatBoost)
        pool = Pool(X, cat_features=self.cat_feature_indices)
        shap_vals = np.asarray(self.model.get_feature_importance(pool, type="ShapValues"), dtype=np.float64)

        base_value = float(shap_vals[0, -1])
        impacts = shap_vals[0, :-1]
        cols = list(X.columns)

        # --- Aggregate clip_* contributions into one "images"
        clip_sum = 0.0
        items = []  # tabular + aggregated images

        for name, imp in zip(cols, impacts):
            imp = float(imp)
            if name.startswith("clip_"):
                clip_sum += imp
                continue

            value = row.get(name)
            reason = self._feature_reasons.get(name)

            items.append(
                {
                    "feature": name,
                    "feature_label": self._fmt_feature(name),
                    "value": value,
                    "reason": reason,
                    **self._impact_to_human(imp, ppm2, area),
                }
            )

        # add aggregated images item (special semantics when n_photos == 0)
        if n_photos == 0:
            images_label = "Нет фото (визуальных данных нет)"
            images_reason = "фото не загружены: визуальные признаки не учитываются (CLIP=0)"
        else:
            images_label = self._fmt_feature("images")
            images_reason = "вклад визуальных признаков из фотографий (CLIP эмбеддинг, агрегировано)"

        items.append(
            {
                "feature": "images",
                "feature_label": images_label,
                "value": f"{n_photos} фото",
                "reason": images_reason,
                **self._impact_to_human(clip_sum, ppm2, area),
            }
        )

        # --- top + / -
        pos = sorted([i for i in items if i["impact_log"] > 0], key=lambda z: z["impact_log"], reverse=True)[:top_n]
        neg = sorted([i for i in items if i["impact_log"] < 0], key=lambda z: z["impact_log"])[:top_n]

        # --- Renovation / recommendations
        if n_photos == 0:
            renovation = {
                "condition": "no_photos",
                "condition_label": "нет фото — состояние не оцениваем",
                "confidence": 0.0,
                "confidence_note": "нет данных",
                "signals": [],
                "notes": [
                    "Загрузите 4–10 фото (кухня, санузел, комнаты), чтобы оценить состояние ремонта.",
                ],
            }
            recommendations: List[Dict[str, Any]] = []
        else:
            renovation_raw = self._renovation_zero_shot(emb, threshold=signal_threshold)

            renovation = {
                "condition": renovation_raw.get("condition"),
                "condition_label": renovation_raw.get("condition_label"),
                "confidence": float(renovation_raw.get("confidence", 0.0)),
                "confidence_note": "низкая"
                if float(renovation_raw.get("confidence", 0.0)) < 0.40
                else "средняя/высокая",
                "signals": renovation_raw.get("signals", []),
                "notes": [
                    "Оценка ремонта по фото — ориентировочная (zero-shot CLIP). Если фото мало/темно/без кухни и санузла — уверенность падает."
                ],
            }

            recommendations = self._build_recommendations(renovation_raw)

        # --- Additional clear breakdown (shown factors only)
        total_pos_kzt = sum(i["impact_kzt_total"] for i in pos)
        total_neg_kzt = sum(i["impact_kzt_total"] for i in neg)

        return {
            "prediction": {
                "price": price,
                "price_per_m2": ppm2,
                "currency": "KZT",
                "area": area,
            },
            "model": {
                "target": "log(price_per_m2)",
                "pred_log_price_per_m2": pred_log,
                "base_value": base_value,
                "explain_how_to_read": [
                    "base_value — среднее ожидание модели (в log(price_per_m2)).",
                    "Каждый фактор добавляет или отнимает вклад (impact_log). Сумма вкладов + base_value ≈ pred_log_price_per_m2.",
                    "impact_pct_ppm2 и impact_kzt_* — приближённая интерпретация вкладов для удобства.",
                ],
            },
            "why_this_price": {
                "top_positive": pos,
                "top_negative": neg,
                "summary": {
                    "biggest_plus": pos[0]["feature_label"] if pos else None,
                    "biggest_minus": neg[0]["feature_label"] if neg else None,
                    "photos_effect_pct_ppm2": next((i["impact_pct_ppm2"] for i in items if i["feature"] == "images"), 0.0),
                    "photos_effect_kzt_total": next((i["impact_kzt_total"] for i in items if i["feature"] == "images"), 0.0),
                    "approx_total_effect_kzt_from_shown_factors": float(total_pos_kzt + total_neg_kzt),
                    "note": "Сводка построена по top факторов; мелкие факторы не показаны.",
                },
            },
            "renovation": renovation,
            "recommendations": recommendations,
            "comparables": self._find_similar_ads(x, top_k=3),
        }



    def _impact_to_json(self, fi: FeatureImpact) -> Dict[str, Any]:
        return {
            "feature": fi.feature,
            "value": fi.value,
            "impact": fi.impact,
            "unit": fi.unit,
            "reason": fi.reason,
        }

    # -------------------------
    # Similar listings
    # -------------------------
    def _load_comparables_df(self) -> pd.DataFrame:
        idx_path = self.project_root / "data" / "index" / "index.parquet"
        if idx_path.exists():
            try:
                df = pd.read_parquet(idx_path)
                return self._normalize_comparables_df(df)
            except Exception:
                pass

        rows: List[Dict[str, Any]] = []
        for raw_dir_name in ("raw_ads_test", "raw_ads"):
            raw_dir = self.project_root / "data" / raw_dir_name
            if not raw_dir.exists():
                continue
            for fp in raw_dir.glob("*.json"):
                try:
                    rec = json.loads(fp.read_text(encoding="utf-8"))
                except Exception:
                    continue
                rec["image_paths"] = []
                rec["image_preview"] = (rec.get("image_urls") or [None])[0]
                rows.append(rec)

        if not rows:
            return pd.DataFrame()

        return self._normalize_comparables_df(pd.DataFrame(rows))

    def _ensure_list(self, v: Any) -> List[Any]:
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, tuple):
            return list(v)
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            try:
                obj = json.loads(s)
                if isinstance(obj, list):
                    return obj
            except Exception:
                pass
            return [s]
        return [v]

    def _normalize_comparables_df(self, df: pd.DataFrame) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame()

        work = df.copy()

        for col in ("price", "area", "price_per_m2", "rooms", "year_built", "floor", "floors_total", "latitude", "longitude"):
            if col in work.columns:
                work[col] = pd.to_numeric(work[col], errors="coerce")

        for col in ("district", "building_type", "residential_complex", "url", "ad_id"):
            if col not in work.columns:
                work[col] = None
            else:
                work[col] = work[col].astype("string")

        if "image_paths" not in work.columns:
            work["image_paths"] = [[] for _ in range(len(work))]
        if "image_urls" not in work.columns:
            work["image_urls"] = [[] for _ in range(len(work))]

        work["image_paths"] = work["image_paths"].apply(self._ensure_list)
        work["image_urls"] = work["image_urls"].apply(self._ensure_list)

        if "image_preview" not in work.columns:
            previews: List[Optional[str]] = []
            for _, r in work.iterrows():
                paths = self._ensure_list(r.get("image_paths"))
                urls = self._ensure_list(r.get("image_urls"))
                pv = paths[0] if paths else (urls[0] if urls else None)
                previews.append(pv)
            work["image_preview"] = previews

        return work

    def _to_float(self, v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (list, tuple, np.ndarray)):
            if len(v) == 0:
                return None
            return self._to_float(v[0])
        try:
            is_na = pd.isna(v)
            if isinstance(is_na, (list, tuple, np.ndarray)):
                return None
            if bool(is_na):
                return None
        except Exception:
            pass
        try:
            return float(v)
        except Exception:
            return None

    def _to_str(self, v: Any, default: str = "") -> str:
        if v is None:
            return default
        if isinstance(v, (list, tuple, np.ndarray)):
            if len(v) == 0:
                return default
            return self._to_str(v[0], default=default)
        try:
            is_na = pd.isna(v)
            if isinstance(is_na, (list, tuple, np.ndarray)):
                return default
            if bool(is_na):
                return default
        except Exception:
            pass
        s = str(v).strip()
        return s if s else default

    def _to_nullable_str(self, v: Any) -> Optional[str]:
        s = self._to_str(v, default="")
        return s if s else None

    def _haversine_km(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        r = 6371.0
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
        return 2.0 * r * math.asin(math.sqrt(a))

    def _find_similar_ads(self, x: Dict[str, Any], top_k: int = 3) -> List[Dict[str, Any]]:
        try:
            if self._comparables_df is None or self._comparables_df.empty:
                return []

            q_area = self._to_float(x.get("area"))
            q_rooms = self._to_float(x.get("rooms"))
            q_floor = self._to_float(x.get("floor"))
            q_total = self._to_float(x.get("floors_total"))
            q_year = self._to_float(x.get("year_built"))
            q_lat = self._to_float(x.get("latitude"))
            q_lon = self._to_float(x.get("longitude"))

            q_district = self._to_str(x.get("district")).lower()
            q_building = self._to_str(x.get("building_type")).lower()
            q_complex = self._to_str(x.get("residential_complex")).lower()

            scored: List[Dict[str, Any]] = []

            for _, row in self._comparables_df.iterrows():
                price = self._to_float(row.get("price"))
                area = self._to_float(row.get("area"))
                if price is None or area is None or area <= 0:
                    continue

                score = 0.0

                district = self._to_str(row.get("district")).lower()
                building = self._to_str(row.get("building_type")).lower()
                complex_name = self._to_str(row.get("residential_complex")).lower()

                if q_district and district == q_district:
                    score += 3.0
                if q_building and building == q_building:
                    score += 2.0
                if q_complex and complex_name and complex_name == q_complex:
                    score += 2.5

                row_rooms = self._to_float(row.get("rooms"))
                if q_rooms is not None and row_rooms is not None:
                    score += max(0.0, 1.5 - abs(q_rooms - row_rooms) * 0.7)

                if q_area is not None:
                    score += max(0.0, 3.0 - abs(q_area - area) / 10.0)

                row_year = self._to_float(row.get("year_built"))
                if q_year is not None and row_year is not None:
                    score += max(0.0, 1.5 - abs(q_year - row_year) / 12.0)

                if q_floor is not None and q_total is not None and q_total > 0:
                    q_ratio = q_floor / q_total
                    r_floor = self._to_float(row.get("floor"))
                    r_total = self._to_float(row.get("floors_total"))
                    if r_floor is not None and r_total is not None and r_total > 0:
                        r_ratio = r_floor / r_total
                        score += max(0.0, 1.0 - abs(q_ratio - r_ratio) * 3.0)

                distance_km = None
                r_lat = self._to_float(row.get("latitude"))
                r_lon = self._to_float(row.get("longitude"))
                if q_lat is not None and q_lon is not None and r_lat is not None and r_lon is not None:
                    distance_km = self._haversine_km(q_lat, q_lon, r_lat, r_lon)
                    score += max(0.0, 2.5 - distance_km * 0.6)

                if score <= 0:
                    continue

                scored.append(
                    {
                        "score": float(score),
                        "distance_km": float(distance_km) if distance_km is not None else None,
                        "ad_id": self._to_str(row.get("ad_id")),
                        "url": self._to_nullable_str(row.get("url")),
                        "price": price,
                        "price_per_m2": self._to_float(row.get("price_per_m2")),
                        "area": area,
                        "rooms": self._to_float(row.get("rooms")),
                        "district": self._to_nullable_str(row.get("district")),
                        "building_type": self._to_nullable_str(row.get("building_type")),
                        "residential_complex": self._to_nullable_str(row.get("residential_complex")),
                        "year_built": self._to_float(row.get("year_built")),
                        "floor": self._to_float(row.get("floor")),
                        "floors_total": self._to_float(row.get("floors_total")),
                        "latitude": r_lat,
                        "longitude": r_lon,
                        "image": self._to_nullable_str(row.get("image_preview")),
                    }
                )

            scored.sort(key=lambda z: z["score"], reverse=True)

            out: List[Dict[str, Any]] = []
            seen = set()
            for item in scored:
                ad_id = item.get("ad_id")
                if ad_id in seen:
                    continue
                seen.add(ad_id)
                out.append(item)
                if len(out) >= top_k:
                    break
            return out
        except Exception:
            # Comparables are auxiliary and must never break core predict/explain APIs.
            return []

    # -------------------------
    # CLIP zero-shot renovation module
    # -------------------------
    def _encode_texts(self, texts: List[str]) -> torch.Tensor:
        tokens = self.tokenizer(texts)
        if isinstance(tokens, np.ndarray):
            tokens = torch.from_numpy(tokens)
        tokens = tokens.to(self.device)

        with torch.no_grad():
            t = self.clip_model.encode_text(tokens)
            t = F.normalize(t, dim=-1)
        return t

    def _renovation_zero_shot(self, emb_np: np.ndarray, threshold: float = 0.55) -> Dict[str, Any]:
        # normalize image embedding for cosine similarities
        emb = torch.from_numpy(emb_np).to(self.device).float().unsqueeze(0)
        emb = F.normalize(emb, dim=-1)

        # condition
        cond_keys = [k for k, _ in self._reno_condition_prompts]
        cond_texts = [t for _, t in self._reno_condition_prompts]
        t_cond = self._encode_texts(cond_texts)  # [3, d]

        with torch.no_grad():
            sims = (emb @ t_cond.T).squeeze(0)  # [3]
            probs = torch.softmax(sims, dim=0)

        idx = int(torch.argmax(probs).item())
        condition = cond_keys[idx]
        confidence = float(probs[idx].item())

        condition_label = {
            "fresh": "свежий ремонт",
            "average": "среднее состояние, вероятно нужна косметика",
            "needs": "требует ремонта",
        }.get(condition, condition)

        # signals
        sig_keys = [k for k, _ in self._reno_signal_prompts]
        sig_texts = [t for _, t in self._reno_signal_prompts]
        t_sig = self._encode_texts(sig_texts)  # [m, d]

        with torch.no_grad():
            sig_sims = (emb @ t_sig.T).squeeze(0)  # [m]
            # convert similarity -> pseudo probability [0..1]
            # (simple squashing; tune if нужно)
            sig_probs = torch.sigmoid((sig_sims - sig_sims.mean()) * 3.0)

        signals = []
        for k, p in zip(sig_keys, sig_probs.tolist()):
            p = float(p)
            if p >= threshold:
                signals.append(
                    {
                        "tag": k,
                        "label": self._signal_label(k),
                        "confidence": p,
                    }
                )

        signals = sorted(signals, key=lambda x: x["confidence"], reverse=True)[:6]

        # a simple numeric score to potentially show as "image condition score"
        # fresh~+1, average~0, needs~-1
        score_map = {"needs": -1.0, "average": 0.0, "fresh": 1.0}
        condition_score = float(score_map.get(condition, 0.0))

        return {
            "condition": condition,
            "condition_label": condition_label,
            "confidence": confidence,
            "condition_score": condition_score,
            "signals": signals,
        }

    def _signal_label(self, tag: str) -> str:
        return {
            "kitchen_outdated": "устаревшая кухня",
            "bathroom_outdated": "санузел без свежего ремонта",
            "low_light": "на фото мало света",
            "clutter": "визуальный шум / захламлённость",
            "worn_floor": "виден износ пола",
            "old_windows": "старые окна",
        }.get(tag, tag)

    # -------------------------
    # Recommendations (rule-based)
    # -------------------------
    def _build_recommendations(self, renovation: Dict[str, Any]) -> List[Dict[str, Any]]:
        tags = {s["tag"]: float(s.get("confidence", 0.0)) for s in renovation.get("signals", [])}
        recs: List[Dict[str, Any]] = []

        # priorities: high/medium/low
        if tags.get("kitchen_outdated", 0) > 0:
            recs.append(
                {
                    "title": "Косметика кухни",
                    "why": "кухня сильно влияет на первое впечатление и готовность покупать",
                    "expected_uplift_pct": [2, 4],
                    "priority": "high",
                }
            )
        if tags.get("bathroom_outdated", 0) > 0:
            recs.append(
                {
                    "title": "Освежить санузел",
                    "why": "санузел — зона доверия: состояние отделки и сантехники заметно на фото",
                    "expected_uplift_pct": [1, 3],
                    "priority": "high",
                }
            )
        if tags.get("low_light", 0) > 0:
            recs.append(
                {
                    "title": "Улучшить освещение и переснять фото",
                    "why": "светлые фото повышают конверсию и визуально увеличивают пространство",
                    "expected_uplift_pct": [1, 2],
                    "priority": "medium",
                }
            )
        if tags.get("clutter", 0) > 0:
            recs.append(
                {
                    "title": "Дехламизация перед показами и фотосъёмкой",
                    "why": "убирает визуальный шум и делает комнаты больше на фото",
                    "expected_uplift_pct": [1, 2],
                    "priority": "medium",
                }
            )
        if tags.get("worn_floor", 0) > 0:
            recs.append(
                {
                    "title": "Подправить/обновить пол",
                    "why": "изношенный пол бросается в глаза на фото и снижает ощущение качества",
                    "expected_uplift_pct": [1, 3],
                    "priority": "medium",
                }
            )
        if tags.get("old_windows", 0) > 0:
            recs.append(
                {
                    "title": "Проверить окна и откосы",
                    "why": "окна связаны с теплом/шумом и визуальной аккуратностью",
                    "expected_uplift_pct": [0, 2],
                    "priority": "low",
                }
            )

        # condition-based generic
        if renovation.get("condition") == "needs":
            recs.insert(
                0,
                {
                    "title": "Минимальный косметический ремонт (точечно)",
                    "why": "даже точечные правки повышают восприятие и снижают торг",
                    "expected_uplift_pct": [3, 7],
                    "priority": "high",
                },
            )

        # cap
        return recs[:6]
