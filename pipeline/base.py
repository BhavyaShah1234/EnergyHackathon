"""Base ingestor — every source subclasses this.

Lifecycle per run:
  1. fetch(): HTTP call(s) to upstream API. Raw response persisted to data/raw.
  2. parse(): API-specific JSON/CSV → tidy DataFrame.
  3. _stamp_provenance(): inject _source, _request_id, _fetched_at_utc, _payload_sha256.
  4. quality.validate(): schema + freshness + dedup. Bad rows → quarantine.
  5. storage.write_bronze() + storage.merge_silver() + storage.register_in_catalog().
  6. return CheckResult for the run report.

Subclasses implement fetch() and parse() only.
"""
from __future__ import annotations

import abc
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import pandera as pa

from .audit import AuditEvent, AuditLog, record_lineage, record_run
from .config import PipelineConfig, SourceSpec, load_config
from .http_client import FetchResult, HttpClient
from .integrity import update_manifest
from .quality.checks import CheckResult, validate
from .storage import merge_silver, register_in_catalog, write_bronze


@dataclass
class ParsedBatch:
    """One fetch's worth of parsed rows + the FetchResult that produced them."""
    df: pd.DataFrame
    fetch: FetchResult


class BaseIngestor(abc.ABC):
    """Subclass and set class vars SOURCE, DATASET, SCHEMA, PARTITION_COL."""

    SOURCE: str = ""            # key in config/sources.yaml
    DATASET: str = ""           # silver table name (may group multiple sources; e.g. eia930)
    PARTITION_COL: str = ""     # timestamp column used to partition silver (UTC)
    SCHEMA: pa.DataFrameSchema | None = None

    def __init__(self, http: HttpClient, cfg: PipelineConfig | None = None):
        if not (self.SOURCE and self.DATASET and self.PARTITION_COL and self.SCHEMA):
            raise RuntimeError(f"{type(self).__name__} is missing class vars")
        self.http = http
        self.cfg = cfg or load_config()
        self.spec: SourceSpec = self.cfg.sources[self.SOURCE]

    # --- Subclass hooks ---
    @abc.abstractmethod
    def fetch(self) -> Iterable[FetchResult]:
        """Yield one FetchResult per upstream call. Most sources yield exactly one."""

    @abc.abstractmethod
    def parse(self, fetch: FetchResult) -> pd.DataFrame:
        """Convert raw bytes to a tidy DataFrame matching SCHEMA (minus provenance)."""

    # --- Entrypoint ---
    def run(self, run_id: str | None = None) -> CheckResult:
        run_id = run_id or uuid.uuid4().hex[:8]
        started = datetime.now(timezone.utc)
        audit = AuditLog(self.cfg.data_root / "_meta")
        catalog = self.cfg.data_root / "_meta" / "catalog.duckdb"
        last_raw: Path | None = None

        frames: list[pd.DataFrame] = []
        for fr in self.fetch():
            last_raw = fr.raw_path
            audit.write(AuditEvent(
                event="fetch", run_id=run_id, source=self.SOURCE, dataset=self.DATASET,
                ts_utc=fr.fetched_at_utc.isoformat(),
                details={
                    "request_id": fr.request_id, "url": fr.url,
                    "status": fr.status_code, "sha256": fr.payload_sha256,
                    "raw_path": str(fr.raw_path),
                },
            ))
            try:
                df = self.parse(fr)
            except Exception as exc:
                audit.write(AuditEvent(
                    event="parse_error", run_id=run_id, source=self.SOURCE, dataset=self.DATASET,
                    ts_utc=datetime.now(timezone.utc).isoformat(),
                    details={"request_id": fr.request_id, "error": f"{type(exc).__name__}: {exc}"},
                ))
                report = CheckResult(
                    dataset=self.DATASET, rows_in=0, rows_out=0, rows_quarantined=0,
                    schema_errors=[f"parser_error: {exc.__class__.__name__}: {exc}"], ok=False,
                )
                self._finalize_run(run_id, started, report, catalog)
                return report
            if df.empty:
                continue
            df = self._stamp_provenance(df, fr)
            write_bronze(df, self.SOURCE, fr.request_id, self.cfg.data_root)
            frames.append(df)

        if not frames:
            report = CheckResult(
                dataset=self.DATASET, rows_in=0, rows_out=0, rows_quarantined=0,
                schema_errors=["no_rows_returned"], ok=False,
            )
            self._finalize_run(run_id, started, report, catalog)
            return report

        all_df = pd.concat(frames, ignore_index=True)
        clean, report = validate(
            all_df,
            self.SCHEMA,
            dataset=self.DATASET,
            freshness_sla_hours=self.spec.freshness_sla_hours,
            freshness_col=self.PARTITION_COL,
            natural_key=self.spec.natural_key,
            quarantine_dir=self.cfg.data_root / "quarantine",
        )
        if not clean.empty:
            merge_silver(
                clean,
                self.DATASET,
                natural_key=self.spec.natural_key,
                partition_col=self.PARTITION_COL,
                data_root=self.cfg.data_root,
            )
            register_in_catalog(self.DATASET, self.cfg.data_root)
            if last_raw is not None:
                record_lineage(
                    catalog, dataset=self.DATASET, df=clean,
                    natural_key=self.spec.natural_key, raw_path=last_raw,
                )
            update_manifest(
                self.cfg.data_root / "silver",
                self.cfg.data_root / "_meta" / "manifest.json",
            )

        audit.write(AuditEvent(
            event="validate", run_id=run_id, source=self.SOURCE, dataset=self.DATASET,
            ts_utc=datetime.now(timezone.utc).isoformat(),
            details={
                "rows_in": report.rows_in, "rows_out": report.rows_out,
                "rows_quarantined": report.rows_quarantined,
                "schema_errors": report.schema_errors,
                "freshness_min": report.freshness_minutes,
                "ok": report.ok,
            },
        ))
        self._finalize_run(run_id, started, report, catalog)
        return report

    def _finalize_run(self, run_id: str, started: datetime, report: CheckResult, catalog: Path) -> None:
        record_run(
            catalog,
            run_id=run_id, dataset=self.DATASET, source=self.SOURCE,
            started_at=started, finished_at=datetime.now(timezone.utc),
            rows_in=report.rows_in, rows_out=report.rows_out,
            rows_quarantined=report.rows_quarantined,
            freshness_min=report.freshness_minutes,
            status="ok" if report.ok else "fail",
            error="; ".join(report.schema_errors) if report.schema_errors else None,
        )

    # --- Helpers ---
    def _stamp_provenance(self, df: pd.DataFrame, fr: FetchResult) -> pd.DataFrame:
        df = df.copy()
        df["_source"] = self.SOURCE
        df["_request_id"] = fr.request_id
        df["_fetched_at_utc"] = pd.Timestamp(fr.fetched_at_utc).tz_convert("UTC")
        df["_payload_sha256"] = fr.payload_sha256
        return df
