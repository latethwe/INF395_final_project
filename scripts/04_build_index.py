import json
import math
from pathlib import Path

import pandas as pd

def main(
    raw_dir="data/raw_ads",
    img_root="data/images",
    out_path="data/index/index.parquet",
    min_images=3,
    require_local_images=False,
):
    rows = []
    for fp in Path(raw_dir).glob("*.json"):
        rec = json.loads(fp.read_text(encoding="utf-8"))

        ppm = rec.get("price_per_m2")
        if not ppm or ppm <= 0:
            continue

        paths = []
        img_dir = Path(img_root) / rec["ad_id"]
        if img_dir.exists():
            for ext in ("*.jpg", "*.jpeg", "*.webp", "*.png"):
                paths.extend([str(p) for p in img_dir.glob(ext)])
        paths = sorted(paths)

        image_urls = rec.get("image_urls") or []
        image_count = len(paths) if paths else len(image_urls)
        if image_count < min_images:
            continue
        if require_local_images and len(paths) < min_images:
            continue

        rows.append({
            "ad_id": rec["ad_id"],
            "url": rec.get("url"),

            "price": rec.get("price"),
            "area": rec.get("area"),
            "price_per_m2": ppm,
            "log_price_per_m2": math.log(ppm),

            "rooms": rec.get("rooms"),
            "district": rec.get("district"),
            "building_type": rec.get("building_type"),
            "residential_complex": rec.get("residential_complex"),
            "year_built": rec.get("year_built"),
            "floor": rec.get("floor"),
            "floors_total": rec.get("floors_total"),
            "latitude": rec.get("latitude"),
            "longitude": rec.get("longitude"),

            "image_paths": paths,
            "image_urls": image_urls,
        })

    df = pd.DataFrame(rows)

    # нормализация типов
    for c in ["rooms", "year_built", "floor", "floors_total", "latitude", "longitude"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    print("Saved:", out_path, "rows:", len(df))

if __name__ == "__main__":
    main()
