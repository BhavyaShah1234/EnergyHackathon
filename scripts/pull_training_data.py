#!/usr/bin/env python3
"""Pull distribution-quality training data from ALL time-series sources.

Unlike pull_diverse_sample.py (95 sparse rows), this pulls **real volume**:
  - EIA-930: 3 BAs (AZPS, CISO, ERCO) × 4 types × 7 days = ~2000+ rows
  - EIA NG:  Henry Hub + Waha × 90 days = ~180 rows
  - CAISO:   3 nodes × 4 LMP components × 6 hours = ~800+ rows
  - NOAA:    156 forecast hours + 200+ recent observations

Total: ~3000–4000 rows across 5 independent source APIs.

Every row gets:
  - Source provenance (_source tag)
  - UTC-normalized timestamps
  - Schema validation (value range checks)
  - Null-rate and distribution stats

Output:
  data/training/             ← per-source parquet files (downstream-ready)
  data/training/quality_report.json  ← distribution stats & DQ summary

Usage:
  python scripts/pull_training_data.py              # all sources
  python scripts/pull_training_data.py --only eia    # just EIA sources
"""
from __future__ import annotations

import csv
import io
import json
import os
import statistics
import sys
import time
import zipfile
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
TRAINING_DIR = ROOT / "data" / "training"
TRAINING_DIR.mkdir(parents=True, exist_ok=True)

EIA_KEY = os.environ.get("EIA_API_KEY", "")
NOAA_UA = os.environ.get("NOAA_USER_AGENT", "collide-energy-pipeline sdonthi4@asu.edu")

NOW = datetime.now(timezone.utc)
TS_TAG = NOW.strftime("%Y%m%dT%H%M%SZ")

# Schema range checks per source (col → (min, max))
RANGE_CHECKS = {
    "eia930": {"value_mw": (-200_000, 400_000)},
    "eia_ng": {"price_usd_per_mmbtu": (0, 100)},
    "caiso_lmp": {"price_usd_per_mwh": (-2000, 20000)},
    "noaa_forecast": {"temperature_f": (-60, 140), "probability_of_precipitation": (0, 100)},
    "noaa_obs": {"temperature_c": (-50, 60), "visibility_m": (0, 100_000), "wind_speed_kph": (0, 300)},
}


