"""EIA-930 hourly Balancing Authority data via EIA v2 API.

Docs: https://www.eia.gov/opendata/browser/electricity/rto/region-data
One ingestor per BA so run failures are isolated and the DQ report shows
per-BA freshness — critical when e.g. AZPS is live but CAISO is lagging.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

import pandas as pd

from ..base import BaseIngestor
from ..http_client import FetchResult
from ..quality.schemas import EIA930_SCHEMA


class _EIA930Base(BaseIngestor):
    DATASET = "eia930"
    PARTITION_COL = "period_utc"
    SCHEMA = EIA930_SCHEMA
    RESPONDENT: str = ""  # overridden by subclasses

    # Look back 72h every run; idempotent merge handles overlap.
    LOOKBACK_HOURS = 72

    def fetch(self) -> Iterable[FetchResult]:
        if not self.cfg.eia_api_key:
            raise RuntimeError("EIA_API_KEY not set in .env")
        end = datetime.now(timezone.utc)
        start = end - timedelta(hours=self.LOOKBACK_HOURS)
        params = [
            ("api_key", self.cfg.eia_api_key),
            ("frequency", "hourly"),
            ("data[0]", "value"),
            ("facets[respondent][]", self.RESPONDENT),
            ("start", start.strftime("%Y-%m-%dT%H")),
            ("end", end.strftime("%Y-%m-%dT%H")),
            ("sort[0][column]", "period"),
            ("sort[0][direction]", "desc"),
            ("length", "5000"),
        ]
        # Multiple type facets — EIA accepts repeated keys.
        for t in self.spec.facets.get("type", []):
            params.append(("facets[type][]", t))

        yield self.http.fetch(self.SOURCE, self.spec.endpoint, params=params)

    def parse(self, fr: FetchResult) -> pd.DataFrame:
        payload = json.loads(fr.body)
        rows = payload.get("response", {}).get("data", [])
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        # EIA periods look like "2026-04-18T15" — hour-precision UTC.
        df["period_utc"] = pd.to_datetime(df["period"], utc=True, format="%Y-%m-%dT%H")
        df = df.rename(columns={"value": "value_mw"})
        df["value_mw"] = pd.to_numeric(df["value_mw"], errors="coerce")
        return df[["period_utc", "respondent", "type", "value_mw"]]


class EIA930AZPSIngestor(_EIA930Base):
    SOURCE = "eia930_azps"
    RESPONDENT = "AZPS"


class EIA930CISOIngestor(_EIA930Base):
    SOURCE = "eia930_ciso"
    RESPONDENT = "CISO"


class EIA930ERCOIngestor(_EIA930Base):
    SOURCE = "eia930_erco"
    RESPONDENT = "ERCO"
