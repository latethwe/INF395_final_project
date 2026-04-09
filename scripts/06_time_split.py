import argparse
from pathlib import Path

import pandas as pd


def main(
    parquet_path: str = "data/index/index.parquet",
    out_dir: str = "data/processed",
    train_ratio: float = 0.8,
    val_ratio: float = 0.1,
):
    path = Path(parquet_path)
    if not path.exists():
        raise FileNotFoundError(f"Parquet not found: {path}")

    df = pd.read_parquet(path)
    if df.empty:
        raise ValueError("Empty dataset")

    df["ad_id"] = df["ad_id"].astype(str)
    if "collected_at" in df.columns:
        df["collected_at"] = pd.to_datetime(df["collected_at"], errors="coerce", utc=True)
    else:
        df["collected_at"] = pd.NaT

    # Time-based split: oldest -> newest. Missing timestamps go to the start.
    df = df.sort_values(["collected_at", "ad_id"], ascending=[True, True], na_position="first").reset_index(drop=True)

    n = len(df)
    n_train = int(n * train_ratio)
    n_val = int(n * val_ratio)
    n_test = n - n_train - n_val
    if n_train <= 0 or n_val <= 0 or n_test <= 0:
        raise ValueError(f"Invalid split sizes: train={n_train}, val={n_val}, test={n_test}, total={n}")

    train_ids = df.iloc[:n_train]["ad_id"]
    val_ids = df.iloc[n_train:n_train + n_val]["ad_id"]
    test_ids = df.iloc[n_train + n_val:]["ad_id"]

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    train_ids.to_csv(out / "train_ad_ids.csv", index=False, header=False)
    val_ids.to_csv(out / "val_ad_ids.csv", index=False, header=False)
    test_ids.to_csv(out / "test_ad_ids.csv", index=False, header=False)

    print(f"Saved splits to {out}")
    print(f"Rows: total={n}, train={len(train_ids)}, val={len(val_ids)}, test={len(test_ids)}")
    print(f"collected_at nulls: {int(df['collected_at'].isna().sum())}")
    if df["collected_at"].notna().any():
        print("time range:", df["collected_at"].min(), "->", df["collected_at"].max())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create time-based train/val/test split by collected_at")
    parser.add_argument("--parquet", default="data/index/index.parquet")
    parser.add_argument("--out-dir", default="data/processed")
    parser.add_argument("--train-ratio", type=float, default=0.8)
    parser.add_argument("--val-ratio", type=float, default=0.1)
    args = parser.parse_args()

    main(
        parquet_path=args.parquet,
        out_dir=args.out_dir,
        train_ratio=args.train_ratio,
        val_ratio=args.val_ratio,
    )
