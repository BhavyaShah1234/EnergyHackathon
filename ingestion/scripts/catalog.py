"""Inspect what's landed in the lake.

  python scripts/catalog.py
"""
from __future__ import annotations

from pathlib import Path

import duckdb
from rich.console import Console
from rich.table import Table

from pipeline.config import load_config
from pipeline.registry import REGISTRY


def main() -> None:
    cfg = load_config()
    con_path = cfg.data_root / "_meta" / "catalog.duckdb"
    console = Console()
    if not con_path.exists():
        console.print(f"[yellow]no catalog yet at {con_path} — run `python -m orchestrator.run_once` first")
        return
    con = duckdb.connect(str(con_path), read_only=True)
    table = Table(title=f"Silver catalog — {con_path}")
    for col in ["dataset", "rows", "earliest", "latest", "last_fetch_utc"]:
        table.add_column(col)
    datasets = sorted({e.dataset for e in REGISTRY.values()})
    for ds in datasets:
        try:
            row = con.execute(f"""
                SELECT COUNT(*),
                       MIN(COALESCE(period_utc, interval_start_utc, start_time_utc, timestamp_utc)),
                       MAX(COALESCE(period_utc, interval_start_utc, start_time_utc, timestamp_utc)),
                       MAX(_fetched_at_utc)
                FROM {ds}
            """).fetchone()
        except duckdb.Error as exc:
            table.add_row(ds, "—", "—", "—", f"(no data: {exc.__class__.__name__})")
            continue
        rows, earliest, latest, last_fetch = row
        table.add_row(ds, str(rows), str(earliest), str(latest), str(last_fetch))
    console.print(table)


if __name__ == "__main__":
    main()
