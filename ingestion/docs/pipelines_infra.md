# `pipelines_infra` — Natural Gas Pipeline Routes

**What:** Every interstate and intrastate natural gas pipeline segment in the WECC-SW + ERCOT region, with geometry, type, and operator. Collide sub-problem B: gas supply reliability.

**Source:** EIA's public ArcGIS FeatureServer ([Natural Gas Interstate and Intrastate Pipelines](https://services2.arcgis.com/FiaPA4ga0iQKduv3/arcgis/rest/services/Natural_Gas_Interstate_and_Intrastate_Pipelines_1/FeatureServer/0)). Unauthenticated. WGS84 (EPSG:4326).

**Scope:** bbox `lon ∈ [-125, -93]`, `lat ∈ [25, 42]` — AZ, NM, CA, NV, UT, CO, TX + parts of OR/ID/WY/OK/KS/LA.

---

## How to pull it

```bash
python -m orchestrator.run_once --only pipelines_infra
```

Or inline:

```python
from pipeline.http_client import HttpClient
from pipeline.sources.pipelines_infra import PipelineInfraIngestor

with HttpClient() as http:
    report = PipelineInfraIngestor(http=http).run()
print(report.ok, report.rows_out)
```

Writes to `data/silver/pipelines_infra/{date}.parquet`. Re-running is idempotent because the natural key is `pipeline_id`.

A small committed preview is available at `data/_samples/pipelines_infra_sample.csv`.

---

## Key fields

| Column | Meaning |
|---|---|
| `pipeline_id` | Stable EIA `FID` per segment |
| `pipe_type` | `Interstate` or `Intrastate` |
| `operator` | Pipeline operator name |
| `status` | Operational status from the source layer |
| `start_*`, `end_*` | First and last WGS84 vertices of the polyline |
| `midpoint_*` | Unweighted centroid of all vertices |
| `length_km` | Great-circle length along the polyline |
| `num_vertices` | Vertex count |
| `geometry_wkt` | OGC WKT `LINESTRING` geometry |

---

## Known gap

The public EIA layer does **not** expose per-segment `install_year`, `pipe_material`, `diameter_in`, or `max_operating_pressure_psi`.

Collide sub-B's failure-probability modeling wants vintage/material. Those have to come from PHMSA Annual Report form `F-7100.1-1`, joined downstream at the operator/state level once the team has a manual copy or a mirrored source.

Until then:

- use `pipelines_infra` for route proximity, operator concentration, and trunk/branch topology features
- do not claim segment-level vintage/material coverage
