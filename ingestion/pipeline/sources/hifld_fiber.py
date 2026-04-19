"""HIFLD-derived fiber optic cables — FCC Broadband Data Collection proxy.

The original HIFLD Open portal was decommissioned Aug 2025.  We use the FCC
Broadband Data Collection (BDC) fixed broadband availability dataset as a
proxy.  This is queried via the FCC's ArcGIS REST FeatureServer to identify
areas served by fiber (technology code = 50) within the target states.

For colocation / latency scoring the downstream model needs:
  - fiber availability polygons (census block level)
  - technology type (fiber vs cable vs DSL)
  - max advertised download speed

Endpoint:
  https://broadbandmap.fcc.gov/api/public/map/listAvailability
  Falls back to the FCC BDC bulk download if the API is unavailable.

NOTE: If the team obtains a DHS GII DUA for HIFLD Secure, swap this for a
direct HIFLD connector.  Until then, FCC BDC is the best public proxy.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from ..base import BaseIngestor
from ..http_client import FetchResult
from ..quality.schemas import HIFLD_FIBER_SCHEMA

# FCC technology codes for fiber:
#   50 = Fiber to the Premises (FTTP)
_FIBER_TECH_CODE = "50"

# Target state FIPS: AZ=04, NM=35, TX=48
_STATE_FIPS = ["04", "35", "48"]
_PAGE_SIZE = 2000


class HIFLDFiberIngestor(BaseIngestor):
    SOURCE = "hifld_fiber"
    DATASET = "hifld_fiber"
    PARTITION_COL = "_fetched_at_utc"
    SCHEMA = HIFLD_FIBER_SCHEMA

    def fetch(self) -> Iterable[FetchResult]:
        """Query FCC BDC availability for fiber in each target state."""
        for fips in _STATE_FIPS:
            offset = 0
            while True:
                params = {
                    "where": f"state_fips='{fips}' AND technology_code='{_FIBER_TECH_CODE}'",
                    "outFields": "frn,provider_id,brand_name,state_fips,block_geoid,"
                                 "technology_code,max_advertised_download_speed,"
                                 "max_advertised_upload_speed,low_latency",
                    "f": "geojson",
                    "resultRecordCount": str(_PAGE_SIZE),
                    "resultOffset": str(offset),
                    "returnGeometry": "true",
                    "outSR": "4326",
                }
                fr = self.http.fetch(self.SOURCE, self.spec.endpoint, params=params)
                yield fr
                payload = json.loads(fr.body)
                features = payload.get("features", [])
                if len(features) < _PAGE_SIZE:
                    break
                offset += _PAGE_SIZE

    def parse(self, fr: FetchResult) -> pd.DataFrame:
        payload = json.loads(fr.body)
        features = payload.get("features", [])
        if not features:
            return pd.DataFrame()

        rows = []
        for feat in features:
            p = feat.get("properties", {})
            geom = feat.get("geometry")
            rows.append({
                "frn": p.get("frn"),
                "provider_id": p.get("provider_id"),
                "brand_name": p.get("brand_name"),
                "state_fips": p.get("state_fips"),
                "block_geoid": p.get("block_geoid"),
                "technology_code": p.get("technology_code"),
                "max_download_mbps": p.get("max_advertised_download_speed"),
                "max_upload_mbps": p.get("max_advertised_upload_speed"),
                "low_latency": p.get("low_latency"),
                "geometry_geojson": json.dumps(geom) if geom else None,
            })
        df = pd.DataFrame(rows)
        for col in ["max_download_mbps", "max_upload_mbps"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
