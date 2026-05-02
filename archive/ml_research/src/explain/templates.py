# app/explain/templates.py
from typing import List, Dict
from .....apps.backend.ml.v2_infer import FeatureImpact

REASONS = {
  "district": "район влияет на спрос и ликвидность",
  "area": "площадь напрямую масштабирует цену",
  "year_built": "год постройки влияет на состояние дома/коммуникаций",
  "building_type": "тип дома влияет на восприятие качества и ликвидность",
  "image_condition_score": "состояние по фото влияет на готовность покупателей платить",
}

def add_reasons(items: List[FeatureImpact]) -> List[FeatureImpact]:
    for x in items:
        if x.reason is None:
            x.reason = REASONS.get(x.feature)
    return items

def build_recommendations(renov: Dict, pos: List[FeatureImpact], neg: List[FeatureImpact]) -> List[Dict]:
    recs = []
    tags = {s["tag"]: s["confidence"] for s in renov.get("signals", [])}

    if tags.get("kitchen_outdated", 0) >= 0.55:
        recs.append({
          "title":"Косметика кухни",
          "why":"кухня сильнее всего влияет на первое впечатление",
          "expected_uplift_pct":[2,4],
          "priority":"high"
        })

    if tags.get("bathroom_outdated", 0) >= 0.55:
        recs.append({
          "title":"Освежить санузел",
          "why":"санузел — критичная зона доверия к состоянию квартиры",
          "expected_uplift_pct":[1,3],
          "priority":"high"
        })

    if tags.get("low_light", 0) >= 0.55:
        recs.append({
          "title":"Свет и фотографии",
          "why":"улучшите освещение и переснимите — повышает конверсию и восприятие",
          "expected_uplift_pct":[1,2],
          "priority":"medium"
        })

    # ограничим
    return recs[:5]
