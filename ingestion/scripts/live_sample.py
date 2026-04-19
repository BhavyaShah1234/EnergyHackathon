"""Pull a small live sample from the unauthenticated sources the pipeline
currently supports end-to-end.

Three sources:

  1. NOAA KPHX observations     — APS weather ground truth
  2. NOAA Phoenix forecast      — APS hourly weather forecast
  3. CAISO Palo Verde LMP       — Collide sub-C WECC market signal

ERCOT MIS is intentionally absent here because the production connector is not
wired until a developer token is available from mis.ercot.com.

Writes raw responses to data/_samples/ and a tidy CSV preview.
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "_samples"
OUT.mkdir(parents=True, exist_ok=True)

UA = "collide-energy-pipeline sdonthi4@asu.edu"
HEADERS = {"User-Agent": UA}
NOW = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _save_raw(name: str, body: bytes) -> Path:
    p = OUT / f"{name}_{NOW}.bin"
    p.write_bytes(body)
    return p


def noaa_obs() -> pd.DataFrame:
    r = httpx.get(
        "https://api.weather.gov/stations/KPHX/observations",
        headers=HEADERS, timeout=30,
    )
    r.raise_for_status()
    _save_raw("noaa_obs", r.content)
    rows = []
    for feat in r.json().get("features", [])[:5]:
        p = feat.get("properties", {})
        rows.append({
            "source": "noaa_obs",
            "timestamp_utc": p.get("timestamp"),
            "station": "KPHX",
            "temperature_c": _v(p.get("temperature")),
            "wind_speed_kph": _v(p.get("windSpeed")),
            "visibility_m": _v(p.get("visibility")),
            "text": (p.get("textDescription") or "")[:30],
        })
    return pd.DataFrame(rows)


def noaa_forecast() -> pd.DataFrame:
    r = httpx.get(
        "https://api.weather.gov/gridpoints/PSR/158,56/forecast/hourly",
        headers=HEADERS, timeout=30,
    )
    r.raise_for_status()
    _save_raw("noaa_forecast", r.content)
    rows = []
    for p in r.json().get("properties", {}).get("periods", [])[:6]:
        rows.append({
            "source": "noaa_forecast",
            "start_time_utc": p.get("startTime"),
            "grid_id": "PSR/158,56",
            "temperature_f": p.get("temperature"),
            "wind_speed": p.get("windSpeed"),
            "precip_pct": (p.get("probabilityOfPrecipitation") or {}).get("value"),
            "text": (p.get("shortForecast") or "")[:30],
        })
    return pd.DataFrame(rows)

def caiso_palo_verde_lmp() -> pd.DataFrame:
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    end = end.replace(minute=(end.minute // 5) * 5) - timedelta(minutes=15)
    start = end - timedelta(hours=1)
    params = {
        "queryname": "PRC_INTVL_LMP", "market_run_id": "RTM", "version": "1",
        "resultformat": "6", "node": "PALOVRDE_ASR-APND",
        "startdatetime": start.strftime("%Y%m%dT%H:%M-0000"),
        "enddatetime": end.strftime("%Y%m%dT%H:%M-0000"),
    }
    r = httpx.get("https://oasis.caiso.com/oasisapi/SingleZip",
                  params=params, headers=HEADERS, timeout=30)
    r.raise_for_status()
    _save_raw("caiso_palo_verde_lmp", r.content)
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    frames = []
    for name in zf.namelist():
        if name.endswith(".csv"):
            with zf.open(name) as fh:
                frames.append(pd.read_csv(fh))
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    # Keep total LMP only (filter the 3 sub-components out) and show last 5 intervals.
    df = df[df["LMP_TYPE"] == "LMP"].copy()
    df = df.rename(columns={
        "INTERVALSTARTTIME_GMT": "interval_start_utc",
        "NODE": "node",
        "MW": "price_usd_per_mwh",
    })
    df["source"] = "caiso_lmp"
    return df[["source", "interval_start_utc", "node", "price_usd_per_mwh"]].tail(6).reset_index(drop=True)


def _v(obj):
    return obj.get("value") if isinstance(obj, dict) else obj


def main() -> None:
    sources = [
        ("noaa_obs",       noaa_obs),
        ("noaa_forecast",  noaa_forecast),
        ("caiso_lmp",      caiso_palo_verde_lmp),
    ]
    frames = []
    for name, fn in sources:
        try:
            df = fn()
            print(f"\n=== {name} ({len(df)} rows) ===")
            print(df.to_string(index=False, max_colwidth=40))
            frames.append(df)
        except Exception as exc:
            print(f"\n=== {name} FAILED: {type(exc).__name__}: {str(exc)[:120]} ===")

    if frames:
        preview = OUT / "sample_preview.csv"
        # Union-safe concat across heterogeneous schemas — pandas broadcasts NaN.
        pd.concat(frames, ignore_index=True).to_csv(preview, index=False)
        print(f"\n[saved preview    → {preview}]")
        print(f"[raw responses   → {OUT}/*_{NOW}.bin]")


if __name__ == "__main__":
    main()
