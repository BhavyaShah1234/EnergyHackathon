"""USGS FDSN Earthquake Catalog — historical seismic events.

Queries the USGS FDSN API for events matching the SW/ERCOT bbox and magnitude criteria.
Deduplicates by the unique event 'ids' property.

Endpoint:
  https://earthquake.usgs.gov/fdsnws/event/1/query
"""
from __future__ import annotations

import json
from typing import Iterable

import pandas as pd

from ..base import BaseIngestor
from ..http_client import FetchResult
from ..quality.schemas import SEISMIC_SCHEMA


class USGSSeismicIngestor(BaseIngestor):
    SOURCE = "usgs_seismic"
    DATASET = "usgs_seismic"
    PARTITION_COL = "timestamp_utc"
    SCHEMA = SEISMIC_SCHEMA

    def fetch(self) -> Iterable[FetchResult]:
        """Fetch all seismic events matching the config criteria."""
        params = self.spec.params or {}
        # Ensure we always get geojson
        params["format"] = "geojson"
        
        fr = self.http.fetch(self.SOURCE, self.spec.endpoint, params=params)
        yield fr

    def parse(self, fr: FetchResult) -> pd.DataFrame:
        payload = json.loads(fr.body)
        features = payload.get("features", [])
        if not features:
            return pd.DataFrame()

        rows = []
        for feat in features:
            props = feat.get("properties", {})
            geom = feat.get("geometry", {})
            coords = geom.get("coordinates", [None, None, None])
            
            # USGS time is ms since epoch
            ts_ms = props.get("time")
            ts_utc = (
                pd.to_datetime(ts_ms, unit="ms", utc=True)
                if ts_ms is not None
                else None
            )

            rows.append({
                "timestamp_utc": ts_utc,
                "mag": props.get("mag"),
                "place": props.get("place"),
                "lon": coords[0],
                "lat": coords[1],
                "depth": coords[2] if len(coords) > 2 else None,
                "ids": props.get("ids"),
                "url": props.get("url"),
                "geometry_geojson": json.dumps(geom) if geom else None,
            })
            
        return pd.DataFrame(rows)
