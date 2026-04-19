"""
Land & Pipeline Spatial Index Builder
======================================
Precomputes spatial lookup structures from all ingested datasets so that
backend scoring can quickly retrieve proximity features for any (lat, lon).

Datasets used:
  blm_sma             → federal land ownership polygons (TX/AZ/NM)
  glo_upland_leases   → Texas GLO upland lease status + activity type
  glo_oilgas_active   → active oil/gas lease locations (proxy: private, active)
  nhd_waterbody       → USGS water body centroids (nearest water distance)
  usgs_seismic        → earthquake events → per-grid seismic hazard score
  fema_nri_wildfire   → census tract wildfire risk scores (FEMA NRI)
  pipelines_infra     → gas pipeline segments → nearest pipeline distance

Outputs:
  data/models/land_spatial_index.pkl   — dict with KDTree indices + metadata
  data/models/pipeline_index.pkl       — pipeline KDTree for gas scoring

Usage:
  python scripts/training/build_land_spatial_index.py
"""

import subprocess, sys, os, pickle, json
from pathlib import Path

def install_if_missing(pkg, import_name=None):
    name = import_name or pkg.split("[")[0].replace("-", "_")
    try:
        __import__(name)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

install_if_missing("pandas")
install_if_missing("numpy")
install_if_missing("scikit-learn", "sklearn")
install_if_missing("pyarrow")

import numpy as np
import pandas as pd
from scipy.spatial import KDTree

DATA_DIR_1 = Path("data/training/distribution_handoff_20260419T091318Z")
DATA_DIR_2 = Path("data/training/distribution_handoff_20260419T100610Z")
MODEL_OUT = Path("data/models")
MODEL_OUT.mkdir(parents=True, exist_ok=True)


def haversine_km(lat1, lon1, lat2, lon2):
    """Vectorized haversine distance in km."""
    R = 6371.0
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1)) * np.cos(np.radians(lat2)) * np.sin(dlon/2)**2
    return R * 2 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def extract_centroid(geojson_str):
    """Extract centroid (lat, lon) from a GeoJSON or ESRI geometry string. Returns (lat, lon) or (None, None)."""
    try:
        if not geojson_str:
            return None, None
        g = json.loads(geojson_str)
        gtype = g.get('type', '')
        # Standard GeoJSON
        if gtype == 'Point':
            coords = g['coordinates']
            return coords[1], coords[0]
        elif gtype == 'Polygon':
            pts = np.array(g['coordinates'][0])
            return float(pts[:, 1].mean()), float(pts[:, 0].mean())
        elif gtype == 'MultiPolygon':
            all_pts = np.vstack([np.array(ring[0]) for ring in g['coordinates']])
            return float(all_pts[:, 1].mean()), float(all_pts[:, 0].mean())
        # ESRI JSON format: {"rings": [[[lon, lat], ...]]}
        elif 'rings' in g:
            all_pts = np.array(g['rings'][0])
            return float(all_pts[:, 1].mean()), float(all_pts[:, 0].mean())
        elif 'paths' in g:
            all_pts = np.array(g['paths'][0])
            return float(all_pts[:, 1].mean()), float(all_pts[:, 0].mean())
        return None, None
    except Exception:
        return None, None


# ── 1. Water body centroids (NHD) ────────────────────────────────────────────

print("\n Step 1: Build water body KDTree (NHD)")

df_water = pd.read_parquet(DATA_DIR_1 / "nhd_waterbody.parquet")

water_lats, water_lons = [], []
for geojson in df_water['geometry_geojson']:
    lat, lon = extract_centroid(geojson)
    if lat is not None:
        water_lats.append(lat)
        water_lons.append(lon)

water_coords = np.column_stack([water_lats, water_lons])
water_tree = KDTree(water_coords)
print(f"  Water KDTree: {len(water_coords):,} bodies indexed")


# ── 2. Seismic hazard grid (USGS) ────────────────────────────────────────────

print("\n Step 2: Build seismic hazard grid (USGS)")

df_seis = pd.read_parquet(DATA_DIR_2 / "usgs_seismic.parquet")
df_seis = df_seis.dropna(subset=['lat', 'lon'])

# Compute per-grid seismic hazard using KDE-style density:
# Hazard = weighted event density (weight by magnitude)
# Normalize to 0-1 so higher score = more seismic risk
seis_coords = df_seis[['lat', 'lon']].values
seis_mags   = df_seis['mag'].values
seis_tree   = KDTree(seis_coords)

