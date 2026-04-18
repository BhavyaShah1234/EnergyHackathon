# collide-energy-pipeline

Live data ingestion for the Collide AI-for-Energy hackathon (2026-04-18). Pulls grid, market, weather, and gas data from the public APIs listed in the APS and Collide problem briefs, validates it, and lands it in a partitioned lake ready for downstream modeling (feeder load forecasting, BTM gas-vs-grid LMP spread, siting, scenario stress tests).

**Pipeline-only** — models, dashboards, and scenario code live in sibling repos/branches so teammates can work in parallel.

## Source coverage vs. the briefs

| Source | Required by | Status |
|---|---|---|
| EIA-930 hourly BA (AZPS, CISO, ERCO) | APS + Collide context | ✅ implemented |
| EIA NG spot — Henry Hub, Waha | Collide sub-C | ✅ implemented (needs `EIA_API_KEY`) |
| CAISO OASIS 5-min LMP (Palo Verde, SP15, NP15) | Collide sub-C | ✅ implemented + verified live |
| NOAA NWS forecast + KPHX observations | APS | ✅ implemented + verified live |
| ERCOT MIS (LMP, DAM, fuel-mix, outages) | Collide sub-C | ⏸ pending developer token from mis.ercot.com |
| PHMSA Annual Report + Incident DB | Collide sub-B | ⏸ static bulk, not yet loaded |
| EIA-176 / EIA-757 | Collide sub-B | ⏸ static bulk, not yet loaded |
| BLM GLO / Texas GLO, HIFLD fiber, EPA/NHD | Collide sub-A | ⏸ static geospatial, not yet loaded |
| Pecan Street, NREL SMART-DS / NSRDB / EVI-Pro / EVI-DiST, IEEE feeders | APS | ⏸ static, not yet loaded |

---

## What this pipeline guarantees

| Guarantee | How |
|---|---|
| **No corrupted rows downstream** | Every record passes a pandera schema; schema violations are quarantined, never dropped silently. |
| **Data diversity** | Every modeled quantity has ≥2 independent sources named in the hackathon briefs (AZPS demand via EIA-930; LMP via CAISO OASIS + EIA NG spot for fuel cost; weather via NOAA forecast + KPHX obs). |
| **Idempotent writes** | Natural keys per dataset; re-running the same window is a no-op. |
| **Provenance on every row** | `_source`, `_fetched_at_utc`, `_request_id`, `_payload_sha256` columns let you trace any prediction back to the exact API response. |
| **"Why is this row gone?"** | Append-only `data/_meta/audit/YYYY-MM-DD.jsonl` logs every fetch and validation outcome. `lineage` DuckDB table maps every silver row to the `request_id` that produced it and the one that superseded it. `scripts/explain.py` resolves any natural key → full fetch history + raw payload path. |
| **Tamper-evident silver** | `data/_meta/manifest.json` holds SHA256 of every silver parquet, refreshed on every write. `scripts/verify_integrity.py` re-hashes and reports missing/modified files (exit 1 if drift). |
| **Fail loud, never quiet** | Freshness SLA per source; failing runs write status=fail to the run ledger (DuckDB) and to the per-run JSON DQ report. |
| **Secrets never touch git** | `.env` is gitignored; `.env.example` documents every required key. |
| **UTC everywhere** | All timestamps normalized to `datetime64[ns, UTC]` at ingest. |

## Layout

