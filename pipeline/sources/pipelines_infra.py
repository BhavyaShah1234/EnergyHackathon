"""Natural gas pipeline infrastructure — spatial routes, type, operator.

Source: EIA's public ArcGIS FeatureServer
  https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/
    Natural_Gas_Interstate_and_Intrastate_Pipelines_1/FeatureServer/0
32,892 polyline features nationally. Unauthenticated, WGS84 (EPSG:4326).

What downstream gets per segment:
  pipeline_id         stable OID from EIA (int)
  pipe_type           Interstate | Intrastate
  operator            pipeline operator name (e.g. "El Paso Natural Gas Co")
  status              Operating | Proposed | etc.
  start_lon/lat       first vertex of the polyline
  end_lon/lat         last vertex
  midpoint_lon/lat    unweighted centroid of all vertices
  length_km           haversine sum along the path (great-circle, meters-accurate)
  num_vertices        polyline vertex count
  geometry_wkt        "LINESTRING (lon lat, lon lat, ...)" — OGC standard

Intentional gap: install_year / pipe_material are NOT in the EIA public layer.
Collide sub-problem B expects vintage-driven failure modeling; source that from
PHMSA Annual Report (F-7100.1-1) once the phmsa.dot.gov bulk is reachable.
Join key downstream: operator+state (PHMSA reports are operator-level).

Scope: filtered to the Collide-relevant bbox (WECC SW + ERCOT) rather than all
of CONUS. ~8–12k segments expected; fits comfortably in one parquet partition.
"""
from __future__ import annotations

import json
import math
from typing import Iterable

import pandas as pd

from ..base import BaseIngestor
from ..http_client import FetchResult
from ..quality.schemas import PIPELINE_INFRA_SCHEMA


# WECC-SW + ERCOT bounding box (WGS84). Covers AZ/NM/CA/NV/UT/CO/TX — the
# Collide brief's geography. Expanding this means more features per page, so
# keep it tight enough that one page ≈ a real sub-region rather than all CONUS.
_BBOX = {
    "xmin": -125.0, "ymin": 25.0,
    "xmax":  -93.0, "ymax": 42.0,
}


class PipelineInfraIngestor(BaseIngestor):
    SOURCE = "pipelines_infra"
    DATASET = "pipelines_infra"
    # Static reference data — partition by fetch day so re-pulls overwrite cleanly.
    PARTITION_COL = "_fetched_at_utc"
    SCHEMA = PIPELINE_INFRA_SCHEMA

    PAGE_SIZE = 2000   # ArcGIS maxRecordCount for this service

    def fetch(self) -> Iterable[FetchResult]:
        offset = 0
        while True:
            params = {
                "where": "1=1",
                "outFields": "FID,TYPEPIPE,Operator,Status",
                "returnGeometry": "true",
                "outSR": "4326",
                "geometry": json.dumps(_BBOX),
                "geometryType": "esriGeometryEnvelope",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "resultOffset": str(offset),
                "resultRecordCount": str(self.PAGE_SIZE),
                "f": "json",
            }
            fr = self.http.fetch(self.SOURCE, self.spec.endpoint, params=params)
            yield fr
            # Peek at the body to decide if there's another page. ArcGIS sets
            # `exceededTransferLimit=true` when more features are available.
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
            paths = geom.get("paths") or []
            # A polyline can have multiple paths (multi-segment). Flatten — for
            # downstream siting we only need the full ordered vertex list per row.
            vertices: list[list[float]] = []
            for path in paths:
                vertices.extend(path)
            if not vertices:
                continue

            start = vertices[0]
            end = vertices[-1]
            midpoint_lon = sum(v[0] for v in vertices) / len(vertices)
            midpoint_lat = sum(v[1] for v in vertices) / len(vertices)
            length_km = _polyline_length_km(vertices)
            wkt = "LINESTRING (" + ", ".join(f"{v[0]} {v[1]}" for v in vertices) + ")"

            rows.append({
                "pipeline_id": int(attrs.get("FID")),
                "pipe_type": attrs.get("TYPEPIPE"),
                "operator": attrs.get("Operator"),
                "status": attrs.get("Status"),
                "start_lon": float(start[0]),
                "start_lat": float(start[1]),
                "end_lon": float(end[0]),
                "end_lat": float(end[1]),
                "midpoint_lon": float(midpoint_lon),
                "midpoint_lat": float(midpoint_lat),
                "length_km": float(length_km),
                "num_vertices": len(vertices),
                "geometry_wkt": wkt,
            })

        return pd.DataFrame(rows)


def _polyline_length_km(vertices: list[list[float]]) -> float:
    """Great-circle length along a polyline, WGS84. Good to ~0.5% over continental distances."""
    R = 6371.0088  # mean Earth radius, km
    total = 0.0
    for (lon1, lat1), (lon2, lat2) in zip(vertices[:-1], vertices[1:]):
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        total += 2 * R * math.asin(math.sqrt(a))
    return total
