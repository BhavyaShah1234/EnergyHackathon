"""Pull a small live sample from the hackathon-required sources that work
unauthenticated. No API keys needed.

Four sources, all referenced by the APS and Collide briefs:

  1. NOAA KPHX observations     — APS: "NOAA hourly observational access"
  2. NOAA Phoenix forecast      — APS: "NOAA hourly weather"
  3. ERCOT fuel mix             — Collide C: "ERCOT MIS ... fuel mix"
  4. CAISO Palo Verde LMP       — Collide C: "CAISO OASIS — WECC LMP Data"

EIA NG spot (Henry Hub + Waha) and EIA-930 also come from the briefs but need
EIA_API_KEY — set it in .env and use orchestrator.run_once instead.

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


def ercot_fuel_mix() -> pd.DataFrame:
    r = httpx.get(
        "https://www.ercot.com/api/1/services/read/dashboards/fuel-mix.json",
        headers=HEADERS, timeout=30,
    )
    r.raise_for_status()
    _save_raw("ercot_fuel_mix", r.content)
    payload = r.json()
    # payload['data'] is an object keyed by date → list of 5-min samples; pull latest.
    data = payload.get("data", {})
    if not data:
        return pd.DataFrame()
    latest_date = sorted(data.keys())[-1]
    samples = data[latest_date]
    if isinstance(samples, dict):
        samples = list(samples.values())
    if not samples:
        return pd.DataFrame()
    last = samples[-1] if isinstance(samples[-1], dict) else samples[-1]
    # Each sample has fuel-type → MW. Flatten the last one.
    rows = []
    ts = last.get("timestamp", latest_date)
    for fuel in payload.get("types", []):
        val = last.get(fuel) or last.get(fuel.replace(" ", "_"))
        # ERCOT wraps each fuel's value as {"gen": <MW>, ...}. Flatten defensively.
        if isinstance(val, dict):
            val = val.get("gen") if val.get("gen") is not None else val.get("value")
        if val is None:
            continue
        rows.append({
            "source": "ercot_fuel_mix",
            "timestamp": ts,
            "fuel": fuel,
            "mw": float(val),
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
        ("ercot_fuel_mix", ercot_fuel_mix),
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
