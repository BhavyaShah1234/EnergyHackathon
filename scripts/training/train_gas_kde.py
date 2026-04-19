"""
COLLIDE — Gas Reliability KDE Training Script
===============================================
Trains a Gaussian KDE on PHMSA incident coordinates, weighted by incident severity.
Output: data/models/gas_kde.pkl  (sklearn KernelDensity fitted to incident lat/lon)

Data source: PHMSA Gas Distribution Incident Data (free CSV download)
  URL: https://www.phmsa.dot.gov/data-and-statistics/pipeline/gas-distribution-incident-data
  Download the "Gas Distribution Incidents" CSV — all years.

If you don't have the CSV yet, this script generates a realistic synthetic dataset
based on known Winter Storm Uri (Feb 2021) failure patterns in Texas.

Run on Google Colab:
  !git clone https://github.com/BhavyaShah1234/EnergyHackathon
  %cd EnergyHackathon
  # Optional: upload PHMSA CSV first
  # from google.colab import files; files.upload()
  !python scripts/training/train_gas_kde.py
"""

import subprocess, sys

def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

install("scikit-learn")
install("pandas")
install("numpy")
install("matplotlib")
install("torch")

try:
    from google.colab import drive
    drive.mount('/content/drive', force_remount=False)
    CKPT_DIR = "/content/drive/MyDrive/collide_checkpoints"
    print(f"✅ Drive mounted — checkpoints at {CKPT_DIR}")
except Exception:
    CKPT_DIR = "/tmp/collide_checkpoints"
    print(f"⚠️  Not on Colab — checkpoints at {CKPT_DIR}")

import os, pickle, sys
import numpy as np
import pandas as pd
from pathlib import Path

# Import GPUKernelDensity from the backend module so pickle can resolve it on load
_root = Path(__file__).resolve().parents[2]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
from backend.scoring.gas import GPUKernelDensity

import torch
_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"  Using device: {_DEVICE}")

os.makedirs(CKPT_DIR, exist_ok=True)
MODEL_OUT = Path("data/models")
MODEL_OUT.mkdir(parents=True, exist_ok=True)

PHMSA_CSV_CANDIDATES = [
    "gas_distribution_incidents.csv",
    "phmsa_incidents.csv",
    "/content/gas_distribution_incidents.csv",
    "/content/drive/MyDrive/phmsa_incidents.csv",
]


def ckpt_path(name):
    return os.path.join(CKPT_DIR, f"{name}.pkl")


def save_ckpt(name, obj):
    with open(ckpt_path(name), "wb") as f:
        pickle.dump(obj, f)
    print(f"  💾 Checkpoint saved: {name}")


def load_ckpt(name):
    p = ckpt_path(name)
    if os.path.exists(p):
        with open(p, "rb") as f:
            return pickle.load(f)
    return None


# ── 1. Load PHMSA incident data ─────────────────────────────────────────────

print("\n📊 Step 1: Load PHMSA incident data")

CKPT_INCIDENTS = load_ckpt("phmsa_incidents")

