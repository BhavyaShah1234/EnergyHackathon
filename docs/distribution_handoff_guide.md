# Distribution Handoff Guide

This guide explains the files in:

- `data/training/distribution_handoff_20260419T091318Z/`

The goal of this handoff is simple:

- give downstream model work a broad real-data package for the chart items
- say clearly what each file means in plain English
- say what is still missing

This handoff focuses on these chart items:

- `legal document`
- `water body prox`
- `distance to nearest pipeline`
- `history fuel prices`
- `history grid prices`

We intentionally did **not** rely on:

- fiber optics
- seismic
- wildfire

`flood zone` was attempted, but the FEMA service failed during export, so it is not present in the final package.

## What Is In The Folder

### `blm_sma.csv` and `blm_sma.parquet`

Rows: `129`

This file supports the chart item `legal document`.

What each row means:

- one BLM land-ownership/status record in AZ, NM, or TX

What the fields mean:

- `object_id`: the source record id
- `sma_id`: the surface-management-agency code id
- `admin_department`: high-level department code
- `admin_agency`: agency code
- `admin_state`: state code
- `admin_unit_name`: land-management unit name when present
- `admin_unit_type`: type of unit when present
- `shape_area_sq_deg`: area of the polygon in source map units

Plain-English meaning:

- this tells us who broadly controls the land
- it helps answer “what kind of land-control situation is this?”
- this is not a full parcel deed file

Important limitation:

- to keep the service stable, this export uses ownership attributes only
- it does not include the full polygon geometry

### `glo_upland_leases.csv` and `glo_upland_leases.parquet`

Rows: `1,545`

This file supports the chart item `legal document`.

What each row means:

- one Texas GLO upland lease record

What the fields mean:

- `lease_number`: the lease id
- `lease_status`: whether the lease is active/inactive
- `activity`: what the lease is for
- `primary_lessee`: main lessee
- `all_lessee`: all named lessees
- `total_consideration`: money amount tied to the lease
- `project_latitude`, `project_longitude`: project coordinates
- `project_name`, `project_number`: source project ids
- `purposeclass`: category of lease purpose
- `gloid`: GLO identifier
- `geometry_geojson`: map geometry for the lease feature

Plain-English meaning:

- this tells us there is a real Texas lease record here
- it tells us who leased it, what it is for, and whether it is active

### `glo_oilgas_active.csv` and `glo_oilgas_active.parquet`

Rows: `7,320`

This file supports the chart item `legal document`.

What each row means:

- one active Texas oil and gas lease record

What the fields mean:

- `lease_number`: lease id
- `lease_status`: current lease status
- `lease_status_date`: date of that status
- `effective_date`: lease start date
- `primary_term_end_date`: end of primary term
- `original_gross_acres`: original acreage
- `current_net_acres`: current net acreage
- `lease_type`: type of lease
- `original_lessee`: original lessee
- `lessor`: owner/lessor
- `county`: county name
- `lease_royalty_gas`, `lease_royalty_oil`: royalty terms
- `land_type`: land-type code
- `first_well_class`: first production class
- `lease_update`: last source update
- `geometry_geojson`: map geometry

Plain-English meaning:

- this is active lease history and structure
- it helps answer “is this place already tied up in active lease arrangements?”

### `glo_oilgas_inactive.csv` and `glo_oilgas_inactive.parquet`

Rows: `12,061`

This file also supports the chart item `legal document`.

What each row means:

- one inactive or terminated Texas oil and gas lease record

Why it matters:

- this gives historical lease churn
- it helps show what used to be leased, not just what is leased right now

The field meanings are the same general idea as the active lease file.

### `nhd_waterbody.csv` and `nhd_waterbody.parquet`

Rows: `59,106`

This file supports the chart item `water body prox`.

What each row means:

- one mapped waterbody from the national hydrography dataset

What the fields mean:

- `object_id`: source id
- `gnis_name`: waterbody name when available
- `feature_type`: type such as lake/reservoir/pond class
- `feature_code`: numeric source code
- `area_sq_km`: mapped area in square kilometers
- `reach_code`: hydrography reach code
- `geometry_geojson`: waterbody map geometry

Plain-English meaning:

- this tells us where the water is
- downstream can compute distance from a candidate site to the nearest waterbody

### `pipelines_infra.csv` and `pipelines_infra.parquet`

Rows: `15,958`

This file supports the chart item `distance to nearest pipeline`.

What each row means:

- one gas pipeline segment in the Southwest/ERCOT study area

What the fields mean:

- `pipeline_id`: segment id
- `pipe_type`: interstate or intrastate
- `operator`: pipeline operator name
- `status`: operating/proposed/etc.
- `geometry_json`: line geometry for the segment

Plain-English meaning:

- this tells us where pipelines are
- downstream can compute distance from a coordinate to the nearest pipeline segment

Important limitation:

- this is pipeline location and operator context
- this is **not** leak history or reliability history by itself

### `eia930.csv` and `eia930.parquet`

Rows: `104,459`

