"""FEMA National Risk Index (NRI) — Wildfire Risk at Census Tract level.

Queries the FEMA NRI FeatureServer for Arizona, New Mexico, and Texas.
Extracts Wildfire Risk Scores (WFIR_RISKS) and Ratings (WFIR_RISKR).

Endpoint:
  https://services.arcgis.com/XG15cJAlne2vxtgt/arcgis/rest/services/National_Risk_Index_Census_Tracts/FeatureServer/0/query
"""
from __future__ import annotations

import json
from typing import Iterable

import pandas as pd

from ..base import BaseIngestor
from ..http_client import FetchResult
from ..quality.schemas import FEMA_NRI_WILDFIRE_SCHEMA


class FEMANRIWildfireIngestor(BaseIngestor):
    SOURCE = "fema_nri_wildfire"
    DATASET = "fema_nri_wildfire"
    PARTITION_COL = "_fetched_at_utc"
    SCHEMA = FEMA_NRI_WILDFIRE_SCHEMA

    PAGE_SIZE = 2000

    def fetch(self) -> Iterable[FetchResult]:
        """Paginate through FEMA NRI results for target states."""
        offset = 0
        while True:
            params = {
                "where": "STATE IN ('Arizona','New Mexico','Texas')",
                "outFields": "OBJECTID,TRACTFIPS,STATE,POPULATION,WFIR_RISKS,WFIR_RISKR",
                "f": "json",
                "returnGeometry": "true",
                "outSR": "4326",
                "resultOffset": str(offset),
                "resultRecordCount": str(self.PAGE_SIZE),
            }
            fr = self.http.fetch(self.SOURCE, self.spec.endpoint, params=params)
            yield fr
            
            payload = json.loads(fr.body)
            if not payload.get("exceededTransferLimit"):
                break
            offset += self.PAGE_SIZE

    def parse(self, fr: FetchResult) -> pd.DataFrame:
        payload = json.loads(fr.body)
        features = payload.get("features", [])
        if not features:
            return pd.DataFrame()

        rows = []
        for feat in features:
            attrs = feat.get("attributes", {})
            geom = feat.get("geometry", {})
            
            rows.append({
                "object_id": attrs.get("OBJECTID"),
                "tract_fips": attrs.get("TRACTFIPS"),
                "state": attrs.get("STATE"),
                "population": attrs.get("POPULATION"),
                "wildfire_risk_score": attrs.get("WFIR_RISKS"),
                "wildfire_risk_rating": attrs.get("WFIR_RISKR"),
                "geometry_geojson": json.dumps(geom) if geom else None,
            })
            
        return pd.DataFrame(rows)
