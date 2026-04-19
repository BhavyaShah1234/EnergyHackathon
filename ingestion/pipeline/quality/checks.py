"""DQ checks run on every bronze → silver promotion.

Philosophy: fail loud, never silently. Corrupt rows go to `data/quarantine/` with
a reason column so you can audit the rejection rate per source per day.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pandera.pandas as pa


@dataclass
class CheckResult:
    dataset: str
    rows_in: int
    rows_out: int
    rows_quarantined: int
    null_rate_by_col: dict[str, float] = field(default_factory=dict)
    freshness_minutes: float | None = None
    freshness_ok: bool = True
    schema_errors: list[str] = field(default_factory=list)
    dup_rate: float = 0.0
    ok: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def validate(
    df: pd.DataFrame,
    schema: pa.DataFrameSchema,
    *,
    dataset: str,
    freshness_sla_hours: float,
    freshness_col: str,
    natural_key: list[str],
    quarantine_dir: Path,
) -> tuple[pd.DataFrame, CheckResult]:
    """Run schema + freshness + dedup checks. Return (clean_df, report).

    Rows failing validation are written to quarantine_dir with a `_reason` column.
    If the schema itself is broken (wrong columns), we raise — the pipeline must
    stop, not ship garbage.
    """
    result = CheckResult(dataset=dataset, rows_in=len(df), rows_out=0, rows_quarantined=0)

    if df.empty:
        result.ok = False
        result.schema_errors.append("empty_dataframe")
        return df, result

    # --- Schema: coerce + validate, collect failures lazily ---
    try:
        valid_df = schema.validate(df, lazy=True)
    except pa.errors.SchemaErrors as exc:
        # Split: keep rows that passed, quarantine the rest.
        bad_idx = sorted(set(exc.failure_cases["index"].dropna().astype(int).tolist()))
        counts = exc.failure_cases.groupby("check")["check"].count().to_dict()
        result.schema_errors = [f"{check}={n}" for check, n in counts.items()]
        bad = df.loc[df.index.isin(bad_idx)].copy()
        bad["_reason"] = "schema_violation"
        _write_quarantine(bad, quarantine_dir, dataset)
        result.rows_quarantined += len(bad)
        valid_df = df.loc[~df.index.isin(bad_idx)]
        try:
            valid_df = schema.validate(valid_df, lazy=False)
        except pa.errors.SchemaError as hard:
            result.ok = False
            result.schema_errors.append(f"fatal={hard}")
            return valid_df, result

    # --- Dedup on natural key (idempotency guarantee) ---
    before = len(valid_df)
    valid_df = valid_df.drop_duplicates(subset=natural_key, keep="last")
    dup_count = before - len(valid_df)
    result.dup_rate = dup_count / before if before else 0.0

    # --- Null rate per column (informational, not blocking) ---
    result.null_rate_by_col = {
        c: float(valid_df[c].isna().mean()) for c in valid_df.columns
    }

    # --- Freshness SLA ---
    if freshness_col in valid_df.columns and not valid_df.empty:
        latest = pd.to_datetime(valid_df[freshness_col]).max()
        if latest.tzinfo is None:
            latest = latest.tz_localize("UTC")
        now = pd.Timestamp.now(tz="UTC")
        age_min = (now - latest).total_seconds() / 60.0
        result.freshness_minutes = age_min
        result.freshness_ok = age_min <= freshness_sla_hours * 60.0
    else:
        result.freshness_ok = False

    result.rows_out = len(valid_df)
    result.ok = bool(
        not result.schema_errors
        and result.freshness_ok
        and result.rows_out > 0
    )
    return valid_df, result


def _write_quarantine(df: pd.DataFrame, quarantine_dir: Path, dataset: str) -> None:
    if df.empty:
        return
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out = quarantine_dir / dataset / f"{day}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    # Append-friendly: write a new file per run via timestamp suffix.
    ts = datetime.now(timezone.utc).strftime("%H%M%S")
    out = out.with_name(f"{day}_{ts}.parquet")
    df.to_parquet(out, index=False)
