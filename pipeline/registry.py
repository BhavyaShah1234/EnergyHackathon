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
    # ERCOT MIS (Collide sub-problem C) — requires a developer token from
    # mis.ercot.com. Add a connector + registry entry once the token is in .env.
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