This file supports the chart item `history grid prices` indirectly by providing grid-condition context.

What each row means:

- one hourly balancing-authority record from EIA-930

What the fields mean:

- `period_utc`: hour
- `respondent`: balancing authority code (`AZPS`, `CISO`, `ERCO`)
- `respondent_name`: balancing authority name
- `type`: record type
- `type_name`: human-readable type name
- `value_mw`: value in megawatts

What the types mean:

- `D`: demand
- `DF`: day-ahead demand forecast
- `NG`: net generation
- `TI`: total interchange

Plain-English meaning:

- this tells us how the grid was behaving hour by hour
- it is not the market price itself
- it is useful context around price behavior

### `eia_ng_henry_hub.csv` and `eia_ng_henry_hub.parquet`

Rows: `241`

This file supports the chart item `history fuel prices`.

What each row means:

- one daily Henry Hub gas price record

What the fields mean:

- `period_utc`: day
- `series`: source series id
- `series_description`: source description
- `price_usd_per_mmbtu`: gas price in dollars per MMBtu

Plain-English meaning:

- this gives daily gas-price history
- right now it is Henry Hub only

Important limitation:

- Waha did not land
- for Texas/Southwest gas-fired economics, that missing Waha history still matters

### `caiso_lmp.csv` and `caiso_lmp.parquet`

Rows: `103,656`

This file supports the chart item `history grid prices`.

What each row means:

- one CAISO 5-minute market-price record

What the fields mean:

- `interval_start_utc`, `interval_end_utc`: 5-minute interval
- `node`: trading node / hub
- `lmp_component`: price component
- `price_usd_per_mwh`: price in dollars per MWh

What the price components mean:

- `LMP`: total locational marginal price
- `MCC`: congestion piece
- `MCE`: energy piece
- `MCL`: loss piece

Plain-English meaning:

- this is real Western market price history
- it gives downstream real price movement over time at key nodes

### `ercot_dam_hub_prices.csv` and `ercot_dam_hub_prices.parquet`

Rows: `88,536`

This file supports the chart item `history grid prices`.

What each row means:

- one ERCOT day-ahead market record for a hub or load zone

What the fields mean:

- `delivery_date_local`: market day in ERCOT local time
- `hour_ending`: market hour
- `repeated_hour_flag`: daylight-savings repeated-hour marker
- `settlement_point`: hub/load-zone name
- `price_usd_per_mwh`: day-ahead settlement point price
- `interval_start_utc`: normalized UTC timestamp
- `report_friendly_name`: source ERCOT archive name

Plain-English meaning:

- this is historical Texas day-ahead price history
- it tells what ERCOT expected those hub/load-zone prices to be before real-time delivery

### `ercot_rtm_hub_prices.csv` and `ercot_rtm_hub_prices.parquet`

Rows: `520,800`

This file supports the chart item `history grid prices`.

What each row means:

- one ERCOT real-time 15-minute market record for a hub or load zone

What the fields mean:

- `delivery_date_local`: market day in ERCOT local time
- `delivery_hour`: hour number
- `delivery_interval`: 15-minute interval number
- `repeated_hour_flag`: daylight-savings repeated-hour marker
- `settlement_point_name`: hub/load-zone name
- `settlement_point_type`: type code
- `price_usd_per_mwh`: real-time settlement point price
- `interval_start_utc`: normalized UTC timestamp
- `report_friendly_name`: source ERCOT archive name

Plain-English meaning:

- this is historical Texas real-time price history
- this is the strongest single price-history file in the handoff

## What Is Missing

### `flood zone`

We attempted FEMA NFHL.

Status:

- not present in the final package
- the FEMA service returned server-side `500` errors during export

Meaning:

- flood was not included in the pushed handoff package

### `history pipeline leakage reports`

Expected source:

- PHMSA incident files

Status:

- missing

Reason:

- official published zip URL returned `403` during automation

### `history operator reports`

Expected source:

- PHMSA annual report data

Status:

- missing

Reason:

- official published bulk path returned `403` during automation

### `history pipeline throughput`

Expected source:

- EIA-176 / EIA-757

Status:

- missing

Reason:

- direct company-level bulk export path still needs to be wired

### `history fuel prices` gap

Expected source:

- Henry Hub + Waha

Status:

- Henry Hub present
- Waha missing

Reason:

- current EIA series/path setup did not return real Waha spot history

## Bottom Line For Teammates

If you are using this folder:

- use `glo_*` and `blm_sma` for the chart item `legal document`
- use `nhd_waterbody` for the chart item `water body prox`
- use `pipelines_infra` for the chart item `distance to nearest pipeline`
- use `eia_ng_henry_hub` for the currently available part of `history fuel prices`
- use `caiso_lmp`, `ercot_dam_hub_prices`, and `ercot_rtm_hub_prices` for `history grid prices`
- use `eia930` as extra grid-condition context

Do **not** assume this folder already contains:

- flood-zone data
- PHMSA leak history
- PHMSA operator annual reports
- EIA-176 / EIA-757 throughput history
- Waha fuel-price history