if CKPT_INCIDENTS is None:
    phmsa_df = None
    for path in PHMSA_CSV_CANDIDATES:
        if os.path.exists(path):
            print(f"  Found PHMSA CSV at: {path}")
            try:
                phmsa_df = pd.read_csv(path, low_memory=False)
                print(f"  Loaded {len(phmsa_df):,} incident records")
                break
            except Exception as e:
                print(f"  Failed to read {path}: {e}")

    if phmsa_df is None:
        print("  ⚠️  PHMSA CSV not found — generating synthetic dataset")
        print("       (Based on Winter Storm Uri Feb 2021 + historical TX/NM incident patterns)")

        np.random.seed(42)

        # Winter Storm Uri clusters (Feb 2021 — known gas failures in TX)
        uri_clusters = [
            (32.5, -100.5, 80),   # West Texas Permian (weatherization failures)
            (31.8, -102.2, 60),   # Midland/Odessa corridor
            (29.8, -95.4,  50),   # Houston area (compressor failures)
            (32.8, -97.3,  45),   # DFW Metroplex (freeze-offs)
            (33.6, -101.9, 35),   # Lubbock area
            (31.5, -97.1,  30),   # Waco area
            (30.5, -97.8,  25),   # Austin area
        ]

        # Historical incident clusters (non-Uri, all years)
        hist_clusters = [
            (32.0, -102.1, 120),  # Permian Basin (corrosion, aging infrastructure)
            (29.7, -95.3,  100),  # Houston (dense distribution network)
            (32.8, -97.4,   80),  # DFW (urban excavation damage)
            (29.4, -98.5,   60),  # San Antonio
            (30.3, -97.7,   50),  # Austin metro
            (35.2, -101.8,  40),  # Panhandle TX
            (33.4, -104.5,  30),  # Roswell NM (older distribution)
            (32.4, -104.2,  25),  # Carlsbad NM
        ]

        records = []
        cause_map = {
            0: ('CORROSION', 3.0),
            1: ('MATERIAL_FAILURE', 2.5),
            2: ('EXCAVATION_DAMAGE', 2.0),
            3: ('NATURAL_FORCES', 1.5),
            4: ('OTHER', 1.0),
        }

        for lat_c, lon_c, n in uri_clusters + hist_clusters:
            lats = np.random.normal(lat_c, 0.6, n)
            lons = np.random.normal(lon_c, 0.8, n)
            causes = np.random.randint(0, 5, n)
            for lat, lon, cause_i in zip(lats, lons, causes):
                cause, severity = cause_map[cause_i]
                records.append({
                    'lat': lat, 'lon': lon,
                    'cause': cause, 'severity_weight': severity,
                    'year': np.random.randint(2010, 2025),
                })

        phmsa_df = pd.DataFrame(records)
        print(f"  Generated {len(phmsa_df):,} synthetic incident records")

    # Standardize column names (real PHMSA CSV uses different headers)
    col_map = {
        'LATITUDE':   'lat', 'LONGITUDE': 'lon',
        'Latitude':   'lat', 'Longitude': 'lon',
        'CAUSE':      'cause', 'Cause': 'cause',
    }
    phmsa_df = phmsa_df.rename(columns=col_map)

    # Keep only records with valid lat/lon in TX/NM/AZ bounding box
    if 'lat' in phmsa_df.columns and 'lon' in phmsa_df.columns:
        phmsa_df = phmsa_df.dropna(subset=['lat', 'lon'])
        mask = (
            (phmsa_df['lat'] >= 25.0) & (phmsa_df['lat'] <= 37.5) &
            (phmsa_df['lon'] >= -115.0) & (phmsa_df['lon'] <= -93.0)
        )
        phmsa_df = phmsa_df[mask].copy()
    else:
        print("  ERROR: CSV missing lat/lon columns. Check column names.")
        print(f"  Available columns: {list(phmsa_df.columns)[:10]}")
        sys.exit(1)

    # Severity weights: corrosion incidents are 3× more serious than other causes
    if 'severity_weight' not in phmsa_df.columns:
        cause_col = 'cause' if 'cause' in phmsa_df.columns else phmsa_df.columns[0]
        cause_weights = {
            'CORROSION': 3.0, 'Corrosion': 3.0,
            'MATERIAL_FAILURE': 2.5, 'Material/Weld/Equip Failure': 2.5,
            'EXCAVATION_DAMAGE': 2.0, 'Excavation Damage': 2.0,
            'NATURAL_FORCES': 1.5, 'Natural Force Damage': 1.5,
        }
        phmsa_df['severity_weight'] = phmsa_df.get('cause', 'OTHER').map(cause_weights).fillna(1.0)

    print(f"  Final incident dataset: {len(phmsa_df):,} records in TX/NM/AZ region")
    save_ckpt("phmsa_incidents", phmsa_df)
else:
    phmsa_df = CKPT_INCIDENTS
    print(f"  Loaded {len(phmsa_df):,} incidents from checkpoint")


# ── 2. Fit weighted Gaussian KDE ─────────────────────────────────────────────

print("\n📐 Step 2: Fit Gaussian KDE on incident locations")

CKPT_KDE = load_ckpt("gas_kde_model")

