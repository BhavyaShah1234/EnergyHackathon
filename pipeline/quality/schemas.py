"""Pandera schemas — one per silver dataset.

These are the contract between the pipeline and every downstream consumer.
If you change a schema, bump its version and add a migration note in the PR.
"""
from __future__ import annotations

import pandera as pa
from pandera.typing import Series

# Provenance columns injected by BaseIngestor — every schema inherits them.
_PROVENANCE = {
    "_source": pa.Column(str, nullable=False),
    "_request_id": pa.Column(str, nullable=False),
    "_fetched_at_utc": pa.Column("datetime64[ns, UTC]", nullable=False),
    "_payload_sha256": pa.Column(str, nullable=False),
}


EIA930_SCHEMA = pa.DataFrameSchema(
    {
        "period_utc": pa.Column("datetime64[ns, UTC]", nullable=False),
        "respondent": pa.Column(str, pa.Check.isin(["AZPS", "CISO", "ERCO", "WALC", "SRP", "PNM"])),
        "type": pa.Column(str, pa.Check.isin(["D", "DF", "NG", "TI"])),
        "value_mw": pa.Column(float, pa.Check.in_range(-200_000, 400_000), nullable=True),
        **_PROVENANCE,
    },
    # Uniqueness is enforced by pipeline.quality.checks.validate (post-dedup) so
    # upstream backfills/overlaps don't spuriously fail the schema.
    strict=True,
    coerce=True,
)


EIA_NG_SCHEMA = pa.DataFrameSchema(
    {
        "period_utc": pa.Column("datetime64[ns, UTC]", nullable=False),
        "series": pa.Column(str, nullable=False),
        "price_usd_per_mmbtu": pa.Column(float, pa.Check.in_range(0, 100), nullable=True),
        **_PROVENANCE,
    },
    strict=True,
    coerce=True,
)


CAISO_LMP_SCHEMA = pa.DataFrameSchema(
    {
        "interval_start_utc": pa.Column("datetime64[ns, UTC]", nullable=False),
        "interval_end_utc": pa.Column("datetime64[ns, UTC]", nullable=False),
        "node": pa.Column(str, nullable=False),
        "lmp_component": pa.Column(str, pa.Check.isin(["LMP", "MCE", "MCC", "MCL"])),
        "price_usd_per_mwh": pa.Column(float, pa.Check.in_range(-2000, 20000), nullable=True),
        **_PROVENANCE,
    },
    strict=True,
    coerce=True,
)


ERCOT_LMP_SCHEMA = pa.DataFrameSchema(
    {
        "interval_start_utc": pa.Column("datetime64[ns, UTC]", nullable=False),
        "settlement_point": pa.Column(str, nullable=False),
        "price_usd_per_mwh": pa.Column(float, pa.Check.in_range(-2000, 20000), nullable=True),
        **_PROVENANCE,
    },
    strict=True,
    coerce=True,
)


NOAA_FORECAST_SCHEMA = pa.DataFrameSchema(
    {
        "start_time_utc": pa.Column("datetime64[ns, UTC]", nullable=False),
        "end_time_utc": pa.Column("datetime64[ns, UTC]", nullable=False),
        "grid_id": pa.Column(str, nullable=False),
        "temperature_f": pa.Column(float, pa.Check.in_range(-60, 140), nullable=True),
        "wind_speed_mph": pa.Column(float, pa.Check.in_range(0, 200), nullable=True),
        "probability_of_precipitation": pa.Column(float, pa.Check.in_range(0, 100), nullable=True),
        "short_forecast": pa.Column(str, nullable=True),
        **_PROVENANCE,
    },
    strict=True,
    coerce=True,
)


NOAA_OBS_SCHEMA = pa.DataFrameSchema(
    {
        "timestamp_utc": pa.Column("datetime64[ns, UTC]", nullable=False),
        "station": pa.Column(str, nullable=False),
        "temperature_c": pa.Column(float, pa.Check.in_range(-50, 60), nullable=True),
        "wind_speed_kph": pa.Column(float, pa.Check.in_range(0, 300), nullable=True),
        "visibility_m": pa.Column(float, pa.Check.in_range(0, 100_000), nullable=True),
        "text_description": pa.Column(str, nullable=True),
        **_PROVENANCE,
    },
    strict=True,
    coerce=True,
)


SCHEMAS = {
    "eia930": EIA930_SCHEMA,
    "eia_ng": EIA_NG_SCHEMA,
    "caiso_lmp": CAISO_LMP_SCHEMA,
    "ercot_lmp": ERCOT_LMP_SCHEMA,
    "noaa_forecast": NOAA_FORECAST_SCHEMA,
    "noaa_obs": NOAA_OBS_SCHEMA,
}
