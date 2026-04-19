"""Bronze/silver storage + DuckDB catalog.

Raw: untouched API bodies in data/raw/<source>/<date>/<request_id>.json
Bronze: per-run parsed parquet in data/bronze/<source>/<date>/<request_id>.parquet
Silver: merged, validated, deduplicated in data/silver/<dataset>/<date>.parquet
       — this is what modelers read.
Catalog: data/_meta/catalog.duckdb registers every silver table as a view.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd


def write_bronze(df: pd.DataFrame, source: str, request_id: str, data_root: Path) -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = data_root / "bronze" / source / day / f"{request_id}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out


def merge_silver(
    df: pd.DataFrame,
    dataset: str,
    natural_key: list[str],
    partition_col: str,
    data_root: Path,
) -> Path:
    """Merge new rows into the silver partition for their date, dedup on natural_key.

    This is the idempotency guarantee: re-running with overlapping data produces
    an identical silver file. `keep="last"` means the freshest fetch wins on conflict.
    """
    if df.empty:
        return data_root / "silver" / dataset
    df = df.copy()
    df[partition_col] = pd.to_datetime(df[partition_col], utc=True)
    df["_partition_date"] = df[partition_col].dt.strftime("%Y-%m-%d")

    silver_root = data_root / "silver" / dataset
    silver_root.mkdir(parents=True, exist_ok=True)

    last_path: Path | None = None
    for day, group in df.groupby("_partition_date"):
        out = silver_root / f"{day}.parquet"
        if out.exists():
            existing = pd.read_parquet(out)
            combined = pd.concat([existing, group.drop(columns="_partition_date")], ignore_index=True)
        else:
            combined = group.drop(columns="_partition_date")
        combined = combined.drop_duplicates(subset=natural_key, keep="last").sort_values(natural_key)
        combined.to_parquet(out, index=False)
        last_path = out
    return last_path or silver_root


def register_in_catalog(dataset: str, data_root: Path) -> None:
    """Expose silver as a DuckDB view. Cheap — call after every silver write."""
    catalog_path = data_root / "_meta" / "catalog.duckdb"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    silver_glob = str(data_root / "silver" / dataset / "*.parquet").replace("'", "''")
    con = duckdb.connect(str(catalog_path))
    try:
        con.execute(
            f"CREATE OR REPLACE VIEW {dataset} AS "
            f"SELECT * FROM read_parquet('{silver_glob}', union_by_name=true)"
        )
    finally:
        con.close()
