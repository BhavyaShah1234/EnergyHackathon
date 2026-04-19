"""BLM Surface Management Agency — land ownership for AZ, NM, TX federal lands.

Queries the BLM National SMA MapServer via ArcGIS REST.  Each run pulls the
full AZ+NM+TX extent (these are static polygons, not time-series).  Pagination
handles the 2 000 record-per-request limit.

Endpoint:
  https://gis.blm.gov/arcgis/rest/services/lands/BLM_Natl_SMA_Cached_without_Outline/MapServer/0/query
  &where=ADMIN_ST IN ('AZ','NM','TX') &f=geojson &outFields=*
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from ..base import BaseIngestor
from ..http_client import FetchResult
from ..quality.schemas import BLM_SMA_SCHEMA

# AZ + NM + W-TX envelope (xmin, ymin, xmax, ymax) in WGS84
_STATES = ["AZ", "NM", "TX"]
_PAGE_SIZE = 2000


class BLMSMAIngestor(BaseIngestor):
    SOURCE = "blm_sma"
    DATASET = "blm_sma"
    PARTITION_COL = "_fetched_at_utc"  # static data — partition by ingest time
    SCHEMA = BLM_SMA_SCHEMA

    def fetch(self) -> Iterable[FetchResult]:
        """Paginate through ArcGIS REST query results for target states."""
        offset = 0
        while True:
            params = {
                "where": f"ADMIN_ST IN ({','.join(repr(s) for s in _STATES)})",
                "outFields": "OBJECTID,SMA_CODE,ADMIN_AGENCY_CODE,ADMIN_ST,ADMO_NAME,GIS_ACRES,SHAPE_Area",
                "f": "geojson",
                "resultRecordCount": str(_PAGE_SIZE),
                "resultOffset": str(offset),
                "returnGeometry": "true",
                "outSR": "4326",
            }
            fr = self.http.fetch(self.SOURCE, self.spec.endpoint, params=params)
            yield fr
            # Check if we got a full page; if not, we're done.
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
            props = feat.get("properties", {})
            geom = feat.get("geometry")
            rows.append({
                "object_id": props.get("OBJECTID"),
                "sma_code": props.get("SMA_CODE"),
                "admin_agency": props.get("ADMIN_AGENCY_CODE"),
                "admin_state": props.get("ADMIN_ST"),
                "admin_name": props.get("ADMO_NAME"),
                "acreage": props.get("GIS_ACRES"),
                "shape_area_sq_deg": props.get("SHAPE_Area"),
                "geometry_geojson": json.dumps(geom) if geom else None,
            })
        df = pd.DataFrame(rows)
        df["acreage"] = pd.to_numeric(df["acreage"], errors="coerce")
        df["shape_area_sq_deg"] = pd.to_numeric(df["shape_area_sq_deg"], errors="coerce")
        return df
