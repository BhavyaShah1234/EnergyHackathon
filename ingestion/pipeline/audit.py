"""Audit log + lineage — the 'if data is gone, why and how' layer.

Three layered records:

1. **audit.jsonl** — append-only, one line per HTTP fetch *and* every DQ outcome.
   Never overwritten. This is the ground truth for "was this data ever fetched?".

2. **run_ledger** (DuckDB) — one row per (run_id, dataset) with rows_in/out/quarantined,
   freshness, status, error_msg. Fast to query: "which runs failed this week?".

3. **lineage** (DuckDB) — one row per (dataset, natural_key, request_id) recording which
   fetch first produced that row and which fetch superseded it (dedup winner). Lets you
   answer: "why is this row in silver?", "when did it change?", "where's the raw payload?".

If a row disappears from silver, lineage tells you whether it was (a) quarantined — with
the reason + path to the quarantine parquet, (b) never fetched this run — freshness
degraded, or (c) overwritten by a fresher request — with the new request_id.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd


@dataclass
class AuditEvent:
    event: str                      # "fetch", "parse_error", "validate", "silver_merge", "quarantine"
    run_id: str
    source: str
    dataset: str
    ts_utc: str
    details: dict[str, Any]


class AuditLog:
    """Append-only JSONL — rotate by day, never modify past days.

    JSONL is chosen over a DB so recovery after a crash is trivial: lines either
    landed or didn't, no half-written rows. `flush()` after every write so a SIGKILL
    loses at most the in-flight event.
    """

    def __init__(self, meta_dir: Path):
        self.dir = meta_dir / "audit"
        self.dir.mkdir(parents=True, exist_ok=True)

    def _path(self) -> Path:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.dir / f"{day}.jsonl"

    def write(self, event: AuditEvent) -> None:
        line = json.dumps(
            {
                "event": event.event,
                "run_id": event.run_id,
                "source": event.source,
                "dataset": event.dataset,
                "ts_utc": event.ts_utc,
                "details": event.details,
            },
            separators=(",", ":"),
            default=str,
        )
        with self._path().open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()


# ---------- DuckDB-backed ledger + lineage ----------

_DDL = [
    """
    CREATE TABLE IF NOT EXISTS run_ledger (
        run_id          VARCHAR,
        dataset         VARCHAR,
        source          VARCHAR,
        started_at_utc  TIMESTAMP,
        finished_at_utc TIMESTAMP,
        rows_in         INTEGER,
        rows_out        INTEGER,
        rows_quarantined INTEGER,
        freshness_min   DOUBLE,
        status          VARCHAR,
        error           VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lineage (
        dataset         VARCHAR,
        natural_key     VARCHAR,         -- JSON-encoded tuple of the key columns
        request_id      VARCHAR,         -- fetch that produced/updated this row
        payload_sha256  VARCHAR,
        fetched_at_utc  TIMESTAMP,
        raw_path        VARCHAR,         -- pointer to data/raw/... JSON envelope
        superseded_by   VARCHAR,         -- request_id of the fetch that overwrote it, NULL if current
        superseded_at_utc TIMESTAMP
    )
    """,
]


def _connect(catalog_path: Path) -> duckdb.DuckDBPyConnection:
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(catalog_path))
    for stmt in _DDL:
        con.execute(stmt)
    return con


def record_run(
    catalog_path: Path,
    *,
    run_id: str,
    dataset: str,
    source: str,
    started_at: datetime,
    finished_at: datetime,
    rows_in: int,
    rows_out: int,
    rows_quarantined: int,
    freshness_min: float | None,
    status: str,
    error: str | None,
) -> None:
    con = _connect(catalog_path)
    try:
        con.execute(
            "INSERT INTO run_ledger VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                run_id, dataset, source,
                started_at, finished_at,
                rows_in, rows_out, rows_quarantined,
                freshness_min, status, error,
            ],
        )
    finally:
        con.close()


def record_lineage(
    catalog_path: Path,
    *,
    dataset: str,
    df: pd.DataFrame,
    natural_key: list[str],
    raw_path: Path,
) -> None:
    """Insert one lineage row per (natural_key, request_id). Supersession is
    updated by a second pass: any prior row with the same natural_key whose
    superseded_by is NULL gets stamped."""
    if df.empty:
        return
    con = _connect(catalog_path)
    try:
        for _, row in df.iterrows():
            key = json.dumps({k: str(row[k]) for k in natural_key}, separators=(",", ":"))
            con.execute(
                """
                UPDATE lineage
                SET superseded_by = ?, superseded_at_utc = ?
                WHERE dataset = ? AND natural_key = ? AND superseded_by IS NULL
                  AND request_id <> ?
                """,
                [row["_request_id"], row["_fetched_at_utc"], dataset, key, row["_request_id"]],
            )
            con.execute(
                "INSERT INTO lineage VALUES (?,?,?,?,?,?,NULL,NULL)",
                [
                    dataset, key, row["_request_id"],
                    row["_payload_sha256"], row["_fetched_at_utc"], str(raw_path),
                ],
            )
    finally:
        con.close()


def explain_row(catalog_path: Path, dataset: str, natural_key_json: str) -> pd.DataFrame:
    """Return full history for a row: every fetch that ever touched it."""
    con = _connect(catalog_path)
    try:
        return con.execute(
            """
            SELECT request_id, payload_sha256, fetched_at_utc, raw_path,
                   superseded_by, superseded_at_utc
            FROM lineage
            WHERE dataset = ? AND natural_key = ?
            ORDER BY fetched_at_utc
            """,
            [dataset, natural_key_json],
        ).df()
    finally:
        con.close()
