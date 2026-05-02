import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
try:
    from catboost import CatBoostRegressor
except Exception:
    CatBoostRegressor = None


def _load_ids(path: Path) -> set[str]:
    if not path.exists():
        raise FileNotFoundError(path)
    return set(pd.read_csv(path, header=None).iloc[:, 0].astype(str).tolist())


def _normalize_cat(value):
    if value is None:
        return "unknown"
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return "unknown"
    return s


def _prepare_features(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    work["rooms"] = pd.to_numeric(work.get("rooms"), errors="coerce")
    work["floor"] = pd.to_numeric(work.get("floor"), errors="coerce")
    work["floors_total"] = pd.to_numeric(work.get("floors_total"), errors="coerce")
    work["area"] = pd.to_numeric(work.get("area"), errors="coerce")
    work["year_built"] = pd.to_numeric(work.get("year_built"), errors="coerce")
    work["latitude"] = pd.to_numeric(work.get("latitude"), errors="coerce")
    work["longitude"] = pd.to_numeric(work.get("longitude"), errors="coerce")
    if "condition_confidence" in work.columns:
        work["condition_confidence"] = pd.to_numeric(work["condition_confidence"], errors="coerce").fillna(0.0)
    else:
        work["condition_confidence"] = 0.0

    work["floor_ratio"] = np.where(work["floors_total"] > 0, work["floor"] / work["floors_total"], 0.0)
    work["floor_ratio"] = work["floor_ratio"].clip(0, 1)
    work["is_first"] = (work["floor"] == 1).astype(int)
    work["is_last"] = ((work["floors_total"] > 0) & (work["floor"] == work["floors_total"])).astype(int)
    work["building_age"] = 2026 - work["year_built"]
    work["has_geo"] = ((work["latitude"].notna()) & (work["longitude"].notna())).astype(int)
    work["has_residential_complex"] = work.get("residential_complex").fillna("").astype(str).str.strip().ne("").astype(int)

    work["latitude"] = work["latitude"].fillna(43.238949)
    work["longitude"] = work["longitude"].fillna(76.889709)

    for c in ["district", "building_type", "residential_complex", "object_type", "condition_norm", "condition_source"]:
        if c not in work.columns:
            work[c] = "unknown"
        work[c] = work[c].apply(_normalize_cat)

    num_features = [
        "area",
        "rooms",
        "floor",
        "floors_total",
        "floor_ratio",
        "is_first",
        "is_last",
        "building_age",
        "latitude",
        "longitude",
        "has_geo",
        "has_residential_complex",
        "condition_confidence",
    ]
    cat_features = [
        "district",
        "building_type",
        "residential_complex",
        "object_type",
        "condition_norm",
        "condition_source",
    ]

    all_features = num_features + cat_features
    return work, all_features, cat_features


def _metrics(y_true_log: np.ndarray, y_pred_log: np.ndarray, area: np.ndarray) -> dict:
    y_true_ppm2 = np.exp(y_true_log)
    y_pred_ppm2 = np.exp(y_pred_log)

    y_true_price = y_true_ppm2 * area
    y_pred_price = y_pred_ppm2 * area

    def _mae(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.mean(np.abs(a - b)))

    def _rmse(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.sqrt(np.mean((a - b) ** 2)))

    return {
        "mae_ppm2": _mae(y_true_ppm2, y_pred_ppm2),
        "rmse_ppm2": _rmse(y_true_ppm2, y_pred_ppm2),
        "mae_price": _mae(y_true_price, y_pred_price),
        "rmse_price": _rmse(y_true_price, y_pred_price),
    }


def main(parquet: str = "data/index/index.parquet", splits_dir: str = "data/processed", out_json: str = "data/processed/time_eval_metrics.json"):
    df = pd.read_parquet(parquet)
    if df.empty:
        raise ValueError("Empty dataset")

    df["ad_id"] = df["ad_id"].astype(str)
    df["price_per_m2"] = pd.to_numeric(df.get("price_per_m2"), errors="coerce")
    df["area"] = pd.to_numeric(df.get("area"), errors="coerce")
    df = df[(df["price_per_m2"] > 0) & (df["area"] > 0)].copy()
    df["target_log_ppm2"] = np.log(df["price_per_m2"].astype(float))

    split_dir = Path(splits_dir)
    train_ids = _load_ids(split_dir / "train_ad_ids.csv")
    val_ids = _load_ids(split_dir / "val_ad_ids.csv")
    test_ids = _load_ids(split_dir / "test_ad_ids.csv")

    train_df = df[df["ad_id"].isin(train_ids)].copy()
    val_df = df[df["ad_id"].isin(val_ids)].copy()
    test_df = df[df["ad_id"].isin(test_ids)].copy()

    for name, part in [("train", train_df), ("val", val_df), ("test", test_df)]:
        if part.empty:
            raise ValueError(f"Split {name} is empty")

    train_df, all_features, cat_features = _prepare_features(train_df)
    val_df, _, _ = _prepare_features(val_df)
    test_df, _, _ = _prepare_features(test_df)

    model_name = "catboost"
    if CatBoostRegressor is not None:
        model_kwargs = dict(
            loss_function="RMSE",
            eval_metric="RMSE",
            depth=8,
            learning_rate=0.05,
            n_estimators=1200,
            random_seed=42,
            verbose=False,
        )
        model_kwargs_gpu = dict(model_kwargs)
        model_kwargs_gpu.update(dict(task_type="GPU", devices="0"))
        model = CatBoostRegressor(**model_kwargs_gpu)
        try:
            model.fit(
                train_df[all_features],
                train_df["target_log_ppm2"],
                cat_features=cat_features,
                eval_set=(val_df[all_features], val_df["target_log_ppm2"]),
                use_best_model=True,
            )
        except Exception:
            # Fallback to CPU if GPU runtime is unavailable.
            model = CatBoostRegressor(**model_kwargs)
            model.fit(
                train_df[all_features],
                train_df["target_log_ppm2"],
                cat_features=cat_features,
                eval_set=(val_df[all_features], val_df["target_log_ppm2"]),
                use_best_model=True,
            )
        val_pred = model.predict(val_df[all_features])
        test_pred = model.predict(test_df[all_features])
    else:
        # Fallback without external ML deps: OLS over one-hot encoded features.
        model_name = "ols_fallback"
        train_X = pd.get_dummies(train_df[all_features], columns=cat_features, dtype=float)
        val_X = pd.get_dummies(val_df[all_features], columns=cat_features, dtype=float)
        test_X = pd.get_dummies(test_df[all_features], columns=cat_features, dtype=float)

        cols = sorted(set(train_X.columns) | set(val_X.columns) | set(test_X.columns))
        train_X = train_X.reindex(columns=cols, fill_value=0.0)
        val_X = val_X.reindex(columns=cols, fill_value=0.0)
        test_X = test_X.reindex(columns=cols, fill_value=0.0)

        X = train_X.to_numpy(dtype=float)
        y = train_df["target_log_ppm2"].to_numpy(dtype=float)
        X_aug = np.column_stack([np.ones(len(X)), X])
        beta, *_ = np.linalg.lstsq(X_aug, y, rcond=None)

        val_aug = np.column_stack([np.ones(len(val_X)), val_X.to_numpy(dtype=float)])
        test_aug = np.column_stack([np.ones(len(test_X)), test_X.to_numpy(dtype=float)])
        val_pred = val_aug @ beta
        test_pred = test_aug @ beta

    report = {
        "dataset_rows": int(len(df)),
        "splits": {
            "train": int(len(train_df)),
            "val": int(len(val_df)),
            "test": int(len(test_df)),
        },
        "features": {
            "num": [f for f in all_features if f not in cat_features],
            "cat": cat_features,
        },
        "model": model_name,
        "metrics_val": _metrics(
            val_df["target_log_ppm2"].to_numpy(dtype=float),
            np.asarray(val_pred, dtype=float),
            val_df["area"].to_numpy(dtype=float),
        ),
        "metrics_test": _metrics(
            test_df["target_log_ppm2"].to_numpy(dtype=float),
            np.asarray(test_pred, dtype=float),
            test_df["area"].to_numpy(dtype=float),
        ),
    }

    out_path = Path(out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Saved: {out_path}")
    print(json.dumps(report["metrics_test"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train/evaluate baseline with time-based split")
    parser.add_argument("--parquet", default="data/index/index.parquet")
    parser.add_argument("--splits-dir", default="data/processed")
    parser.add_argument("--out-json", default="data/processed/time_eval_metrics.json")
    args = parser.parse_args()

    main(parquet=args.parquet, splits_dir=args.splits_dir, out_json=args.out_json)
