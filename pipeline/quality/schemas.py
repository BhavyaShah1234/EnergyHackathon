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


# --- Geospatial / static datasets (Collide sub-A) ---

BLM_SMA_SCHEMA = pa.DataFrameSchema(
    {
        "object_id": pa.Column(float, nullable=True),
        "sma_code": pa.Column(str, nullable=True),
        "admin_agency": pa.Column(str, nullable=True),
        "admin_state": pa.Column(str, pa.Check.isin(["AZ", "NM", "TX"]), nullable=True),
        "admin_name": pa.Column(str, nullable=True),
        "acreage": pa.Column(float, pa.Check.ge(0), nullable=True),
        "shape_area_sq_deg": pa.Column(float, nullable=True),
        "geometry_geojson": pa.Column(str, nullable=True),
        **_PROVENANCE,
    },
    strict=True,
    coerce=True,
)


HIFLD_FIBER_SCHEMA = pa.DataFrameSchema(
    {
        "frn": pa.Column(str, nullable=True),
        "provider_id": pa.Column(str, nullable=True),
        "brand_name": pa.Column(str, nullable=True),
        "state_fips": pa.Column(str, pa.Check.isin(["04", "35", "48"]), nullable=True),
        "block_geoid": pa.Column(str, nullable=True),
        "technology_code": pa.Column(str, nullable=True),
        "max_download_mbps": pa.Column(float, pa.Check.ge(0), nullable=True),
        "max_upload_mbps": pa.Column(float, pa.Check.ge(0), nullable=True),
        "low_latency": pa.Column(str, nullable=True),
        "geometry_geojson": pa.Column(str, nullable=True),
        **_PROVENANCE,
    },
    strict=True,
    coerce=True,
)


NHD_WATERBODY_SCHEMA = pa.DataFrameSchema(
    {
        "object_id": pa.Column(float, nullable=True),
        "gnis_name": pa.Column(str, nullable=True),
        "feature_type": pa.Column(str, nullable=True),
        "feature_code": pa.Column(str, nullable=True),
        "area_sq_km": pa.Column(float, pa.Check.ge(0), nullable=True),
        "reach_code": pa.Column(str, nullable=True),
        "geometry_geojson": pa.Column(str, nullable=True),
        **_PROVENANCE,
    },
    strict=True,
    coerce=True,
)


FEMA_FLOODPLAIN_SCHEMA = pa.DataFrameSchema(
    {
        "object_id": pa.Column(float, nullable=True),
        "flood_area_id": pa.Column(str, nullable=True),
        "flood_zone": pa.Column(str, nullable=True),
        "zone_subtype": pa.Column(str, nullable=True),
        "sfha_flag": pa.Column(str, nullable=True),
        "static_bfe_ft": pa.Column(float, nullable=True),
        "depth_ft": pa.Column(float, nullable=True),
        "geometry_geojson": pa.Column(str, nullable=True),
        **_PROVENANCE,
    },
    strict=True,
    coerce=True,
)


# --- Natural gas infrastructure (Collide sub-B: gas supply reliability) ---

PIPELINE_INFRA_SCHEMA = pa.DataFrameSchema(
    {
        "pipeline_id": pa.Column(int, nullable=False),
        "pipe_type": pa.Column(str, pa.Check.isin(["Interstate", "Intrastate"])),
        "operator": pa.Column(str, nullable=True),
        "status": pa.Column(str, nullable=True),
        # North America envelope — catches flipped lat/lon or bad geometry, but
        # lets segments that cross the query bbox through (they legitimately extend
        # slightly outside when spatialRel=Intersects matches a boundary-crossing line).
        "start_lon": pa.Column(float, pa.Check.in_range(-170.0, -50.0)),
        "start_lat": pa.Column(float, pa.Check.in_range(15.0, 72.0)),
        "end_lon": pa.Column(float, pa.Check.in_range(-170.0, -50.0)),
        "end_lat": pa.Column(float, pa.Check.in_range(15.0, 72.0)),
        "midpoint_lon": pa.Column(float, pa.Check.in_range(-170.0, -50.0)),
        "midpoint_lat": pa.Column(float, pa.Check.in_range(15.0, 72.0)),
        "length_km": pa.Column(float, pa.Check.in_range(0.0, 5000.0)),
        "num_vertices": pa.Column(int, pa.Check.ge(2)),
        "geometry_wkt": pa.Column(str, nullable=False),
        **_PROVENANCE,
    },
    strict=True,
    coerce=True,
)


SEISMIC_SCHEMA = pa.DataFrameSchema(
    {
        "timestamp_utc": pa.Column("datetime64[ns, UTC]", nullable=False),
        "mag": pa.Column(float, pa.Check.in_range(-2, 10), nullable=True),
        "place": pa.Column(str, nullable=True),
        "lat": pa.Column(float, pa.Check.in_range(-90, 90)),
        "lon": pa.Column(float, pa.Check.in_range(-180, 180)),
        "depth": pa.Column(float, nullable=True),
        "ids": pa.Column(str, nullable=False),
        "url": pa.Column(str, nullable=True),
        "geometry_geojson": pa.Column(str, nullable=True),
        **_PROVENANCE,
    },
    strict=True,
    coerce=True,
)


FEMA_NRI_WILDFIRE_SCHEMA = pa.DataFrameSchema(
    {
        "object_id": pa.Column(float, nullable=False),
        "tract_fips": pa.Column(str, nullable=True),
        "state": pa.Column(str, nullable=True),
        "wildfire_risk_score": pa.Column(float, nullable=True),
        "wildfire_risk_rating": pa.Column(str, nullable=True),
        "population": pa.Column(float, nullable=True),
        "geometry_geojson": pa.Column(str, nullable=True),
        **_PROVENANCE,
    },
    strict=True,
    coerce=True,
)


SEISMIC_SCHEMA = pa.DataFrameSchema(
    {
        "timestamp_utc": pa.Column("datetime64[ns, UTC]", nullable=False),
        "mag": pa.Column(float, pa.Check.in_range(-2, 10), nullable=True),
        "place": pa.Column(str, nullable=True),
        "lat": pa.Column(float, pa.Check.in_range(-90, 90)),
        "lon": pa.Column(float, pa.Check.in_range(-180, 180)),
        "depth": pa.Column(float, nullable=True),
        "ids": pa.Column(str, nullable=False),
        "url": pa.Column(str, nullable=True),
        "geometry_geojson": pa.Column(str, nullable=True),
        **_PROVENANCE,
    },
    strict=True,
    coerce=True,
)


WILDFIRE_SCHEMA = pa.DataFrameSchema(
    {
        "object_id": pa.Column(float, nullable=False),
        "whp_class": pa.Column(int, pa.Check.in_range(1, 5), nullable=True),
        "whp_class_name": pa.Column(
            str,
            pa.Check.isin(["Very Low", "Low", "Moderate", "High", "Very High"]),
            nullable=True,
        ),
        "geometry_geojson": pa.Column(str, nullable=True),
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
    "blm_sma": BLM_SMA_SCHEMA,
    "hifld_fiber": HIFLD_FIBER_SCHEMA,
    "nhd_waterbody": NHD_WATERBODY_SCHEMA,
    "fema_floodplain": FEMA_FLOODPLAIN_SCHEMA,
    "pipelines_infra": PIPELINE_INFRA_SCHEMA,
    "usgs_seismic": SEISMIC_SCHEMA,
    "fema_nri_wildfire": FEMA_NRI_WILDFIRE_SCHEMA,
}