```
pipeline/
  base.py          HTTP client (retry, backoff, rate-limit, cache), provenance injector
  storage.py       raw → bronze → silver parquet, DuckDB catalog
  quality/
    schemas.py     pandera schemas per dataset
    checks.py      freshness, null-rate, range, dup-rate, schema-drift checks
    report.py      per-run JSON DQ report written to data/_meta/runs/
  sources/
    eia930.py      hourly BA demand/forecast/netgen/interchange (AZPS, CISO, ERCO)
    eia_ng.py      Henry Hub + Waha daily spot   (requires EIA_API_KEY)
    caiso.py       OASIS 5-min LMP (PRC_LMP) at Palo Verde + SP15 + NP15
    noaa.py        api.weather.gov Phoenix forecast + KPHX observations
    # ERCOT MIS: pending — proper mis.ercot.com access needs a developer token.
  registry.py      dataset catalog: schema, cadence, owner, SLA
orchestrator/
  run_once.py      one-shot backfill or catch-up
  run_live.py      continuous (APScheduler) runner
config/
  sources.yaml     endpoints, facets, polling cadence, freshness SLA
data/
  raw/             untouched API responses (JSON/CSV), partitioned by source/date
  bronze/          parsed + typed, one parquet per source/date
  silver/          joined + feature-ready tables for downstream ML
  quarantine/      rows that failed validation, with reason
  _meta/
    catalog.duckdb       silver views + run_ledger + lineage tables
    manifest.json        SHA256 of every silver file (tamper detection)
    audit/YYYY-MM-DD.jsonl  append-only log of every fetch + validation
    runs/*.json          per-run DQ reports
```

### Answering "what happened to this row?"

```bash
# Every fetch that ever touched (period=2026-04-18T15, respondent=AZPS, type=D)
python scripts/explain.py --dataset eia930 \
  --key '{"period_utc":"2026-04-18 15:00:00+00:00","respondent":"AZPS","type":"D"}'

# Has anyone mutated silver outside the pipeline?
python scripts/verify_integrity.py

# All failed runs in the last 24h
duckdb data/_meta/catalog.duckdb \
  "SELECT run_id,dataset,source,error FROM run_ledger WHERE status='fail' AND started_at_utc > now() - INTERVAL 1 DAY"
```

## Getting started (teammates)

```bash
git clone <repo>
cd collide-energy-pipeline
cp .env.example .env              # fill EIA_API_KEY at minimum
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# One-shot catch-up for the last 48h across all live sources
python -m orchestrator.run_once --since 48h

# Continuous runner (polls per config/sources.yaml cadence)
python -m orchestrator.run_live

# Inspect what landed
python scripts/catalog.py         # prints dataset → rows, freshness, last run
duckdb data/_meta/catalog.duckdb  # ad-hoc SQL over the lake
```

### Colab

```python
!git clone <repo> && cd collide-energy-pipeline && pip install -q -r requirements.txt
import os; os.environ["EIA_API_KEY"] = "..."; os.environ["DATA_ROOT"] = "/content/drive/MyDrive/collide/data"
!python -m orchestrator.run_once --since 48h
```

## For downstream teammates

- **Modelers:** read from `data/silver/*.parquet`. Every file has a stable schema (see `pipeline/quality/schemas.py`). Filter by `_fetched_at_utc` for point-in-time training to avoid leakage.
- **Scenario / what-if:** silver tables are tidy enough to feed OpenDSS or a TFT directly. Join keys are documented in `pipeline/registry.py`.
- **Dashboard:** `data/_meta/catalog.duckdb` is the single source of truth — query it, don't re-read parquets.

## Adding a new source

1. Add entry to `config/sources.yaml` (endpoint, cadence, freshness SLA, natural key).
2. Add pandera schema to `pipeline/quality/schemas.py`.
3. Implement `pipeline/sources/<name>.py` subclassing `BaseIngestor`.
4. Register in `pipeline/registry.py`.
5. `pytest tests/test_<name>.py` — a smoke test against a recorded fixture ships with every source.

## Safety checklist (enforced in CI, not just docs)

- [ ] No secrets in git history (`git log -p | grep -iE 'api[_-]?key|secret'` returns nothing)
- [ ] Every dataset in the registry has a schema + freshness SLA
- [ ] `run_once` is idempotent (running twice produces identical silver tables)
- [ ] Raw responses are retained for 7 days (audit trail)
- [ ] Quarantine rate < 1% per source per day (alerts otherwise)
