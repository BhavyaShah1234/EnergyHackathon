"""CAISO OASIS 5-min LMP (PRC_INTVL_LMP).

The OASIS SingleZip endpoint returns a zip containing one CSV per node/query.
We pull once per run for the configured nodes — Palo Verde is the key node
for Arizona (Palo Verde ASR is the major AZ/CA interconnect) plus SP15/NP15
for California hub context.

OASIS is picky about query shape:
  queryname=PRC_INTVL_LMP, market_run_id=RTM, startdatetime=YYYYMMDDTHH:mm-0000
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Iterable

import pandas as pd

from ..base import BaseIngestor
from ..http_client import FetchResult
from ..quality.schemas import CAISO_LMP_SCHEMA


class CAISOLMPIngestor(BaseIngestor):
    SOURCE = "caiso_lmp"
    DATASET = "caiso_lmp"
    PARTITION_COL = "interval_start_utc"
    SCHEMA = CAISO_LMP_SCHEMA

    # Pull the last 2h of 5-min intervals each run. OASIS rate-limits hard, so
    # keep windows short and let idempotent merge handle re-pulls.
    LOOKBACK_HOURS = 2

    def fetch(self) -> Iterable[FetchResult]:
        end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        start = end - timedelta(hours=self.LOOKBACK_HOURS)
        nodes = self.spec.nodes or ["PALOVRDE_ASR-APND"]
        for node in nodes:
            params = {
                "queryname": "PRC_INTVL_LMP",
                "market_run_id": "RTM",
                "version": "1",
                "resultformat": "6",   # CSV
                "node": node,
                "startdatetime": start.strftime("%Y%m%dT%H:%M-0000"),
                "enddatetime": end.strftime("%Y%m%dT%H:%M-0000"),
            }
            yield self.http.fetch(self.SOURCE, self.spec.endpoint, params=params)

    def parse(self, fr: FetchResult) -> pd.DataFrame:
        # Response is a zip with one CSV inside.
        try:
            zf = zipfile.ZipFile(io.BytesIO(fr.body))
        except zipfile.BadZipFile:
            # OASIS sometimes returns an HTML error page with 200; treat as empty.
            return pd.DataFrame()

        frames = []
        for name in zf.namelist():
            if not name.endswith(".csv"):
                continue
            with zf.open(name) as fh:
                frames.append(pd.read_csv(fh))
        if not frames:
            return pd.DataFrame()

        df = pd.concat(frames, ignore_index=True)
        # CAISO columns vary by query; normalize defensively.
        col_map = {
            "INTERVALSTARTTIME_GMT": "interval_start_utc",
            "INTERVALENDTIME_GMT": "interval_end_utc",
            "NODE": "node",
            "LMP_TYPE": "lmp_component",
            "VALUE": "price_usd_per_mwh",
            "MW": "price_usd_per_mwh",   # some queries use MW for the price col name — EIA legacy
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        required = {"interval_start_utc", "interval_end_utc", "node", "lmp_component", "price_usd_per_mwh"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"CAISO response missing columns: {missing}")

        df["interval_start_utc"] = pd.to_datetime(df["interval_start_utc"], utc=True)
        df["interval_end_utc"] = pd.to_datetime(df["interval_end_utc"], utc=True)
        df["price_usd_per_mwh"] = pd.to_numeric(df["price_usd_per_mwh"], errors="coerce")
        return df[list(required)]
