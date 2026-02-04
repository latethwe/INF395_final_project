# app/explain/explainer.py
from typing import Dict, List, Tuple
from ..v2_infer import FeatureImpact

class ModelExplainer:
    def __init__(self, est):
        self.est = est
        self._shap_explainer = None
        self._background = None

        # лениво, чтобы быстро стартовать API
        self._init()

    def _init(self):
        import shap
        # background: небольшой сэмпл тренировочных данных (например 256 строк)
        # важно: это не изображения, а уже готовые табличные признаки.
        self._background = self.est.load_background_matrix(n=256)  # сделайте хелпер
        self._shap_explainer = shap.Explainer(self.est.model, self._background)

    def local_explain(self, feats: Dict[str, any]) -> Tuple[float, List[FeatureImpact]]:
        X = self.est._to_model_input(feats)
        sv = self._shap_explainer(X)

        base = float(sv.base_values[0])
        impacts: List[FeatureImpact] = []

        # маппим индексы в имена колонок
        cols = self.est.preproc.feature_names_
        vals = self.est.preproc.last_input_values_  # если сможете сохранить; иначе feats

        for j, name in enumerate(cols):
            impact = float(sv.values[0][j])
            value = vals.get(name) if isinstance(vals, dict) else None
            impacts.append(FeatureImpact(feature=name, value=value, impact=impact))

        return base, impacts
