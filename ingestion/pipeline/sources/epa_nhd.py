"""EPA/USGS NHD water bodies + FEMA NFHL floodplain zones for cooling water
availability and environmental risk screening.

Two sub-ingestors:
  1. NHDWaterbodyIngestor — queries USGS NHD MapServer Layer 10 (Waterbody -
     Small Scale) for lakes/reservoirs in AZ/NM/TX.
  2. FEMAFloodplainIngestor — queries FEMA NFHL MapServer Layer 28 (Flood
     Hazard Zones) for 100-year floodplain extents in AZ/NM/TX.

Endpoints:
  NHD:  https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer/10/query
  NFHL: https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/28/query
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterable

import pandas as pd

from ..base import BaseIngestor
from ..http_client import FetchResult
from ..quality.schemas import NHD_WATERBODY_SCHEMA, FEMA_FLOODPLAIN_SCHEMA

_PAGE_SIZE = 2000

# Bounding boxes for AZ + NM + TX (WGS84: xmin, ymin, xmax, ymax)
_SW_BBOX = {
    "AZ": "-114.82,31.33,-109.04,37.00",
    "NM": "-109.05,31.33,-103.00,37.00",
    "TX": "-106.65,25.84,-93.51,36.50",
}


class NHDWaterbodyIngestor(BaseIngestor):
    """USGS NHD Waterbody polygons (lakes, reservoirs, ponds) in target states."""
    SOURCE = "nhd_waterbody"
    DATASET = "nhd_waterbody"
    PARTITION_COL = "_fetched_at_utc"
    SCHEMA = NHD_WATERBODY_SCHEMA

    def fetch(self) -> Iterable[FetchResult]:
        for state, bbox in _SW_BBOX.items():
            offset = 0
            while True:
                params = {
                    "where": "1=1",
                    "geometry": bbox,
                    "geometryType": "esriGeometryEnvelope",
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "OBJECTID,GNIS_NAME,FTYPE,FCODE,AREASQKM,REACHCODE",
                    "f": "geojson",
                    "resultRecordCount": str(_PAGE_SIZE),
                    "resultOffset": str(offset),
                    "returnGeometry": "true",
                    "inSR": "4326",
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
                "object_id": p.get("OBJECTID"),
                "gnis_name": p.get("GNIS_NAME"),
                "feature_type": p.get("FTYPE"),
                "feature_code": p.get("FCODE"),
                "area_sq_km": p.get("AREASQKM"),
                "reach_code": p.get("REACHCODE"),
                "geometry_geojson": json.dumps(geom) if geom else None,
            })
        df = pd.DataFrame(rows)
        df["area_sq_km"] = pd.to_numeric(df["area_sq_km"], errors="coerce")
        return df


class FEMAFloodplainIngestor(BaseIngestor):
    """FEMA NFHL Flood Hazard Zones — 100-year and 500-year floodplain extents."""
    SOURCE = "fema_floodplain"
    DATASET = "fema_floodplain"
    PARTITION_COL = "_fetched_at_utc"
    SCHEMA = FEMA_FLOODPLAIN_SCHEMA

    def fetch(self) -> Iterable[FetchResult]:
        for state, bbox in _SW_BBOX.items():
            offset = 0
            while True:
                params = {
                    "where": "1=1",
                    "geometry": bbox,
                    "geometryType": "esriGeometryEnvelope",
                    "spatialRel": "esriSpatialRelIntersects",
                    "outFields": "OBJECTID,FLD_AR_ID,FLD_ZONE,ZONE_SUBTY,SFHA_TF,STATIC_BFE,DEPTH",
                    "f": "geojson",
                    "resultRecordCount": str(_PAGE_SIZE),
                    "resultOffset": str(offset),
                    "returnGeometry": "true",
                    "inSR": "4326",
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
                "object_id": p.get("OBJECTID"),
                "flood_area_id": p.get("FLD_AR_ID"),
                "flood_zone": p.get("FLD_ZONE"),
                "zone_subtype": p.get("ZONE_SUBTY"),
                "sfha_flag": p.get("SFHA_TF"),
                "static_bfe_ft": p.get("STATIC_BFE"),
                "depth_ft": p.get("DEPTH"),
                "geometry_geojson": json.dumps(geom) if geom else None,
            })
        df = pd.DataFrame(rows)
        for col in ["static_bfe_ft", "depth_ft"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df