# ---------------------------------------------------------------------------
# HTTP helper (stdlib only — no httpx dep needed)
# ---------------------------------------------------------------------------
def _get(url: str, headers: dict | None = None, timeout: int = 45) -> bytes:
    hdrs = {"User-Agent": NOAA_UA, "Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    req = Request(url, headers=hdrs)
    for attempt in range(4):
        try:
            with urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except Exception as e:
            if attempt == 3:
                raise
            wait = 2 ** attempt
            print(f"    retry {attempt+1}/3 after {wait}s ({type(e).__name__})")
            time.sleep(wait)
    return b""


def _unwrap(obj):
    """NOAA wraps values as {value: X, unitCode: ...}."""
    return obj.get("value") if isinstance(obj, dict) else obj


# ---------------------------------------------------------------------------
# Source: EIA-930 Balancing Authority (AZPS, CISO, ERCO)
# ---------------------------------------------------------------------------
def pull_eia930() -> list[dict]:
    """Pull 7 days of hourly data for 3 BAs × 4 types."""
    if not EIA_KEY:
        print("  [EIA-930] SKIP — no EIA_API_KEY")
        return []
    all_rows = []
    for ba in ["AZPS", "CISO", "ERCO"]:
        print(f"  [EIA-930] {ba}...", end=" ", flush=True)
        url = (
            f"https://api.eia.gov/v2/electricity/rto/region-data/data/"
            f"?api_key={EIA_KEY}&frequency=hourly&data[0]=value"
            f"&facets[respondent][]={ba}"
            f"&facets[type][]=D&facets[type][]=DF&facets[type][]=NG&facets[type][]=TI"
            f"&sort[0][column]=period&sort[0][direction]=desc&length=5000"
            f"&offset=0"
        )
        try:
            data = json.loads(_get(url))
            records = data.get("response", {}).get("data", [])
            for r in records:
                val = r.get("value")
                all_rows.append({
                    "_source": f"eia930_{ba.lower()}",
                    "dataset": "eia930",
                    "period_utc": r.get("period"),
                    "respondent": r.get("respondent"),
                    "respondent_name": r.get("respondent-name"),
                    "type": r.get("type"),
                    "type_name": r.get("type-name"),
                    "value_mw": float(val) if val is not None else None,
                })
            print(f"{len(records)} rows")
        except Exception as e:
            print(f"FAILED ({e})")
        time.sleep(0.3)  # rate-limit courtesy
    return all_rows


# ---------------------------------------------------------------------------
# Source: EIA Natural Gas Spot Prices (Henry Hub, Waha)
# ---------------------------------------------------------------------------
def pull_eia_ng() -> list[dict]:
    """Pull ~90 days of daily gas spot prices."""
    if not EIA_KEY:
        print("  [EIA-NG] SKIP — no EIA_API_KEY")
        return []
    all_rows = []
    configs = [
        ("RNGWHHD", "henry_hub_spot", "https://api.eia.gov/v2/natural-gas/pri/fut/data/"),
        ("RNGC1", "ng_front_month", "https://api.eia.gov/v2/natural-gas/pri/fut/data/"),
        ("RNGC4", "ng_contract4", "https://api.eia.gov/v2/natural-gas/pri/fut/data/"),
    ]
    for series_id, label, endpoint in configs:
        print(f"  [EIA-NG] {label} ({series_id})...", end=" ", flush=True)
        start = (NOW - timedelta(days=90)).strftime("%Y-%m-%d")
        url = (
            f"{endpoint}"
            f"?api_key={EIA_KEY}&frequency=daily&data[0]=value"
            f"&facets[series][]={series_id}"
            f"&sort[0][column]=period&sort[0][direction]=desc&length=5000"
            f"&start={start}"
        )
        try:
            data = json.loads(_get(url))
            records = data.get("response", {}).get("data", [])
            for r in records:
                val = r.get("value")
                all_rows.append({
                    "_source": f"eia_ng_{label}",
                    "dataset": "eia_ng",
                    "period_utc": r.get("period"),
                    "series": r.get("series") or series_id,
                    "series_description": r.get("series-description", ""),
                    "price_usd_per_mmbtu": float(val) if val is not None else None,
                })
            print(f"{len(records)} rows")
        except Exception as e:
            print(f"FAILED ({e})")
        time.sleep(0.3)
    return all_rows


# ---------------------------------------------------------------------------
# Source: CAISO OASIS 5-min LMP (3 nodes × all components)
# ---------------------------------------------------------------------------
def pull_caiso_lmp() -> list[dict]:
    """Pull 6 hours of 5-min LMP for Palo Verde + SP15 + NP15."""
    print("  [CAISO] OASIS LMP...", end=" ", flush=True)
    all_rows = []
    nodes = ["PALOVRDE_ASR-APND", "TH_SP15_GEN-APND", "TH_NP15_GEN-APND"]
    
    # CAISO OASIS allows max 1 node per request via SingleZip
    end = NOW.replace(second=0, microsecond=0)
    end = end.replace(minute=(end.minute // 5) * 5)
    start = end - timedelta(hours=6)
    
    for node in nodes:
        params = (
            f"queryname=PRC_INTVL_LMP&market_run_id=RTM&version=1&resultformat=6"
            f"&node={node}"
            f"&startdatetime={start.strftime('%Y%m%dT%H:%M-0000')}"
            f"&enddatetime={end.strftime('%Y%m%dT%H:%M-0000')}"
        )
        try:
            body = _get(f"https://oasis.caiso.com/oasisapi/SingleZip?{params}", timeout=60)
            zf = zipfile.ZipFile(io.BytesIO(body))
            for name in zf.namelist():
                if not name.endswith(".csv"):
                    continue
                with zf.open(name) as fh:
                    reader = csv.DictReader(io.TextIOWrapper(fh))
                    for r in reader:
                        val = r.get("VALUE") or r.get("MW")
                        all_rows.append({
                            "_source": "caiso_lmp",
                            "dataset": "caiso_lmp",
                            "interval_start_utc": r.get("INTERVALSTARTTIME_GMT"),
                            "interval_end_utc": r.get("INTERVALENDTIME_GMT"),
                            "node": r.get("NODE"),
                            "lmp_component": r.get("LMP_TYPE"),
                            "price_usd_per_mwh": float(val) if val else None,
                        })
            print(f"{node.split('_')[0]}✓", end=" ", flush=True)
        except Exception as e:
            print(f"{node.split('_')[0]}✗({e})", end=" ", flush=True)
        time.sleep(1.5)  # CAISO rate limit is strict
    
    print(f"→ {len(all_rows)} total rows")
    return all_rows


# ---------------------------------------------------------------------------
# Source: NOAA NWS Gridpoint Forecast (Phoenix PSR/158,56)
# ---------------------------------------------------------------------------
def pull_noaa_forecast() -> list[dict]:
    """Pull full 7-day hourly forecast (156 periods)."""
    print("  [NOAA] Phoenix forecast...", end=" ", flush=True)
    try:
        data = json.loads(_get("https://api.weather.gov/gridpoints/PSR/158,56/forecast/hourly"))
        periods = data.get("properties", {}).get("periods", [])
        rows = []
        for p in periods:
            precip = p.get("probabilityOfPrecipitation", {})
            wind_str = p.get("windSpeed", "")
            # Parse "15 mph" → 15.0
            wind_val = None
            if isinstance(wind_str, str) and "mph" in wind_str.lower():
                try:
                    wind_val = float(wind_str.split()[0])
                except (ValueError, IndexError):
                    pass
            rows.append({
                "_source": "noaa_phoenix",
                "dataset": "noaa_forecast",
                "start_time_utc": p.get("startTime"),
                "end_time_utc": p.get("endTime"),
                "grid_id": "PSR/158,56",
                "temperature_f": p.get("temperature"),
                "wind_speed_mph": wind_val,
                "wind_speed_raw": wind_str,
                "probability_of_precipitation": precip.get("value") if isinstance(precip, dict) else precip,
                "short_forecast": p.get("shortForecast"),
                "is_daytime": p.get("isDaytime"),
            })
        print(f"{len(rows)} rows")
        return rows
    except Exception as e:
        print(f"FAILED ({e})")
        return []


# ---------------------------------------------------------------------------
# Source: NOAA NWS Station Observations (KPHX)
# ---------------------------------------------------------------------------
def pull_noaa_obs() -> list[dict]:
    """Pull all available recent observations from KPHX (typically ~200+)."""
    print("  [NOAA] KPHX observations...", end=" ", flush=True)
    try:
        data = json.loads(_get("https://api.weather.gov/stations/KPHX/observations"))
        features = data.get("features", [])
        rows = []
        for feat in features:
            p = feat.get("properties", {})
            rows.append({
                "_source": "noaa_phoenix_obs",
                "dataset": "noaa_obs",
                "timestamp_utc": p.get("timestamp"),
                "station": "KPHX",
                "temperature_c": _unwrap(p.get("temperature")),
                "wind_speed_kph": _unwrap(p.get("windSpeed")),
                "wind_direction_deg": _unwrap(p.get("windDirection")),
                "barometric_pressure_pa": _unwrap(p.get("barometricPressure")),
                "visibility_m": _unwrap(p.get("visibility")),
                "relative_humidity_pct": _unwrap(p.get("relativeHumidity")),
                "dewpoint_c": _unwrap(p.get("dewpoint")),
                "heat_index_c": _unwrap(p.get("heatIndex")),
                "text_description": p.get("textDescription"),
            })
        print(f"{len(rows)} rows")
        return rows
    except Exception as e:
        print(f"FAILED ({e})")
        return []


# ---------------------------------------------------------------------------
# Quality validation + distribution stats
# ---------------------------------------------------------------------------
def validate_and_report(source_data: dict[str, list[dict]]) -> dict:
    """Run range checks, compute distribution stats, build DQ report."""
    report = {
        "generated_at_utc": NOW.isoformat(),
        "total_rows": 0,
        "sources": {},
    }
    total_pass = 0
    total_fail = 0

    for dataset, rows in sorted(source_data.items()):
        if not rows:
            continue
        n = len(rows)
        report["total_rows"] += n

        src_report = {
            "row_count": n,
            "unique_sources": sorted(set(r.get("_source", "") for r in rows)),
            "columns": {},
            "range_violations": [],
            "null_rates": {},
        }

        # Collect all columns
        all_cols = sorted(set().union(*(r.keys() for r in rows)) - {"_source", "dataset"})

        for col in all_cols:
            vals = [r.get(col) for r in rows]
            non_null = [v for v in vals if v is not None and v != ""]
            null_rate = 1.0 - len(non_null) / n if n > 0 else 1.0
            src_report["null_rates"][col] = round(null_rate, 4)

            # Try numeric stats
            nums = []
            for v in non_null:
                try:
                    nums.append(float(v))
                except (ValueError, TypeError):
                    pass

            col_stats = {"non_null_count": len(non_null)}
            if nums:
                col_stats.update({
                    "min": round(min(nums), 4),
                    "max": round(max(nums), 4),
                    "mean": round(statistics.mean(nums), 4),
                    "median": round(statistics.median(nums), 4),
                    "stdev": round(statistics.stdev(nums), 4) if len(nums) > 1 else 0,
                    "p5": round(sorted(nums)[max(0, int(len(nums) * 0.05))], 4),
                    "p25": round(sorted(nums)[int(len(nums) * 0.25)], 4),
                    "p75": round(sorted(nums)[int(len(nums) * 0.75)], 4),
                    "p95": round(sorted(nums)[min(len(nums)-1, int(len(nums) * 0.95))], 4),
                })
            else:
                # Categorical stats
                uniq = sorted(set(str(v) for v in non_null))
                col_stats["unique_count"] = len(uniq)
                col_stats["sample_values"] = uniq[:10]

            src_report["columns"][col] = col_stats

        # Range checks
        checks = RANGE_CHECKS.get(dataset, {})
        for col, (lo, hi) in checks.items():
            vals = [r.get(col) for r in rows if r.get(col) is not None]
            for v in vals:
                try:
                    fv = float(v)
                    if fv < lo or fv > hi:
                        src_report["range_violations"].append(
                            {"column": col, "value": fv, "expected_range": [lo, hi]}
                        )
                except (ValueError, TypeError):
                    pass

        n_violations = len(src_report["range_violations"])
        src_report["range_violations_count"] = n_violations
        # Cap stored violations at 20 to keep report readable
        src_report["range_violations"] = src_report["range_violations"][:20]
        src_report["quality_pass"] = n_violations == 0
        total_pass += n - n_violations
        total_fail += n_violations

        report["sources"][dataset] = src_report

    report["total_pass"] = total_pass
    report["total_fail"] = total_fail
    report["overall_quality_pct"] = round(100 * total_pass / max(1, total_pass + total_fail), 2)
    return report


def save_per_source_csv(dataset: str, rows: list[dict]) -> Path:
    """Save per-source CSV for easy examination."""
    if not rows:
        return Path()
    cols = sorted(set().union(*(r.keys() for r in rows)))
    path = TRAINING_DIR / f"{dataset}_{TS_TAG}.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return path


def save_parquet_if_possible(dataset: str, rows: list[dict]) -> Path | None:
    """Save as parquet for downstream training if pandas + pyarrow available."""
    try:
        import pandas as pd
        df = pd.DataFrame(rows)
        path = TRAINING_DIR / f"{dataset}_{TS_TAG}.parquet"
        df.to_parquet(path, index=False, engine="pyarrow")
        return path
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    only = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        if idx + 1 < len(sys.argv):
            only = set(sys.argv[idx + 1].split(","))

    # Load .env manually (no dotenv dep required)
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    global EIA_KEY
    EIA_KEY = os.environ.get("EIA_API_KEY", "")

    print(f"{'='*70}")
    print(f"TRAINING DATA PULL — {NOW.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'='*70}")
    print(f"EIA API key: {'✓ set' if EIA_KEY else '✗ missing'}")
    print(f"Output: {TRAINING_DIR}/")
    print()

    # Pull from all sources
    source_data: dict[str, list[dict]] = {}
    
    pullers = [
        ("eia", "eia930", pull_eia930),
        ("eia", "eia_ng", pull_eia_ng),
        ("caiso", "caiso_lmp", pull_caiso_lmp),
        ("noaa", "noaa_forecast", pull_noaa_forecast),
        ("noaa", "noaa_obs", pull_noaa_obs),
    ]

    for group, dataset, fn in pullers:
        if only and group not in only and dataset not in only:
            continue
        rows = fn()
        if rows:
            source_data[dataset] = rows
            csv_path = save_per_source_csv(dataset, rows)
            pq_path = save_parquet_if_possible(dataset, rows)
            fmt = f"CSV: {csv_path.name}"
            if pq_path:
                fmt += f" + Parquet: {pq_path.name}"
            print(f"    → saved {len(rows)} rows ({fmt})")
        print()

    if not source_data:
        print("No data pulled — check API keys and network.")
        return 1

    # Validate and report
    print(f"{'='*70}")
    print("QUALITY VALIDATION")
    print(f"{'='*70}")
    report = validate_and_report(source_data)
    report_path = TRAINING_DIR / f"quality_report_{TS_TAG}.json"
    report_path.write_text(json.dumps(report, indent=2, default=str))

    # Print summary
    print(f"\n  Total rows:     {report['total_rows']}")
    print(f"  Range passes:   {report['total_pass']}")
    print(f"  Range failures: {report['total_fail']}")
    print(f"  Quality:        {report['overall_quality_pct']}%")
    print()

    for dataset, info in report["sources"].items():
        print(f"  --- {dataset} ({info['row_count']} rows, sources: {info['unique_sources']}) ---")
        if info["range_violations_count"] > 0:
            print(f"    ⚠ {info['range_violations_count']} range violations!")
        else:
            print(f"    ✓ All range checks passed")
        
        # Show key distribution stats
        for col, stats in info["columns"].items():
            if "mean" in stats:
                print(f"    {col}: μ={stats['mean']}, σ={stats['stdev']}, "
                      f"range=[{stats['min']}, {stats['max']}], "
                      f"p5={stats['p5']}, p95={stats['p95']}")
            elif "unique_count" in stats:
                samples = stats.get("sample_values", [])[:5]
                print(f"    {col}: {stats['unique_count']} unique — {samples}")
        
        # Null rates > 0
        high_null = {c: r for c, r in info["null_rates"].items() if r > 0.01}
        if high_null:
            print(f"    null rates > 1%: {high_null}")
        print()

    print(f"Quality report → {report_path}")
    print(f"Training data  → {TRAINING_DIR}/")

    # Also save a combined CSV for quick inspection
    all_rows = []
    for rows in source_data.values():
        all_rows.extend(rows)
    combined_path = TRAINING_DIR / f"combined_training_{TS_TAG}.csv"
    all_cols = sorted(set().union(*(r.keys() for r in all_rows)))
    with combined_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=all_cols)
        w.writeheader()
        w.writerows(all_rows)
    print(f"Combined CSV   → {combined_path.name} ({len(all_rows)} rows)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