def seismic_hazard_at(lat, lon, radius_km=100.0):
    """Return a 0-1 seismic hazard score: sum of mag weights within radius_km."""
    lat_r = radius_km / 111.0
    candidates = seis_tree.query_ball_point([lat, lon], lat_r)
    if not candidates:
        return 0.0
    mags = seis_mags[candidates]
    # Weight by Richter scale energy: 10^(1.5*mag)
    energy_weights = np.power(10.0, 1.5 * mags)
    raw = float(np.log1p(energy_weights.sum()))
    return raw  # will be normalized globally

# Calibrate normalization using the full dataset
sample_pts = seis_coords[np.random.RandomState(42).choice(len(seis_coords), min(500, len(seis_coords)), replace=False)]
raw_hazards = np.array([seismic_hazard_at(lat, lon) for lat, lon in sample_pts])
seis_max = float(np.percentile(raw_hazards, 99))  # clip to 99th pctile
seis_max = max(seis_max, 1e-6)

print(f"  Seismic events: {len(df_seis):,}, magnitude range: {df_seis['mag'].min():.1f}–{df_seis['mag'].max():.1f}")
print(f"  Seismic hazard normalization max (99th pctile): {seis_max:.2f}")


# ── 3. Wildfire risk by census tract (FEMA NRI) ──────────────────────────────

print("\n Step 3: Build wildfire risk lookup (FEMA NRI)")

wf_parts = []
# Prefer parquet over CSV to avoid loading both
parquet_parts = sorted(DATA_DIR_2.glob("fema_nri_wildfire_part*.parquet"))
if parquet_parts:
    for part_path in parquet_parts:
        try:
            part = pd.read_parquet(part_path)
            if 'wildfire_risk_score' in part.columns:
                cols = [c for c in ['geometry_geojson', 'wildfire_risk_score', 'wildfire_risk_rating', 'state'] if c in part.columns]
                wf_parts.append(part[cols])
                print(f"  Loaded {len(part):,} rows from {part_path.name}")
        except Exception as e:
            print(f"  Skipped {part_path.name}: {e}")
else:
    for part_path in sorted(DATA_DIR_2.glob("fema_nri_wildfire_part*.csv")):
        try:
            part = pd.read_csv(part_path, usecols=['geometry_geojson', 'wildfire_risk_score', 'wildfire_risk_rating', 'state'])
            wf_parts.append(part)
            print(f"  Loaded {len(part):,} rows from {part_path.name}")
        except Exception as e:
            print(f"  Skipped {part_path.name}: {e}")

df_wf = pd.concat(wf_parts, ignore_index=True)
df_wf = df_wf.dropna(subset=['wildfire_risk_score'])

# Normalize wildfire_risk_score to 0-1
wf_max = float(df_wf['wildfire_risk_score'].quantile(0.99))
df_wf['risk_norm'] = (df_wf['wildfire_risk_score'] / max(wf_max, 1e-6)).clip(0, 1)

# Extract centroids for spatial lookup
wf_lats, wf_lons, wf_risks = [], [], []
for _, row in df_wf.iterrows():
    result = extract_centroid(row.get('geometry_geojson', ''))
    if result is None:
        continue
    lat, lon = result
    if lat is not None:
        wf_lats.append(lat)
        wf_lons.append(lon)
        wf_risks.append(row['risk_norm'])

wf_coords = np.column_stack([wf_lats, wf_lons])
wf_risks_arr = np.array(wf_risks)
wf_tree = KDTree(wf_coords)

print(f"  Wildfire KDTree: {len(wf_coords):,} census tracts, risk range 0–{wf_max:.0f}")


# ── 4. Pipeline segments (gas infrastructure) ────────────────────────────────

print("\n Step 4: Build pipeline segment KDTree")

df_pipe = pd.read_parquet(DATA_DIR_1 / "pipelines_infra.parquet")

pipe_lats, pipe_lons, pipe_types, pipe_operators, pipe_statuses = [], [], [], [], []

for _, row in df_pipe.iterrows():
    try:
        g = json.loads(row['geometry_json'])
        paths = g.get('paths', [])
        for path in paths:
            if len(path) == 0:
                continue
            # Use midpoint of each path segment
            pts = np.array(path)
            mid_idx = len(pts) // 2
            lon, lat = pts[mid_idx][0], pts[mid_idx][1]
            if -115 <= lon <= -93 and 25 <= lat <= 37.5:
                pipe_lats.append(lat)
                pipe_lons.append(lon)
                pipe_types.append(row['pipe_type'])
                pipe_operators.append(row['operator'])
                pipe_statuses.append(row['status'])
    except Exception:
        continue

