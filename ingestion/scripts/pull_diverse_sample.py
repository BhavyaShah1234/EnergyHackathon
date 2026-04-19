#!/usr/bin/env python3
"""Pull diverse live samples — zero deps beyond stdlib."""
from __future__ import annotations
import csv, io, json, os, sys, zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "data" / "_samples"

def _get(url, ua="collide-energy-pipeline sdonthi4@asu.edu"):
    req = Request(url, headers={"User-Agent": ua, "Accept": "application/json"})
    with urlopen(req, timeout=30) as resp: return resp.read()

def _unwrap(obj):
    return obj.get("value") if isinstance(obj, dict) else obj

def pull_noaa_obs():
    print("  [1/4] NOAA KPHX observations...", end=" ", flush=True)
    data = json.loads(_get("https://api.weather.gov/stations/KPHX/observations"))
    rows = []
    for feat in data.get("features", [])[:20]:
        p = feat.get("properties", {})
        rows.append({"source":"noaa_obs","timestamp_utc":p.get("timestamp"),"station":"KPHX",
            "temperature_c":_unwrap(p.get("temperature")),"wind_speed_kph":_unwrap(p.get("windSpeed")),
            "visibility_m":_unwrap(p.get("visibility")),"text_description":p.get("textDescription")})
    print(f"{len(rows)} rows"); return rows

def pull_noaa_forecast():
    print("  [2/4] NOAA Phoenix forecast...", end=" ", flush=True)
    data = json.loads(_get("https://api.weather.gov/gridpoints/PSR/158,56/forecast/hourly"))
    rows = []
    for p in data.get("properties",{}).get("periods",[])[:24]:
        precip = p.get("probabilityOfPrecipitation",{})
        rows.append({"source":"noaa_forecast","start_time_utc":p.get("startTime"),
            "grid_id":"PSR/158,56","temperature_f":p.get("temperature"),
            "wind_speed":p.get("windSpeed"),
            "probability_of_precipitation":precip.get("value") if isinstance(precip,dict) else precip,
            "short_forecast":p.get("shortForecast")})
    print(f"{len(rows)} rows"); return rows

def pull_caiso_lmp():
    print("  [3/4] CAISO OASIS LMP (Palo Verde)...", end=" ", flush=True)
    now = datetime.now(timezone.utc).replace(minute=0,second=0,microsecond=0)
    from datetime import timedelta
    start = now - timedelta(hours=2)
    params = (f"queryname=PRC_INTVL_LMP&market_run_id=RTM&version=1&resultformat=6"
        f"&node=PALOVRDE_ASR-APND&startdatetime={start.strftime('%Y%m%dT%H:%M-0000')}"
        f"&enddatetime={now.strftime('%Y%m%dT%H:%M-0000')}")
    try:
        body = _get(f"https://oasis.caiso.com/oasisapi/SingleZip?{params}")
        zf = zipfile.ZipFile(io.BytesIO(body)); rows = []
        for name in zf.namelist():
            if not name.endswith(".csv"): continue
            with zf.open(name) as fh:
                for r in csv.DictReader(io.TextIOWrapper(fh)):
                    rows.append({"source":"caiso_lmp","interval_start_utc":r.get("INTERVALSTARTTIME_GMT"),
                        "node":r.get("NODE"),"lmp_component":r.get("LMP_TYPE"),
                        "price_usd_per_mwh":r.get("VALUE") or r.get("MW")})
        print(f"{len(rows)} rows"); return rows[:50]
    except Exception as e: print(f"SKIP ({e})"); return []

def pull_eia930(api_key):
    if not api_key: print("  [4/4] EIA-930 AZPS... SKIP (no EIA_API_KEY)"); return []
    print("  [4/4] EIA-930 AZPS...", end=" ", flush=True)
    url = (f"https://api.eia.gov/v2/electricity/rto/region-data/data/"
        f"?api_key={api_key}&frequency=hourly&data[0]=value"
        f"&facets[respondent][]=AZPS&facets[type][]=D&facets[type][]=DF"
        f"&sort[0][column]=period&sort[0][direction]=desc&length=48")
    data = json.loads(_get(url)); rows = []
    for r in data.get("response",{}).get("data",[]):
        rows.append({"source":"eia930_azps","period_utc":r.get("period"),
            "respondent":r.get("respondent"),"type":r.get("type"),"value_mw":r.get("value")})
    print(f"{len(rows)} rows"); return rows

def main():
    SAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    eia_key = os.environ.get("EIA_API_KEY")
    print("Pulling diverse live samples...")
    all_rows = pull_noaa_obs() + pull_noaa_forecast() + pull_caiso_lmp() + pull_eia930(eia_key)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if all_rows:
        all_cols = sorted(set().union(*(r.keys() for r in all_rows)))
        with (SAMPLES_DIR / f"diverse_sample_{ts}.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=all_cols); w.writeheader(); w.writerows(all_rows)
        print(f"\n=> {len(all_rows)} rows written")
    by_source = {}
    for r in all_rows: by_source.setdefault(r["source"],[]).append(r)
    for src, rows in by_source.items():
        (SAMPLES_DIR/f"{src}_{ts}.json").write_text(json.dumps(rows, indent=2, default=str))
    print(f"\n{'='*60}\nDATA DIVERSITY SUMMARY\n{'='*60}")
    for src, rows in sorted(by_source.items()):
        cols = set().union(*(r.keys() for r in rows)) - {"source"}
        print(f"\n  {src} ({len(rows)} rows)")
        for c in sorted(cols):
            vals = [r.get(c) for r in rows if r.get(c) is not None]
            if not vals: continue
            try:
                nums = [float(v) for v in vals]
                print(f"    {c}: min={min(nums):.2f} max={max(nums):.2f}")
            except: print(f"    {c}: {len(set(str(v) for v in vals))} unique, e.g. {[str(v) for v in vals[:2]]}")
    return 0

if __name__ == "__main__": sys.exit(main())
