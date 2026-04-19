"""Answer: 'where did this silver row come from, and if it's gone, why?'

Usage:
  python scripts/explain.py --dataset eia930 --key '{"period_utc":"2026-04-18 15:00:00+00:00","respondent":"AZPS","type":"D"}'

Prints the full fetch history for that natural key: every request_id that ever
produced the row, which one is current, which ones were superseded, and the
path to the raw API envelope so you can re-parse it.
"""
from __future__ import annotations

import argparse
import json

from rich.console import Console
from rich.table import Table

from pipeline.audit import explain_row
from pipeline.config import load_config


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--key", required=True, help="JSON dict of natural key columns")
    args = ap.parse_args()

    cfg = load_config()
    catalog = cfg.data_root / "_meta" / "catalog.duckdb"
    # Normalize key JSON so it matches the canonical form we store.
    key_obj = json.loads(args.key)
    key_json = json.dumps({k: str(v) for k, v in key_obj.items()}, separators=(",", ":"))
    hist = explain_row(catalog, args.dataset, key_json)

    console = Console()
    if hist.empty:
        console.print(f"[yellow]no lineage rows for dataset={args.dataset} key={key_json}")
        return
    table = Table(title=f"{args.dataset} :: {key_json}")
    for col in ["request_id", "fetched_at_utc", "payload_sha256", "superseded_by", "raw_path"]:
        table.add_column(col)
    for _, r in hist.iterrows():
        table.add_row(
            str(r["request_id"]),
            str(r["fetched_at_utc"]),
            str(r["payload_sha256"])[:12],
            str(r["superseded_by"] or "CURRENT"),
            str(r["raw_path"]),
        )
    console.print(table)


if __name__ == "__main__":
    main()