if CKPT_KDE is None:
    coords = phmsa_df[['lat', 'lon']].values
    weights = phmsa_df['severity_weight'].values

    # Normalize weights
    weights_norm = weights / weights.sum()

    # bandwidth=0.5 degrees ≈ 55km — appropriate for regional pipeline reliability
    kde = GPUKernelDensity(bandwidth=0.5)
    kde.fit(coords, sample_weight=weights_norm)

    # Validate: score a known high-risk area (Permian Basin) vs. low-risk
    permian    = kde.score_samples([[31.9973, -102.0779]])[0]  # Midland TX
    low_risk   = kde.score_samples([[36.0,    -108.0]])[0]    # Remote NM desert

    print(f"  KDE log-density at Midland TX (high risk):  {permian:.3f}")
    print(f"  KDE log-density at Remote NM (low risk):    {low_risk:.3f}")
    assert permian > low_risk, "KDE should score Permian higher than remote desert"

    print("  ✅ KDE validation passed")
    save_ckpt("gas_kde_model", kde)
else:
    kde = CKPT_KDE
    print("  KDE loaded from checkpoint")


# ── 3. Build scored evaluation grid (for visualization + fast lookup) ────────

print("\n🗺️  Step 3: Build scored evaluation grid")

CKPT_GRID = load_ckpt("gas_kde_grid")

if CKPT_GRID is None:
    lat_range = np.linspace(25.5, 37.0, 60)
    lon_range = np.linspace(-115.0, -93.0, 80)
    LAT, LON = np.meshgrid(lat_range, lon_range)
    grid_points = np.column_stack([LAT.ravel(), LON.ravel()])

    log_dens = kde.score_samples(grid_points)
    # Normalize to [0, 1] — 0 = high risk (many incidents), 1 = safe
    dens_min, dens_max = log_dens.min(), log_dens.max()
    reliability_score = 1.0 - (log_dens - dens_min) / (dens_max - dens_min + 1e-9)

    grid = pd.DataFrame({
        'lat': grid_points[:, 0],
        'lon': grid_points[:, 1],
        'log_density': log_dens,
        'reliability_score': reliability_score,
    })
    print(f"  Grid: {len(grid):,} points, score range [{reliability_score.min():.3f}, {reliability_score.max():.3f}]")
    save_ckpt("gas_kde_grid", grid)
else:
    grid = CKPT_GRID
    print(f"  Grid loaded from checkpoint ({len(grid):,} points)")


# ── 4. Quick visualization ───────────────────────────────────────────────────

print("\n📈 Step 4: Visualize KDE reliability map")

try:
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))

    # Incident density heatmap
    ax1.scatter(phmsa_df['lon'], phmsa_df['lat'],
                c='red', alpha=0.3, s=5, label='PHMSA incidents')
    ax1.set_xlim(-115, -93); ax1.set_ylim(25.5, 37.0)
    ax1.set_title('PHMSA Incident Locations (TX/NM/AZ)')
    ax1.set_xlabel('Longitude'); ax1.set_ylabel('Latitude')
    ax1.legend()

    # Reliability score heatmap
    sc = ax2.scatter(grid['lon'], grid['lat'],
                     c=grid['reliability_score'], cmap='RdYlGn',
                     s=20, alpha=0.7, vmin=0, vmax=1)
    plt.colorbar(sc, ax=ax2, label='Gas Reliability Score (1=safe, 0=risky)')
    ax2.set_title('Gas Reliability Score (KDE)')
    ax2.set_xlabel('Longitude'); ax2.set_ylabel('Latitude')

    plt.tight_layout()
    fig.savefig(f"{CKPT_DIR}/gas_kde_map.png", dpi=100)
    print(f"  Map saved to {CKPT_DIR}/gas_kde_map.png")
    plt.show()
except Exception as e:
    print(f"  Visualization skipped: {e}")


# ── 5. Save production model ─────────────────────────────────────────────────

print("\n💾 Step 5: Save production KDE model")

with open(MODEL_OUT / "gas_kde.pkl", "wb") as f:
    pickle.dump(kde, f)
print(f"  ✅ Saved: {MODEL_OUT}/gas_kde.pkl")

import shutil
shutil.copy(MODEL_OUT / "gas_kde.pkl", f"{CKPT_DIR}/gas_kde.pkl")
print(f"  ✅ Backed up to Drive")

print("\n🎉 Gas KDE training complete!")
print("   backend/scoring/gas.py loads data/models/gas_kde.pkl automatically")
print()
print("   NOTE: Update backend/features/extractor.py to call kde.score_samples([[lat, lon]])")
print("   and pass the density to score_gas() instead of the fallback phmsa_incident_density")
