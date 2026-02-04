# app/explain/renovation.py
from typing import Any, Dict, List
import numpy as np

class RenovationModule:
    def __init__(self, est):
        self.est = est
        # загрузить маленькие модели (logreg / lightgbm) для condition и signals
        self.condition_clf = est.load_condition_model()
        self.signal_clfs = est.load_signal_models()  # dict(tag -> model)

    def infer(self, images: List[Any]) -> Dict[str, Any]:
        # 1) эмбеддинги на каждую картинку
        emb = self.est.image_encoder.encode(images)   # (n, d)
        emb_mean = emb.mean(axis=0, keepdims=True)    # (1, d)

        # 2) condition
        proba = self.condition_clf.predict_proba(emb_mean)[0]
        classes = list(self.condition_clf.classes_)  # ["fresh","average","needs"]
        idx = int(np.argmax(proba))
        condition = classes[idx]
        confidence = float(proba[idx])

        # score -1..+1 (пример)
        score_map = {"needs": -1.0, "average": 0.0, "fresh": 1.0}
        condition_score = score_map.get(condition, 0.0)

        # 3) signals
        signals = []
        signal_scores = []
        for tag, clf in self.signal_clfs.items():
            p = float(clf.predict_proba(emb_mean)[0][1])  # бинарный класс=1
            signal_scores.append({"tag": tag, "score": p})
            if p >= 0.55:
                signals.append({
                    "tag": tag,
                    "label": self._label(tag),
                    "confidence": p
                })

        return {
            "condition": condition,
            "condition_label": self._label_condition(condition),
            "confidence": confidence,
            "condition_score": float(condition_score),
            "signals": sorted(signals, key=lambda x: x["confidence"], reverse=True)[:6],
            "signal_scores": signal_scores
        }

    def _label_condition(self, c: str) -> str:
        return {
            "fresh": "свежий ремонт",
            "average": "среднее, вероятно нужна косметика",
            "needs": "требует ремонта"
        }.get(c, "не удалось определить")

    def _label(self, tag: str) -> str:
        return {
            "kitchen_outdated": "устаревшая кухня",
            "bathroom_outdated": "санузел без свежего ремонта",
            "low_light": "на фото мало света",
            "clutter": "много визуального шума/захламлённость",
            "floor_wear": "виден износ пола",
        }.get(tag, tag)
