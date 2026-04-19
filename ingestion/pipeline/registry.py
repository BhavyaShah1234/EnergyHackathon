"""Dataset catalog — what exists, who owns it, how to join.

Import ingestor classes lazily so `python -m pipeline.registry` works even before
a source is fully implemented.
"""
from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import Type

from .base import BaseIngestor


@dataclass
class DatasetEntry:
    source: str
    dataset: str
    module: str
    class_name: str
    join_keys: list[str]
    description: str

    def load(self) -> Type[BaseIngestor]:
        return getattr(import_module(self.module), self.class_name)


REGISTRY: dict[str, DatasetEntry] = {
    "eia930_azps": DatasetEntry(
        source="eia930_azps", dataset="eia930",
        module="pipeline.sources.eia930", class_name="EIA930AZPSIngestor",
        join_keys=["period_utc", "respondent"],
        description="APS (AZPS) hourly demand/forecast/netgen/interchange",
    ),
    "eia930_ciso": DatasetEntry(
        source="eia930_ciso", dataset="eia930",
        module="pipeline.sources.eia930", class_name="EIA930CISOIngestor",
        join_keys=["period_utc", "respondent"],
        description="CAISO hourly grid monitor",
    ),
    "eia930_erco": DatasetEntry(
        source="eia930_erco", dataset="eia930",
        module="pipeline.sources.eia930", class_name="EIA930ERCOIngestor",
        join_keys=["period_utc", "respondent"],
        description="ERCOT hourly grid monitor",
    ),
    "eia_ng_henry_hub": DatasetEntry(
        source="eia_ng_henry_hub", dataset="eia_ng",
        module="pipeline.sources.eia_ng", class_name="EIANGHenryHubIngestor",
        join_keys=["period_utc", "series"],
        description="Henry Hub daily spot gas price",
    ),
    "eia_ng_waha": DatasetEntry(
        source="eia_ng_waha", dataset="eia_ng",
        module="pipeline.sources.eia_ng", class_name="EIANGWahaIngestor",
        join_keys=["period_utc", "series"],
        description="Waha Hub daily spot gas price (SW fuel cost)",
    ),
    "caiso_lmp": DatasetEntry(
        source="caiso_lmp", dataset="caiso_lmp",
        module="pipeline.sources.caiso", class_name="CAISOLMPIngestor",
        join_keys=["interval_start_utc", "node"],
        description="CAISO OASIS 5-min LMP at Palo Verde + SP15 + NP15 hubs",
    ),
    "noaa_phoenix": DatasetEntry(
        source="noaa_phoenix", dataset="noaa_forecast",
        module="pipeline.sources.noaa", class_name="NOAAForecastIngestor",
        join_keys=["start_time_utc"],
        description="Phoenix gridpoint hourly forecast (temp/wind/precip)",
    ),
    "noaa_phoenix_obs": DatasetEntry(
        source="noaa_phoenix_obs", dataset="noaa_obs",
        module="pipeline.sources.noaa", class_name="NOAAObservationIngestor",
        join_keys=["timestamp_utc"],
        description="KPHX observations (ground truth temp/visibility/wind)",
    ),
    # --- Geospatial / static datasets (Collide sub-A: siting) ---
    "blm_sma": DatasetEntry(
        source="blm_sma", dataset="blm_sma",
        module="pipeline.sources.blm_glo", class_name="BLMSMAIngestor",
        join_keys=["object_id"],
        description="BLM Surface Management Agency — federal/state land ownership (AZ/NM/TX)",
    ),
    "hifld_fiber": DatasetEntry(
        source="hifld_fiber", dataset="hifld_fiber",
        module="pipeline.sources.hifld_fiber", class_name="HIFLDFiberIngestor",
        join_keys=["block_geoid", "provider_id"],
        description="FTTP fiber availability at census-block level via FCC BDC (AZ/NM/TX)",
    ),
    "nhd_waterbody": DatasetEntry(
        source="nhd_waterbody", dataset="nhd_waterbody",
        module="pipeline.sources.epa_nhd", class_name="NHDWaterbodyIngestor",
        join_keys=["object_id"],
        description="USGS NHD waterbody polygons — cooling water proximity (AZ/NM/TX)",
    ),
    "fema_floodplain": DatasetEntry(
        source="fema_floodplain", dataset="fema_floodplain",
        module="pipeline.sources.epa_nhd", class_name="FEMAFloodplainIngestor",
        join_keys=["object_id"],
        description="FEMA NFHL flood hazard zones — 100yr/500yr floodplain (AZ/NM/TX)",
    ),
    # --- Natural gas infrastructure (Collide sub-B: gas supply reliability) ---
    "pipelines_infra": DatasetEntry(
        source="pipelines_infra", dataset="pipelines_infra",
        module="pipeline.sources.pipelines_infra", class_name="PipelineInfraIngestor",
        join_keys=["pipeline_id"],
        description="NG pipeline routes (spatial + type + operator) — EIA ArcGIS, WECC-SW + ERCOT bbox",
    ),
}


def all_sources() -> list[str]:
    return list(REGISTRY.keys())


if __name__ == "__main__":
    from rich.console import Console
    from rich.table import Table

    table = Table(title="Dataset Registry")
    for col in ["source", "dataset", "join_keys", "description"]:
        table.add_column(col)
    for entry in REGISTRY.values():
        table.add_row(entry.source, entry.dataset, ",".join(entry.join_keys), entry.description)
    Console().print(table)
