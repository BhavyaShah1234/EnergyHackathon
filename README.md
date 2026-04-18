# collide-energy-pipeline

Production data ingestion pipeline for the **Collide AI-for-Energy Hackathon** (2026-04-18).  
Pulls grid, market, weather, gas, geospatial, and infrastructure data from the public APIs specified in the APS and Collide problem briefs. Validates every row, lands it in a partitioned Parquet lake, and exposes a DuckDB catalog for downstream modeling.

**Pipeline-only** — models, dashboards, and scenario code live in sibling repos/branches.

---

## Source Coverage

### ✅ Live Time-Series APIs (Verified)

| Source | Dataset | Cadence | Hackathon Brief | API Docs |
|---|---|---|---|---|
| **EIA-930 BA** (AZPS, CISO, ERCO) | `eia930` | 15 min | APS + Collide context | [EIA Open Data v2 — Electricity](https://www.eia.gov/opendata/browser/electricity/rto/region-data) |
| **EIA NG Spot** (Henry Hub, Waha) | `eia_ng` | 1 hr | Collide sub-C | [EIA Open Data v2 — Natural Gas Prices](https://www.eia.gov/opendata/browser/natural-gas/pri) |
| **CAISO OASIS LMP** (Palo Verde, SP15, NP15) | `caiso_lmp` | 5 min | Collide sub-C | [CAISO OASIS](http://oasis.caiso.com) · [Developer Portal](https://developer.caiso.com/) |
| **NOAA NWS Forecast** (Phoenix PSR/158,56) | `noaa_forecast` | 30 min | APS | [NWS API — Gridpoints Forecast](https://www.weather.gov/documentation/services-web-api) |
| **NOAA NWS Observations** (KPHX) | `noaa_obs` | 10 min | APS | [NWS API — Station Observations](https://www.weather.gov/documentation/services-web-api) |

### ✅ Static Geospatial APIs (Implemented)

| Source | Dataset | Cadence | Hackathon Brief | API Docs |
|---|---|---|---|---|
| **BLM Surface Mgmt Agency** (AZ/NM/TX) | `blm_sma` | Daily | Collide sub-A | [BLM GeoBOB ArcGIS Hub](https://gbp-blm-egis.hub.arcgis.com/) · [REST Directory](https://gis.blm.gov/arcgis/rest/services/lands/) |
| **FCC BDC Fiber** (FTTP, AZ/NM/TX) | `hifld_fiber` | Daily | Collide sub-A | [FCC Broadband Data Collection](https://broadbandmap.fcc.gov/) |
| **USGS NHD Waterbodies** (AZ/NM/TX) | `nhd_waterbody` | Daily | Collide sub-A | [USGS NHD](https://www.usgs.gov/national-hydrography/national-hydrography-dataset) · [MapServer](https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer) |
| **FEMA NFHL Floodplain** (AZ/NM/TX) | `fema_floodplain` | Daily | Collide sub-A | [FEMA NFHL](https://www.fema.gov/flood-maps/national-flood-hazard-layer) · [REST Service](https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer) |

### ⏸ Pending

| Source | Reason |
|---|---|
| ERCOT MIS (LMP, DAM, fuel-mix, outages) | Pending developer token from [mis.ercot.com](https://mis.ercot.com) |
| PHMSA Annual Report + Incident DB | Static bulk; not yet loaded |
| EIA-176 / EIA-757 | Static bulk; not yet loaded |
| Pecan Street, NREL SMART-DS / NSRDB / EVI-Pro | Static; not yet loaded |

> **Note on HIFLD:** The HIFLD Open portal was [decommissioned August 2025](https://hifld-geoplatform.opendata.arcgis.com/). The `hifld_fiber` source ingests FCC Broadband Data Collection (BDC) FTTP availability data as the best public proxy. Swap for HIFLD Secure if a DHS GII Data Use Agreement is obtained.

---

## Schema Reference

Every row that enters silver passes a [pandera](https://pandera.readthedocs.io/) schema. Schemas are defined in [`pipeline/quality/schemas.py`](pipeline/quality/schemas.py).

### `eia930` — EIA-930 Hourly Balancing Authority Data

> Official docs: [EIA Open Data v2 — Electricity RTO Region Data](https://www.eia.gov/opendata/browser/electricity/rto/region-data)

| Column | Type | Constraints | Description |
|---|---|---|---|
| `period_utc` | `datetime64[ns, UTC]` | not null | Hour-resolution UTC timestamp from EIA `period` field |
| `respondent` | `str` | ∈ {AZPS, CISO, ERCO, WALC, SRP, PNM} | Balancing authority ID per [EIA-930](https://www.eia.gov/electricity/gridmonitor/about) |
| `type` | `str` | ∈ {D, DF, NG, TI} | D=demand, DF=day-ahead forecast, NG=net generation, TI=total interchange |
| `value_mw` | `float` | [-200000, 400000] | Megawatts; nullable for missing periods |

**Natural key:** `(period_utc, respondent, type)` · **Freshness SLA:** 3 hours

---

### `eia_ng` — EIA Natural Gas Daily Spot Prices

> Official docs: [EIA Open Data v2 — Natural Gas Prices](https://www.eia.gov/opendata/browser/natural-gas/pri)

| Column | Type | Constraints | Description |
|---|---|---|---|
| `period_utc` | `datetime64[ns, UTC]` | not null | Trading date (UTC) |
| `series` | `str` | not null | EIA series ID: `RNGWHHD` (Henry Hub), `RNGC4` (Waha proxy) |
| `price_usd_per_mmbtu` | `float` | [0, 100] | Spot price in $/MMBtu; nullable on weekends/holidays |

**Natural key:** `(period_utc, series)` · **Freshness SLA:** 48h (Henry Hub), 72h (Waha)

---

### `caiso_lmp` — CAISO OASIS 5-Minute LMP

> Official docs: [CAISO OASIS](http://oasis.caiso.com) · [Developer Portal](https://developer.caiso.com/) · Query: `PRC_INTVL_LMP`, `market_run_id=RTM`

| Column | Type | Constraints | Description |
|---|---|---|---|
| `interval_start_utc` | `datetime64[ns, UTC]` | not null | Interval start (5-min resolution) |
| `interval_end_utc` | `datetime64[ns, UTC]` | not null | Interval end |
| `node` | `str` | not null | Pricing node: `PALOVRDE_ASR-APND`, `TH_SP15_GEN-APND`, `TH_NP15_GEN-APND` |
| `lmp_component` | `str` | ∈ {LMP, MCE, MCC, MCL} | Total LMP, energy, congestion, loss components |
| `price_usd_per_mwh` | `float` | [-2000, 20000] | $/MWh locational marginal price |

**Natural key:** `(interval_start_utc, node, lmp_component)` · **Freshness SLA:** 1 hour

---

### `noaa_forecast` — NOAA NWS Hourly Gridpoint Forecast

> Official docs: [NWS API Web Service — Gridpoints](https://www.weather.gov/documentation/services-web-api)

| Column | Type | Constraints | Description |
|---|---|---|---|
| `start_time_utc` | `datetime64[ns, UTC]` | not null | Forecast period start |
| `end_time_utc` | `datetime64[ns, UTC]` | not null | Forecast period end |
| `grid_id` | `str` | not null | NWS gridpoint: `PSR/158,56` (Phoenix metro) |
| `temperature_f` | `float` | [-60, 140] | Forecast temperature (°F) |
| `wind_speed_mph` | `float` | [0, 200] | Forecast wind speed (mph) |
| `probability_of_precipitation` | `float` | [0, 100] | POP percentage |
| `short_forecast` | `str` | nullable | e.g. "Sunny", "Partly Cloudy" |

**Natural key:** `(start_time_utc, grid_id)` · **Freshness SLA:** 2 hours

---

### `noaa_obs` — NOAA NWS Station Observations

> Official docs: [NWS API Web Service — Station Observations](https://www.weather.gov/documentation/services-web-api)

| Column | Type | Constraints | Description |
|---|---|---|---|
| `timestamp_utc` | `datetime64[ns, UTC]` | not null | Observation timestamp |
| `station` | `str` | not null | Station ID: `KPHX` (Phoenix Sky Harbor) |
| `temperature_c` | `float` | [-50, 60] | Observed temperature (°C) |
| `wind_speed_kph` | `float` | [0, 300] | Observed wind speed (km/h) |
| `visibility_m` | `float` | [0, 100000] | Observed visibility (meters) |
| `text_description` | `str` | nullable | e.g. "Clear", "Mostly Cloudy" |

**Natural key:** `(timestamp_utc, station)` · **Freshness SLA:** 2 hours

---

### `blm_sma` — BLM Surface Management Agency (Land Ownership)

> Official docs: [BLM GeoBOB Data Hub](https://gbp-blm-egis.hub.arcgis.com/) · [SMA Data Standard](https://www.blm.gov/services/geospatial/GISData)

| Column | Type | Constraints | Description |
|---|---|---|---|
| `object_id` | `float` | nullable | ArcGIS OBJECTID |
| `sma_code` | `str` | nullable | Surface Management Agency code (e.g. BLM, FS, DOD) |
| `admin_agency` | `str` | nullable | Administering agency code |
| `admin_state` | `str` | ∈ {AZ, NM, TX} | BLM administrative state |
| `admin_name` | `str` | nullable | Management unit name |
| `acreage` | `float` | ≥ 0 | Parcel acreage from `GIS_ACRES` |
| `shape_area_sq_deg` | `float` | nullable | Polygon area in square degrees |
| `geometry_geojson` | `str` | nullable | Full GeoJSON geometry (polygon) |

**Natural key:** `(object_id)` · **Freshness SLA:** 168h (weekly — static data)

---

### `hifld_fiber` — Fiber Infrastructure (FCC BDC Proxy)

> Official docs: [FCC Broadband Data Collection](https://broadbandmap.fcc.gov/) · [BDC Data Specification](https://help.bdc.fcc.gov/hc/en-us)

| Column | Type | Constraints | Description |
|---|---|---|---|
| `frn` | `str` | nullable | FCC Registration Number |
| `provider_id` | `str` | nullable | ISP provider identifier |
| `brand_name` | `str` | nullable | ISP brand name (e.g. "AT&T Fiber") |
| `state_fips` | `str` | ∈ {04, 35, 48} | State FIPS: 04=AZ, 35=NM, 48=TX |
| `block_geoid` | `str` | nullable | Census block GEOID (15 digits) |
| `technology_code` | `str` | nullable | FCC tech code: `50` = Fiber to the Premises |
| `max_download_mbps` | `float` | ≥ 0 | Max advertised download speed (Mbps) |
| `max_upload_mbps` | `float` | ≥ 0 | Max advertised upload speed (Mbps) |
| `low_latency` | `str` | nullable | Low-latency flag (Y/N) |
| `geometry_geojson` | `str` | nullable | Census block polygon (GeoJSON) |

**Natural key:** `(block_geoid, provider_id)` · **Freshness SLA:** 168h (weekly)

---

### `nhd_waterbody` — USGS NHD Waterbody Polygons

> Official docs: [USGS National Hydrography Dataset](https://www.usgs.gov/national-hydrography/national-hydrography-dataset) · [NHD MapServer](https://hydro.nationalmap.gov/arcgis/rest/services/nhd/MapServer)

| Column | Type | Constraints | Description |
|---|---|---|---|
| `object_id` | `float` | nullable | ArcGIS OBJECTID |
| `gnis_name` | `str` | nullable | Geographic Names Info System name (e.g. "Lake Pleasant") |
| `feature_type` | `str` | nullable | NHD FTYPE: LakePond, Reservoir, SwampMarsh, etc. |
| `feature_code` | `str` | nullable | NHD FCODE (5-digit hydrographic classification) |
| `area_sq_km` | `float` | ≥ 0 | Waterbody surface area in km² |
| `reach_code` | `str` | nullable | NHD Reach Code (14-digit identifier for network tracing) |
| `geometry_geojson` | `str` | nullable | Waterbody polygon (GeoJSON) |

**Natural key:** `(object_id)` · **Freshness SLA:** 168h (weekly — static data)

---

### `fema_floodplain` — FEMA NFHL Flood Hazard Zones

> Official docs: [FEMA National Flood Hazard Layer](https://www.fema.gov/flood-maps/national-flood-hazard-layer) · [NFHL REST Service](https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer)

| Column | Type | Constraints | Description |
|---|---|---|---|
| `object_id` | `float` | nullable | ArcGIS OBJECTID |
| `flood_area_id` | `str` | nullable | FEMA flood area identifier (`FLD_AR_ID`) |
| `flood_zone` | `str` | nullable | FEMA zone: A, AE, AH, AO, V, VE, X, D ([zone definitions](https://msc.fema.gov/portal/home)) |
| `zone_subtype` | `str` | nullable | Zone subtype: FLOODWAY, COASTAL FLOODPLAIN, etc. |
| `sfha_flag` | `str` | nullable | Special Flood Hazard Area flag (T/F) |
| `static_bfe_ft` | `float` | nullable | Base Flood Elevation in feet (NAVD88) |
| `depth_ft` | `float` | nullable | Flood depth in feet (Zone AO/AH only) |
| `geometry_geojson` | `str` | nullable | Flood zone polygon (GeoJSON) |

**Natural key:** `(object_id)` · **Freshness SLA:** 168h (weekly — static data)

---

### Provenance Columns (All Datasets)

Every row in every dataset carries four provenance columns injected by [`BaseIngestor`](pipeline/base.py):

| Column | Type | Description |
|---|---|---|
| `_source` | `str` | Source config key (e.g. `eia930_azps`, `blm_sma`) |
| `_request_id` | `str` | UUID4 for the HTTP request that produced this row |
| `_fetched_at_utc` | `datetime64[ns, UTC]` | When the API response was received |
| `_payload_sha256` | `str` | SHA256 of the raw response body (dedup + integrity) |

---

## Data Quality Guarantees

| Guarantee | Implementation |
|---|---|
| **No corrupted rows** | Every row passes its pandera schema; violations are quarantined, never dropped silently |
| **Idempotent writes** | Natural-key dedup per dataset; re-running the same window is a no-op |
| **Provenance trail** | `_source`, `_request_id`, `_fetched_at_utc`, `_payload_sha256` on every row |
| **Row-level lineage** | DuckDB `lineage` table maps every silver row to the `request_id` and raw payload that produced it |
| **Append-only audit** | `data/_meta/audit/YYYY-MM-DD.jsonl` logs every fetch and validation outcome |
| **Tamper-evident silver** | `data/_meta/manifest.json` holds SHA256 of every silver parquet; `scripts/verify_integrity.py` detects drift |
| **Fail loud** | Freshness SLA per source. Failed runs recorded in DuckDB `run_ledger` and per-run JSON DQ reports |
| **UTC everywhere** | All timestamps normalized to `datetime64[ns, UTC]` at ingest |
| **Secrets never in git** | `.env` is gitignored; `.env.example` documents every key |

---

## Project Layout

```
pipeline/
  base.py              BaseIngestor — fetch/parse/validate/store lifecycle
  http_client.py        HTTP client (retry, backoff, rate-limit per host, raw persistence)
  config.py             Loads config/sources.yaml + .env → typed PipelineConfig
  storage.py            raw → bronze → silver parquet, DuckDB catalog registration
  audit.py              Append-only JSONL audit log + DuckDB run_ledger + lineage
  integrity.py          SHA256 manifest for tamper-evident silver
  registry.py           Dataset catalog: source → ingestor class mapping
  quality/
    schemas.py          Pandera schemas per dataset (the contract with downstream)
    checks.py           Schema validation, freshness SLA, dedup, null-rate checks
    report.py           Per-run JSON DQ report
  sources/
    eia930.py            EIA-930 hourly BA demand/forecast/netgen/interchange
    eia_ng.py            Henry Hub + Waha daily natural gas spot prices
    caiso.py             CAISO OASIS 5-min LMP at Palo Verde, SP15, NP15
    noaa.py              NWS Phoenix forecast + KPHX observations
    blm_glo.py           BLM Surface Management Agency land ownership (AZ/NM/TX)
    hifld_fiber.py       Fiber infrastructure proxy via FCC BDC (AZ/NM/TX)
    epa_nhd.py           USGS NHD waterbodies + FEMA NFHL floodplains (AZ/NM/TX)
orchestrator/
  run_once.py            One-shot backfill/catch-up
  run_live.py            Continuous (APScheduler) polling runner
config/
  sources.yaml           Endpoints, facets, cadence, freshness SLA, rate limits
scripts/
  live_sample.py         Quick live verification (no API keys needed)
  pull_diverse_sample.py Zero-dep live diversity sampling
  catalog.py             Print dataset → rows, freshness, last run
  explain.py             Trace any row back to its raw API response
  verify_integrity.py    Verify silver files against SHA256 manifest
  purge_old_raw.py       Clean up raw audit trail by retention policy
data/
  raw/                   Untouched API responses, partitioned by source/date
  bronze/                Parsed + typed parquet, one per source/date
  silver/                Validated, deduped, feature-ready for downstream ML
  quarantine/            Rows that failed validation (with _reason column)
  _meta/
    catalog.duckdb       Silver views + run_ledger + lineage tables
    manifest.json        SHA256 manifest of every silver parquet
    audit/               Append-only JSONL (YYYY-MM-DD.jsonl)
    runs/                Per-run JSON DQ reports
  _samples/              Live sample data (committed to git for verification)
tests/
  test_quality.py        DQ layer tests (schema, quarantine, dedup, freshness)
  test_registry.py       Registry import guard (every entry must resolve)
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- An [EIA API key](https://www.eia.gov/opendata/register.php) (free, instant) for EIA-930 and NG spot

### Setup

```bash
git clone https://github.com/BhavyaShah1234/EnergyHackathon.git
cd EnergyHackathon
git checkout suhas/data-pipeline

cp .env.example .env   # fill EIA_API_KEY at minimum
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Quick Verification (No API Keys)

```bash
# Pull live samples from NOAA + CAISO (no keys needed)
python scripts/live_sample.py
python scripts/pull_diverse_sample.py
```

### Full Pipeline Run

```bash
# One-shot catch-up (all sources)
python -m orchestrator.run_once

# Specific sources only
python -m orchestrator.run_once --only eia930_azps,caiso_lmp,noaa_phoenix

# Geospatial sources only
python -m orchestrator.run_once --only blm_sma,nhd_waterbody,fema_floodplain

# Continuous polling (each source at its configured cadence)
python -m orchestrator.run_live
```

### Colab

```python
!git clone <repo> && cd EnergyHackathon && pip install -q -r requirements.txt
import os
os.environ["EIA_API_KEY"] = "..."
os.environ["DATA_ROOT"] = "/content/drive/MyDrive/collide/data"
!python -m orchestrator.run_once
```

---

## For Downstream Teammates

- **Modelers:** Read from `data/silver/*.parquet`. Every file has a stable schema. Filter by `_fetched_at_utc` for point-in-time training to avoid leakage.
- **Geospatial:** Parse `geometry_geojson` with `json.loads()` or `shapely.geometry.shape()`. No geopandas dependency at ingest time.
- **Scenario/What-if:** Silver tables are tidy enough to feed OpenDSS or TFT directly. Join keys documented in [`pipeline/registry.py`](pipeline/registry.py).
- **Dashboard:** Query `data/_meta/catalog.duckdb` — it's the single source of truth:

```sql
-- All failed runs in the last 24h
SELECT run_id, dataset, source, error
FROM run_ledger
WHERE status = 'fail' AND started_at_utc > now() - INTERVAL 1 DAY;

-- Row-level provenance
SELECT * FROM lineage
WHERE dataset = 'eia930'
  AND natural_key = '{"period_utc":"2026-04-18 15:00:00+00:00","respondent":"AZPS","type":"D"}';
```

---

## Inspecting Row History

```bash
# Every fetch that ever touched a specific row
python scripts/explain.py --dataset eia930 \
  --key '{"period_utc":"2026-04-18 15:00:00+00:00","respondent":"AZPS","type":"D"}'

# Has anyone mutated silver outside the pipeline?
python scripts/verify_integrity.py

# Print dataset catalog
python scripts/catalog.py
```

---

## Adding a New Source

1. Add entry to `config/sources.yaml` (endpoint, cadence, freshness SLA, natural key)
2. Add pandera schema to `pipeline/quality/schemas.py`
3. Implement `pipeline/sources/<name>.py` subclassing `BaseIngestor`
4. Register in `pipeline/registry.py`
5. Add per-host rate limit in `config/sources.yaml` → `http.per_host_rps`
6. `pytest tests/` — the registry test auto-validates all entries

---

## Verified Live Data

The `data/_samples/` directory contains live-verified API responses committed to git:

| File | Source | Rows | Verified At |
|---|---|---|---|
| `noaa_obs_*.json` | `api.weather.gov/stations/KPHX` | 20 obs | 2026-04-18T21:09Z |
| `noaa_forecast_*.json` | `api.weather.gov/gridpoints/PSR` | 24 hrs | 2026-04-18T21:09Z |
| `caiso_lmp_*.json` | `oasis.caiso.com` Palo Verde | 50 LMP | 2026-04-18T21:09Z |
| `diverse_sample_*.csv` | Union of above | 95 rows | 2026-04-18T21:09Z |
