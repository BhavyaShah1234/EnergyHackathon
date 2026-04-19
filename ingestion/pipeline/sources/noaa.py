"""NOAA NWS api.weather.gov — hourly gridpoint forecast + station observations.

Gridpoint PSR/158,56 covers Phoenix metro. api.weather.gov requires a descriptive
User-Agent per their terms of service — set NOAA_USER_AGENT in .env.
"""
from __future__ import annotations

import json
from typing import Iterable

import pandas as pd

from ..base import BaseIngestor
from ..http_client import FetchResult
from ..quality.schemas import NOAA_FORECAST_SCHEMA, NOAA_OBS_SCHEMA


class NOAAForecastIngestor(BaseIngestor):
    SOURCE = "noaa_phoenix"
    DATASET = "noaa_forecast"
    PARTITION_COL = "start_time_utc"
    SCHEMA = NOAA_FORECAST_SCHEMA
    GRID_ID = "PSR/158,56"

    def fetch(self) -> Iterable[FetchResult]:
        yield self.http.fetch(self.SOURCE, self.spec.endpoint)

    def parse(self, fr: FetchResult) -> pd.DataFrame:
        payload = json.loads(fr.body)
        periods = payload.get("properties", {}).get("periods", [])
        if not periods:
            return pd.DataFrame()
        df = pd.DataFrame(periods)
        df["start_time_utc"] = pd.to_datetime(df["startTime"], utc=True)
        df["end_time_utc"] = pd.to_datetime(df["endTime"], utc=True)
        df["grid_id"] = self.GRID_ID
        df["temperature_f"] = pd.to_numeric(df["temperature"], errors="coerce")
        # windSpeed is a string like "15 mph" — pull the number.
        df["wind_speed_mph"] = (
            df["windSpeed"].astype(str).str.extract(r"(\d+\.?\d*)")[0].astype(float)
        )
        df["probability_of_precipitation"] = df["probabilityOfPrecipitation"].apply(
            lambda v: v.get("value") if isinstance(v, dict) else v
        )
        df["probability_of_precipitation"] = pd.to_numeric(
            df["probability_of_precipitation"], errors="coerce"
        )
        df = df.rename(columns={"shortForecast": "short_forecast"})
        return df[[
            "start_time_utc", "end_time_utc", "grid_id",
            "temperature_f", "wind_speed_mph", "probability_of_precipitation", "short_forecast",
        ]]


class NOAAObservationIngestor(BaseIngestor):
    SOURCE = "noaa_phoenix_obs"
    DATASET = "noaa_obs"
    PARTITION_COL = "timestamp_utc"
    SCHEMA = NOAA_OBS_SCHEMA
    STATION = "KPHX"

    def fetch(self) -> Iterable[FetchResult]:
        yield self.http.fetch(self.SOURCE, self.spec.endpoint)

    def parse(self, fr: FetchResult) -> pd.DataFrame:
        payload = json.loads(fr.body)
        features = payload.get("features", [])
        if not features:
            return pd.DataFrame()
        rows = []
        for feat in features:
            p = feat.get("properties", {})
            rows.append({
                "timestamp_utc": p.get("timestamp"),
                "station": self.STATION,
                "temperature_c": _val(p.get("temperature")),
                "wind_speed_kph": _val(p.get("windSpeed")),
                "visibility_m": _val(p.get("visibility")),
                "text_description": p.get("textDescription"),
            })
        df = pd.DataFrame(rows)
        df["timestamp_utc"] = pd.to_datetime(df["timestamp_utc"], utc=True, errors="coerce")
        for col in ["temperature_c", "wind_speed_kph", "visibility_m"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna(subset=["timestamp_utc"])


def _val(obj):
    """NWS wraps numeric properties as {'value': x, 'unitCode': ...}. Unwrap."""
    if isinstance(obj, dict):
        return obj.get("value")
    return obj
