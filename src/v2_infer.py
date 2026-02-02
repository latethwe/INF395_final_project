import json
from pathlib import Path
from typing import List, Optional, Dict, Any

import numpy as np
import pandas as pd
from PIL import Image

from catboost import CatBoostRegressor

import torch
import open_clip


class V2Estimator:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

        meta_path = self.project_root / "models" / "v2_metadata.json"
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

        self.device = torch.device("cpu")
        self.clip_model, _, self.preprocess = open_clip.create_model_and_transforms(
            self.clip_model_name, pretrained=self.clip_pretrained, device=self.device
        )
        self.clip_model.eval()

        # Features
        self.features_num = self.meta["features_num"]
        self.features_cat = self.meta["features_cat"]
        self.features = self.features_num + self.features_cat
        self.current_year = int(self.meta["current_year"])

        # Determine embedding dim
        with torch.no_grad():
            dummy = torch.zeros(1, 3, 224, 224, device=self.device)
            z = self.clip_model.encode_image(dummy)
            self.emb_dim = int(z.shape[-1])

        # Create embedding column names
        self.emb_cols = [f"clip_{i:03d}" for i in range(self.emb_dim)]

    def _encode_images(self, image_paths: List[Path]) -> np.ndarray:
        tensors = []
        for p in image_paths[: self.max_images]:
            try:
                img = Image.open(p).convert("RGB")
                tensors.append(self.preprocess(img))
            except Exception:
                continue

        if not tensors:
            # fallback: all zeros
            return np.zeros((self.emb_dim,), dtype=np.float32)

        imgs = torch.stack(tensors, dim=0).to(self.device)

        with torch.no_grad():
            feats = self.clip_model.encode_image(imgs)  # [k, dim]
            if self.normalize_per_image:
                feats = torch.nn.functional.normalize(feats, dim=-1)
            feats = feats.cpu().numpy().astype(np.float32)

        emb = feats.mean(axis=0)
        if self.normalize_agg:
            emb = emb / (np.linalg.norm(emb) + 1e-12)
        return emb.astype(np.float32)

    def _make_tabular_row(self, x: Dict[str, Any]) -> Dict[str, Any]:
        area = float(x["area"])
        rooms = int(x["rooms"])
        floor = int(x["floor"])
        floors_total = int(x["floors_total"])
        year_built = int(x["year_built"])

        district = str(x["district"])
        building_type = str(x["building_type"])

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
            "district": district,
            "building_type": building_type,
        }

    def predict(
        self,
        x: Dict[str, Any],
        image_files: List[Path],
    ) -> Dict[str, float]:
        tab = self._make_tabular_row(x)
        emb = self._encode_images(image_files)

        row = {**tab, **{c: float(v) for c, v in zip(self.emb_cols, emb)}}
        X = pd.DataFrame([row], columns=self.features + self.emb_cols)

        pred_log = float(self.model.predict(X))
        ppm2 = float(np.exp(pred_log))
        price = float(ppm2 * float(tab["area"]))

        return {
            "pred_log_price_per_m2": pred_log,
            "price_per_m2": ppm2,
            "price": price,
        }