pipe_coords = np.column_stack([pipe_lats, pipe_lons])
pipe_types_arr    = np.array(pipe_types)
pipe_statuses_arr = np.array(pipe_statuses)
pipe_tree = KDTree(pipe_coords)

print(f"  Pipeline KDTree: {len(pipe_coords):,} segment midpoints")
print(f"  Types: {pd.Series(pipe_types_arr).value_counts().to_dict()}")


# ── 5. Land ownership (BLM + GLO) ────────────────────────────────────────────

print("\n Step 5: Index land ownership (BLM + GLO leases)")

df_blm = pd.read_parquet(DATA_DIR_1 / "blm_sma.parquet")
df_glo = pd.read_parquet(DATA_DIR_1 / "glo_upland_leases.parquet")
df_glo_active = pd.read_parquet(DATA_DIR_1 / "glo_oilgas_active.parquet")

# GLO upland leases: have lat/lon directly
glo_lats = pd.to_numeric(df_glo['project_latitude'], errors='coerce')
glo_lons = pd.to_numeric(df_glo['project_longitude'], errors='coerce')
glo_valid = df_glo[(glo_lats.notna()) & (glo_lons.notna())].copy()
glo_valid['lat'] = glo_lats[glo_valid.index]
glo_valid['lon'] = glo_lons[glo_valid.index]

glo_coords = glo_valid[['lat', 'lon']].values
glo_status = glo_valid['lease_status'].values
glo_activity = glo_valid['activity'].values
glo_tree = KDTree(glo_coords) if len(glo_coords) > 0 else None

print(f"  GLO upland: {len(glo_coords):,} leases with coordinates")
print(f"  Status breakdown: {pd.Series(glo_status).value_counts().head(5).to_dict()}")


# ── 6. Assemble and save spatial index ───────────────────────────────────────

print("\n Step 6: Save spatial index files")

land_index = {
    # Water bodies
    'water_tree':   water_tree,
    'water_coords': water_coords,

    # Seismic hazard
    'seis_tree':    seis_tree,
    'seis_coords':  seis_coords,
    'seis_mags':    seis_mags,
    'seis_max':     seis_max,

    # Wildfire risk
    'wf_tree':      wf_tree,
    'wf_coords':    wf_coords,
    'wf_risks':     wf_risks_arr,

    # GLO land ownership
    'glo_tree':     glo_tree,
    'glo_coords':   glo_coords,
    'glo_status':   glo_status,
    'glo_activity': glo_activity,
}

pipeline_index = {
    'pipe_tree':     pipe_tree,
    'pipe_coords':   pipe_coords,
    'pipe_types':    pipe_types_arr,
    'pipe_statuses': pipe_statuses_arr,
}

with open(MODEL_OUT / "land_spatial_index.pkl", "wb") as f:
    pickle.dump(land_index, f)
print(f"  Saved: data/models/land_spatial_index.pkl")

with open(MODEL_OUT / "pipeline_index.pkl", "wb") as f:
    pickle.dump(pipeline_index, f)
print(f"  Saved: data/models/pipeline_index.pkl")


# ── 7. Verify: test lookup for a known TX location ───────────────────────────

print("\n Step 7: Verify spatial lookups (Midland TX: 31.997, -102.078)")

test_lat, test_lon = 31.997, -102.078

# Nearest water body
dist_water_deg, _ = water_tree.query([test_lat, test_lon])
dist_water_km = dist_water_deg * 111.0
print(f"  Nearest water: ~{dist_water_km:.1f} km")

# Pipeline distance
dist_pipe_deg, pipe_idx = pipe_tree.query([test_lat, test_lon])
dist_pipe_km = dist_pipe_deg * 111.0
print(f"  Nearest pipeline: ~{dist_pipe_km:.1f} km ({pipe_types_arr[pipe_idx]})")

# Seismic hazard
raw_seis = seismic_hazard_at(test_lat, test_lon)
norm_seis = min(raw_seis / seis_max, 1.0)
print(f"  Seismic hazard: {norm_seis:.3f}")

# Wildfire risk
if len(wf_coords) > 0:
    _, wf_idx = wf_tree.query([test_lat, test_lon])
    print(f"  Wildfire risk: {wf_risks_arr[wf_idx]:.3f}")
else:
    print("  Wildfire risk: index empty (no valid geometries extracted)")

print("\n Land spatial index build complete!")
print("   Use backend/features/spatial.py to query these indices at inference time")
