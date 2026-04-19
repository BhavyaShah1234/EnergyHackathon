# `pipelines_infra` — Natural Gas Pipeline Routes

**What:** Every interstate and intrastate natural gas pipeline segment in the WECC-SW + ERCOT region, with geometry, type, and operator. Collide sub-problem B: gas supply reliability.

**Source:** EIA's public ArcGIS FeatureServer ([Natural Gas Interstate and Intrastate Pipelines](https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/Natural_Gas_Interstate_and_Intrastate_Pipelines_1/FeatureServer/0)). Unauthenticated. WGS84 (EPSG:4326).

**Scope:** bbox `lon ∈ [-125, -93]`, `lat ∈ [25, 42]` — AZ, NM, CA, NV, UT, CO, TX + parts of OR/ID/WY/OK/KS/LA. **15,958 segments** (5,850 interstate / 10,108 intrastate).

---

## How to pull it

```bash
# One-shot refresh (fetches all 15,958 segments, ~20s, 8 API pages)
python -m orchestrator.run_once --source pipelines_infra
```

Or inline:

```python
from pipeline.http_client import HttpClient
from pipeline.sources.pipelines_infra import PipelineInfraIngestor

with HttpClient() as http:
    report = PipelineInfraIngestor(http).run()
print(report.ok, report.rows_out)   # True 15958
```

Writes to `data/silver/pipelines_infra/{date}.parquet`. Re-running is a no-op — natural-key dedup on `pipeline_id` guarantees idempotency.

---

## How to read it

### pandas
```python
import pandas as pd
df = pd.read_parquet('data/silver/pipelines_infra')

# All El Paso Natural Gas segments
df[df['operator'].str.contains('El Paso Natural Gas', na=False)]

# Longest interstate trunks in the region
df[df['pipe_type']=='Interstate'].nlargest(10, 'length_km')

# Segments within 50km of a candidate site (lat, lon)
import numpy as np
site_lat, site_lon = 33.45, -112.07   # Phoenix
dlat = (df['midpoint_lat'] - site_lat).abs()
dlon = (df['midpoint_lon'] - site_lon).abs()
near = df[dlat**2 + dlon**2 < (50/111)**2]   # rough degree→km
```

### DuckDB (preferred for SQL + joins across sources)
```python
import duckdb
con = duckdb.connect('data/_meta/catalog.duckdb')

con.execute("""
  SELECT operator, pipe_type, count(*) segments, round(sum(length_km),1) total_km
  FROM pipelines_infra
  WHERE pipe_type = 'Interstate'
  GROUP BY 1, 2 ORDER BY total_km DESC LIMIT 10
""").df()
```

### GIS tools (QGIS, PostGIS, shapely)
`geometry_wkt` is standard OGC WKT. Load with `shapely.wkt.loads(...)` or import the parquet into QGIS directly — it has a WKT column handler.

---

## Field reference

| Column | Type | Nullable | Constraint | Meaning |
|---|---|---|---|---|
| `pipeline_id` | `int` | no | — | EIA `FID`, stable across refreshes. **Natural key.** |
| `pipe_type` | `str` | no | ∈ {`Interstate`, `Intrastate`} | FERC vs. state jurisdiction |
| `operator` | `str` | yes | — | Pipeline operator name (e.g. `El Paso Natural Gas Co`) |
| `status` | `str` | yes | — | Operational status. In current data, all rows are `Operating` |
| `start_lon`, `start_lat` | `float` | no | NA envelope | First vertex of the polyline (WGS84) |
| `end_lon`, `end_lat` | `float` | no | NA envelope | Last vertex |
| `midpoint_lon`, `midpoint_lat` | `float` | no | NA envelope | Unweighted centroid of **all** vertices — good enough for proximity queries |
| `length_km` | `float` | no | [0, 5000] | Great-circle distance along the polyline (haversine) |
| `num_vertices` | `int` | no | ≥ 2 | Polyline vertex count; correlates loosely with geometric complexity |
| `geometry_wkt` | `str` | no | — | OGC `LINESTRING (lon lat, lon lat, ...)` — feed to shapely/PostGIS/QGIS |
| `_source` | `str` | no | = `pipelines_infra` | Provenance — which source emitted this row |
| `_request_id` | `str` | no | UUID4 | Provenance — which HTTP fetch produced it (one per API page) |
| `_fetched_at_utc` | `datetime64[ns, UTC]` | no | — | Provenance — when we pulled it |
| `_payload_sha256` | `str` | no | hex | Provenance — SHA256 of the raw API response body |

---

## Small sample

Committed in [`data/_samples/pipelines_infra_sample.csv`](../data/_samples/pipelines_infra_sample.csv) (18 rows — interstate/intrastate mix, longest/shortest, AZ/NM/TX/CA representation). First few rows:

| pipeline_id | pipe_type | operator | start_lat | start_lon | length_km | num_vertices |
|---:|---|---|---:|---:|---:|---:|
| 3 | Interstate | El Paso Natural Gas Co | 31.79 | -102.86 | 32.3 | 4 |
| 21435 | Interstate | Enable Gas Transmission | 33.35 | -93.71 | 815.8 | 264 |
| 2 | Intrastate | Texas Intrastate Pipeline Co | 29.66 | -94.60 | 0.16 | 2 |
| 603 | Intrastate | San Diego Gas & Elec Co | 33.42 | -117.15 | 78.7 | 13 |

---

## Known gaps

**Not in this dataset:** `install_year` (pipe vintage), `pipe_material` (steel grade / plastic / cast iron), `diameter_in`, `max_operating_pressure_psi`.

The EIA public layer doesn't publish these. Collide sub-B's failure-probability modeling wants them — they live in PHMSA Annual Report form **F-7100.1-1**, aggregated at operator × state × year. Join path downstream:

```sql
-- conceptual; PHMSA loader is pending
SELECT p.*, a.miles_plastic, a.miles_steel, a.miles_pre_1970
FROM pipelines_infra p
LEFT JOIN phmsa_annual a USING (operator, state)
```

PHMSA's bulk zips on `phmsa.dot.gov` are Akamai-blocked to automated clients (403), so until we have a mirror or a browser-downloaded copy in `data/raw/phmsa/`, vintage/material are unknown per-segment. Document the approximation in any model that uses it.

---

## Data quality guarantees

- **Schema-validated** — 13 business columns + 4 provenance, `strict=True`. See [`pipeline/quality/schemas.py:177`](../pipeline/quality/schemas.py).
- **Range-checked** — lat/lon in North America envelope catches flipped coords; `length_km ∈ [0, 5000]` catches geometric glitches.
- **Quarantined on violation** — bad rows go to `data/quarantine/pipelines_infra/` with `_reason='schema_violation'`; never silently dropped.
- **Idempotent** — re-running produces identical silver output. Natural key = `(pipeline_id)`.
- **Full audit trail** — every row has `_request_id` + `_payload_sha256` linking back to a preserved raw API response in `data/raw/pipelines_infra/{date}/{request_id}.json`.
