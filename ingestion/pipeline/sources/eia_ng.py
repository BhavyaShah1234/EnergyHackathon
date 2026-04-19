"""EIA Natural Gas daily spot prices — Henry Hub (national benchmark) and
Waha (West Texas, primary SW BTM fuel cost).

Both use EIA v2 API. Different series IDs live under different API paths;
we parameterize the path so one parser works for both.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

import pandas as pd

from ..base import BaseIngestor
from ..http_client import FetchResult
from ..quality.schemas import EIA_NG_SCHEMA


class _EIANGBase(BaseIngestor):
    DATASET = "eia_ng"
    PARTITION_COL = "period_utc"
    SCHEMA = EIA_NG_SCHEMA
    LOOKBACK_DAYS = 30

    def fetch(self) -> Iterable[FetchResult]:
        if not self.cfg.eia_api_key:
            raise RuntimeError("EIA_API_KEY not set in .env")
        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=self.LOOKBACK_DAYS)
        params = [
            ("api_key", self.cfg.eia_api_key),
            ("frequency", "daily"),
            ("data[0]", "value"),
            ("start", start.isoformat()),
            ("end", end.isoformat()),
            ("length", "5000"),
        ]
        for s in self.spec.facets.get("series", []):
            params.append(("facets[series][]", s))
        yield self.http.fetch(self.SOURCE, self.spec.endpoint, params=params)

    def parse(self, fr: FetchResult) -> pd.DataFrame:
        payload = json.loads(fr.body)
        rows = payload.get("response", {}).get("data", [])
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        df["period_utc"] = pd.to_datetime(df["period"], utc=True)
        df = df.rename(columns={"value": "price_usd_per_mmbtu"})
        df["price_usd_per_mmbtu"] = pd.to_numeric(df["price_usd_per_mmbtu"], errors="coerce")
        return df[["period_utc", "series", "price_usd_per_mmbtu"]]


class EIANGHenryHubIngestor(_EIANGBase):
    SOURCE = "eia_ng_henry_hub"


class EIANGWahaIngestor(_EIANGBase):
    SOURCE = "eia_ng_waha"
