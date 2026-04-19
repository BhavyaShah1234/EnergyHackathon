# Agent Handoff

This branch is the data-ingestion repo for the APS + Collide Energy hackathon work. Treat it as **pipeline-only**: ingestion, validation, storage, lineage, and source documentation belong here. Modeling, notebooks, dashboards, and scenario logic belong elsewhere.

## Current state

- Branch: `suhas/data-pipeline`
- Runnable implemented sources: `11`
- Explicit blockers from the brief that are **not** implemented: `ERCOT MIS`, `PHMSA annual/incidents`
- Design rule: do not leave half-wired connectors in code or config. If a source is blocked, document it in `README.md` and keep it out of `pipeline/registry.py`, `config/sources.yaml`, and `pipeline/quality/schemas.py`.

## Source map

| Source key | Dataset | Problem mapping | Status |
|---|---|---|---|
| `eia930_azps` | `eia930` | APS | live |
| `noaa_phoenix` | `noaa_forecast` | APS | live |
| `noaa_phoenix_obs` | `noaa_obs` | APS | live |
| `blm_sma` | `blm_sma` | Collide A | live |
| `hifld_fiber` | `hifld_fiber` | Collide A | live |
| `nhd_waterbody` | `nhd_waterbody` | Collide A | live |
| `fema_floodplain` | `fema_floodplain` | Collide A | live |
| `pipelines_infra` | `pipelines_infra` | Collide B | live |
| `eia_ng_henry_hub` | `eia_ng` | Collide C | live |
| `eia_ng_waha` | `eia_ng` | Collide C | live |
| `caiso_lmp` | `caiso_lmp` | Collide C | live |
| `eia930_ciso` | `eia930` | Collide context / WECC | live |
| `eia930_erco` | `eia930` | Collide context / ERCOT | live |

That is the full 13-source/problem map currently tracked in the brief context:

- 11 are runnable in this repo
- 2 are known blockers handled by documentation rather than stub code:
  - `ERCOT MIS` requires a developer token from `mis.ercot.com`
  - `PHMSA` bulk files are not fetchable by the current automated path

## Strict check against the pasted master problem statement

Against the exact Collide master problem statement, the repo should be understood as:

- **Directly aligned / implemented**
  - Sub-problem A: `blm_sma`, `hifld_fiber` (public FCC BDC proxy rather than direct HIFLD route geometry), `nhd_waterbody`, `fema_floodplain`
  - Sub-problem C: `caiso_lmp`, `eia_ng_henry_hub`, `eia_ng_waha`
  - Sub-problem B context layer: `pipelines_infra` provides spatial gas-route topology

- **Still missing relative to that exact statement**
  - Sub-problem A: Texas GLO parcel/lease source, zoning, utility territory, county deed/lease-text ingestion
  - Sub-problem B: PHMSA annual reports, PHMSA incidents, EIA-176 / EIA-757
  - Sub-problem C: ERCOT MIS, and any additional WECC BA feeds beyond CAISO

- **Context sources retained from broader APS work, not required by the strict pasted statement**
  - `eia930_azps`
  - `eia930_ciso`
  - `eia930_erco`
  - `noaa_phoenix`
  - `noaa_phoenix_obs`

So if someone says "all 13 sources are from the exact master problem statement," that is not literally true. The accurate statement is: the 13-source set combines strict Collide requirements with APS/context feeds that are still useful for downstream modeling.

## Files that must stay in sync

When adding or removing a source, update all of these together:

1. `pipeline/sources/*.py`
2. `pipeline/registry.py`
3. `pipeline/quality/schemas.py`
4. `config/sources.yaml`
5. `README.md`
6. `tests/`
7. `docs/` if the source has non-obvious semantics or limitations

If any one of those is stale, the branch is not handoff-ready.

## Runtime notes

- `orchestrator/run_once.py` is the safest smoke-test entrypoint for one-off validation.
- `orchestrator/run_live.py` must always close `HttpClient` on shutdown and on exceptions.
- Raw payloads are preserved under `data/raw/`; silver outputs and DuckDB catalog state are reproducible artifacts, not source code.
- `scripts/live_sample.py` is only a convenience preview for currently supported unauthenticated endpoints. It should not advertise blocked sources.

## What not to do

- Do not resurrect `ercot_lmp` placeholders unless a real connector and auth path exist.
- Do not point the repo at unofficial dashboard endpoints just to make a table look complete.
- Do not mark PHMSA as implemented until there is a real loader and a documented input path.
- Do not remove source/problem mapping context from the docs; future agents need that to avoid deleting valid sources as "extra."
