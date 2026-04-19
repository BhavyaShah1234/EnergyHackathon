"""
Power Economics Training Script
================================
Trains two models from real ERCOT RTM + EIA Henry Hub data:

  Model A: Grid price forecaster (GradientBoostingRegressor)
    - Features: lag_1/4/96/672, cyclical hour/dow/month, rolling stats
    - Target: LMP price ($/MWh) — regression
    - Comparison: GBR vs RF vs Ridge — best AUC saved

  Model B: BTM spread durability classifier (RandomForestClassifier)
    - Features: [lmp, gas_price, regime_enc, wind_pct, demand_scale]
    - Target: P(BTM spread > 5 $/MWh) — binary classification
    - Interface matches backend/scoring/power.py exactly

Outputs:
  data/models/power_forecast_cache.pkl   dict: hub → {p10, p50, p90, spread_durability}
  data/models/power_durability.pkl       (model, scaler) tuple

Usage:
  python scripts/training/train_power_economics.py
"""

import subprocess, sys, os, pickle
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

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor, RandomForestClassifier
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score

try:
    from google.colab import drive
    drive.mount('/content/drive', force_remount=False)
    CKPT_DIR = "/content/drive/MyDrive/collide_checkpoints"
    print(f"Drive mounted — checkpoints at {CKPT_DIR}")
except Exception:
    CKPT_DIR = "/tmp/collide_checkpoints"
    print(f"Not on Colab — checkpoints at {CKPT_DIR}")

os.makedirs(CKPT_DIR, exist_ok=True)
MODEL_OUT = Path("data/models")
MODEL_OUT.mkdir(parents=True, exist_ok=True)

DATA_DIR = Path("data/training/distribution_handoff_20260419T091318Z")

HEAT_RATE = 8.5   # MMBtu/MWh — CCGT turbine efficiency
OM_COST   = 3.0   # $/MWh — operations & maintenance
SPREAD_THRESHOLD = 5.0  # $/MWh — BTM is worthwhile above this


def ckpt_path(name):
    return os.path.join(CKPT_DIR, f"pwr_{name}.pkl")

def save_ckpt(name, obj):
    with open(ckpt_path(name), "wb") as f:
        pickle.dump(obj, f)
    print(f"  Checkpoint saved: {name}")

def load_ckpt(name):
    p = ckpt_path(name)
    if os.path.exists(p):
        with open(p, "rb") as f:
            return pickle.load(f)
    return None


# ── 1. Load and preprocess ERCOT RTM data ───────────────────────────────────

print("\n Step 1: Load ERCOT RTM hub prices")

CKPT_ERCOT = load_ckpt("ercot_ts")

if CKPT_ERCOT is None:
    df = pd.read_parquet(DATA_DIR / "ercot_rtm_hub_prices.parquet")
    df['ts'] = pd.to_datetime(df['interval_start_utc'], utc=True)
    df = df.sort_values('ts')

    # Only hub-level settlement points (HB_*) — exclude load zone (LZ_*)
    hubs = [h for h in df['settlement_point_name'].unique() if h.startswith('HB_')]
    df_hubs = df[df['settlement_point_name'].isin(hubs)].copy()

    # Pivot to wide format: one column per hub, indexed by timestamp
    ts_wide = df_hubs.pivot_table(
        index='ts', columns='settlement_point_name',
        values='price_usd_per_mwh', aggfunc='mean'
    )
    ts_wide = ts_wide.sort_index()
    print(f"  Hubs: {list(ts_wide.columns)}")
    print(f"  Rows: {len(ts_wide)}, date range: {ts_wide.index[0]} → {ts_wide.index[-1]}")
    save_ckpt("ercot_ts", ts_wide)
else:
    ts_wide = CKPT_ERCOT
    print(f"  Loaded from checkpoint: {len(ts_wide)} rows, {len(ts_wide.columns)} hubs")


# ── 2. Load EIA Henry Hub gas prices ────────────────────────────────────────

print("\n Step 2: Load EIA Henry Hub gas prices")

CKPT_GAS = load_ckpt("gas_prices")

if CKPT_GAS is None:
    gas_df = pd.read_parquet(DATA_DIR / "eia_ng_henry_hub.parquet")
    gas_df['date'] = pd.to_datetime(gas_df['period_utc']).dt.date
    gas_df = gas_df.groupby('date')['price_usd_per_mmbtu'].mean().reset_index()
    gas_df['date'] = pd.to_datetime(gas_df['date'])
    gas_df = gas_df.sort_values('date')
    print(f"  Gas prices: {len(gas_df)} daily observations")
    print(f"  Price range: ${gas_df['price_usd_per_mmbtu'].min():.2f}–${gas_df['price_usd_per_mmbtu'].max():.2f}/MMBtu")
    save_ckpt("gas_prices", gas_df)
else:
    gas_df = CKPT_GAS
    print(f"  Loaded from checkpoint: {len(gas_df)} rows")


# ── 3. Feature engineering for grid price model ──────────────────────────────

print("\n Step 3: Feature engineering (lag features + cyclical time)")

CKPT_FEATURES = load_ckpt("features")

if CKPT_FEATURES is None:
    # Work with HB_WEST (West Texas — most relevant for BTM data center sites)
    # and HB_BUSAVG (system average) as training targets
    primary_hub = 'HB_WEST'
    series = ts_wide[primary_hub].dropna()

    def make_features(s: pd.Series) -> pd.DataFrame:
        df = pd.DataFrame({'price': s.values}, index=s.index)
        # Lag features (15-min intervals: 4=1h, 96=24h, 672=7d)
        for lag in [1, 4, 16, 96, 192, 672]:
            df[f'lag_{lag}'] = df['price'].shift(lag)
        # Rolling statistics
        df['roll_mean_4']  = df['price'].shift(1).rolling(4).mean()
        df['roll_std_4']   = df['price'].shift(1).rolling(4).std()
        df['roll_mean_96'] = df['price'].shift(1).rolling(96).mean()
        # Cyclical time encodings (prevent boundary effects at midnight/month-end)
        df['hour'] = df.index.hour
        df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
        df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)
        df['dow_sin']  = np.sin(2 * np.pi * df.index.dayofweek / 7)
        df['dow_cos']  = np.cos(2 * np.pi * df.index.dayofweek / 7)
        df['month_sin'] = np.sin(2 * np.pi * (df.index.month - 1) / 12)
        df['month_cos'] = np.cos(2 * np.pi * (df.index.month - 1) / 12)
        return df.dropna()

    feat_df = make_features(series)
    feature_cols = [c for c in feat_df.columns if c != 'price']
    X_all = feat_df[feature_cols].values
    y_all = feat_df['price'].values

    print(f"  Feature matrix: {X_all.shape}, target range: [{y_all.min():.1f}, {y_all.max():.1f}] $/MWh")
    save_ckpt("features", {
        'X': X_all, 'y': y_all, 'cols': feature_cols,
        'ts_index': feat_df.index, 'series': series,
        'primary_hub': primary_hub,
    })
else:
    X_all = CKPT_FEATURES['X']
    y_all = CKPT_FEATURES['y']
    feature_cols = CKPT_FEATURES['cols']
    series = CKPT_FEATURES['series']
    primary_hub = CKPT_FEATURES['primary_hub']
    print(f"  Loaded from checkpoint: {X_all.shape}")


# ── 4. Train and compare grid price models ───────────────────────────────────

print("\n Step 4: Train + compare grid price models (GBR / RF / Ridge)")

CKPT_GRID = load_ckpt("grid_model")

if CKPT_GRID is None:
    # Use last 20% for test (chronological split — no data leakage)
    split = int(len(X_all) * 0.8)
    X_tr, X_te = X_all[:split], X_all[split:]
    y_tr, y_te = y_all[:split], y_all[split:]

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_tr)
    X_te_s  = scaler.transform(X_te)

    candidates = {
        'GBR(n=200,d=5)': GradientBoostingRegressor(
            n_estimators=200, max_depth=5, learning_rate=0.05,
            subsample=0.8, random_state=42
        ),
        'RF(n=300,d=8)': RandomForestRegressor(
            n_estimators=300, max_depth=8, min_samples_leaf=3,
            random_state=42, n_jobs=-1
        ),
        'Ridge': Ridge(alpha=1.0),
    }

    results = {}
    for name, mdl in candidates.items():
        mdl.fit(X_tr_s, y_tr)
        preds = mdl.predict(X_te_s)
        mae = mean_absolute_error(y_te, preds)
        r2  = r2_score(y_te, preds)
        results[name] = {'model': mdl, 'mae': mae, 'r2': r2}
        print(f"  {name:25s}  MAE={mae:.2f} $/MWh  R²={r2:.4f}")

    best_name = min(results, key=lambda k: results[k]['mae'])
    best = results[best_name]
    print(f"\n  Best model: {best_name} (MAE={best['mae']:.2f} $/MWh)")

    # For multi-step iterative forecasting, RF is safer (bounded, no extrapolation).
    # Always save RF alongside the best single-step model.
    rf_result = results['RF(n=300,d=8)']
    save_ckpt("grid_model", {
        'model': best['model'], 'scaler': scaler,
        'feature_cols': feature_cols, 'best_name': best_name,
        'mae': best['mae'], 'r2': best['r2'],
        'forecast_model': rf_result['model'],  # RF for iterative forecast
    })
else:
    print(f"  Loaded from checkpoint: {CKPT_GRID['best_name']} (MAE={CKPT_GRID['mae']:.2f})")


# ── 5. Generate 72h forecast for each hub ────────────────────────────────────
#
# Strategy: seasonal-naive forecast using the winsorized recent 30-day history.
# For each future timestamp, predict = median LMP for that (hour, day-of-week)
# combination in the last 30 days. This avoids iterative compounding errors from
# spike events (e.g., Winter Storm Uri prices at $2,259/MWh in training data).

print("\n Step 5: Generate 72h seasonal-naive forecast per hub")

CKPT_FORECAST = load_ckpt("forecast_cache")

if CKPT_FORECAST is None:
    # Average Henry Hub gas price (last 30 days of data)
    avg_gas = gas_df['price_usd_per_mmbtu'].iloc[-30:].mean()
    btm_cost = avg_gas * HEAT_RATE + OM_COST
    print(f"  Gas price (30d avg): ${avg_gas:.2f}/MMBtu → BTM cost: ${btm_cost:.1f}/MWh")

    forecast_cache = {}
    last_ts_global = ts_wide.index[-1]

    for hub in ts_wide.columns:
        s = ts_wide[hub].dropna()
        if len(s) < 96 * 30:  # need at least 30 days
            # Fall back to using all available data
            recent = s
        else:
            recent = s.iloc[-96 * 30:]  # last 30 days

        # Winsorize at 95th pctile to remove spike influence
        cap = float(recent.quantile(0.95))
        recent_w = recent.clip(upper=cap)

        # Build seasonal profile: median per (hour, dayofweek) in 15-min bins
        profile_df = pd.DataFrame({'price': recent_w.values}, index=recent.index)
        profile_df['hour']  = profile_df.index.hour
        profile_df['dow']   = profile_df.index.dayofweek
        profile_df['slot']  = profile_df.index.hour * 4 + profile_df.index.minute // 15

        # 72h = 288 fifteen-minute intervals
        freq = pd.Timedelta('15min')
        future_timestamps = [last_ts_global + (i + 1) * freq for i in range(288)]

        p50_preds = []
        for ts in future_timestamps:
            slot = ts.hour * 4 + ts.minute // 15
            dow  = ts.dayofweek
            # Try slot+dow match, fall back to slot-only match
            mask = (profile_df['slot'] == slot) & (profile_df['dow'] == dow)
            vals = profile_df.loc[mask, 'price']
            if len(vals) < 3:
                vals = profile_df.loc[profile_df['slot'] == slot, 'price']
            p50_preds.append(float(vals.median()) if len(vals) > 0 else float(recent_w.median()))

        p50 = np.array(p50_preds)
        hist_std = float(recent_w.std())
        p10 = np.maximum(p50 - 1.28 * hist_std, -50.0)
        p90 = p50 + 1.28 * hist_std

        mean_lmp = float(np.mean(p50))
        spread_durability = float(np.mean(p50 > btm_cost))

        forecast_cache[hub] = {
            'p10': p10, 'p50': p50, 'p90': p90,
            'spread_durability': spread_durability,
            'method': 'seasonal_naive_30d',
        }
        print(f"  {hub:12s}: mean LMP={mean_lmp:.1f} $/MWh, spread_durability={spread_durability:.2%}")

    save_ckpt("forecast_cache", forecast_cache)
else:
    forecast_cache = CKPT_FORECAST
    print(f"  Loaded from checkpoint: {len(forecast_cache)} hubs")


# ── 6. Build BTM spread durability dataset ───────────────────────────────────

print("\n Step 6: Build BTM spread durability training dataset")

CKPT_DUR = load_ckpt("durability_dataset")

if CKPT_DUR is None:
    # Merge ERCOT HB_WEST with Henry Hub gas prices by date
    lmp_series = ts_wide['HB_WEST'].dropna().reset_index()
    lmp_series.columns = ['ts', 'lmp']
    # Strip timezone for merge compatibility
    lmp_series['date'] = lmp_series['ts'].dt.tz_convert('US/Central').dt.normalize().dt.tz_localize(None)

    gas_df['date'] = pd.to_datetime(gas_df['date']).dt.tz_localize(None)
    merged = lmp_series.merge(gas_df[['date', 'price_usd_per_mmbtu']], on='date', how='left')
    merged['price_usd_per_mmbtu'] = merged['price_usd_per_mmbtu'].ffill().bfill()

    # BTM spread: if positive, self-generation is profitable
    merged['btm_cost'] = merged['price_usd_per_mmbtu'] * HEAT_RATE + OM_COST
    merged['spread'] = merged['lmp'] - merged['btm_cost']
    merged['label'] = (merged['spread'] > SPREAD_THRESHOLD).astype(int)

    # Regime classification using simple rules:
    # - stress_scarcity: LMP > 75th percentile AND spread > 0
    # - wind_curtailment: LMP < 10 $/MWh (oversupply)
    # - normal: everything else
    p75_lmp = merged['lmp'].quantile(0.75)
    merged['regime'] = 0  # normal
    merged.loc[(merged['lmp'] > p75_lmp) & (merged['spread'] > 0), 'regime'] = 1  # stress_scarcity
    merged.loc[merged['lmp'] < 10.0, 'regime'] = 2  # wind_curtailment

    # Features must match power.py interface exactly:
    # [lmp_mwh, waha_price, regime_enc, wind_pct, demand_scale]
    merged['wind_pct'] = 0.28  # ERCOT avg wind penetration (hardcoded in power.py)
    merged['demand_scale'] = 55.0  # demand_mw/1000 (hardcoded in power.py)

    X_dur = merged[['lmp', 'price_usd_per_mmbtu', 'regime', 'wind_pct', 'demand_scale']].values
    y_dur = merged['label'].values

    pos_rate = y_dur.mean()
    print(f"  Dataset: {len(X_dur)} samples, {pos_rate:.1%} positive (spread > {SPREAD_THRESHOLD} $/MWh)")
    save_ckpt("durability_dataset", {'X': X_dur, 'y': y_dur})
else:
    X_dur = CKPT_DUR['X']
    y_dur = CKPT_DUR['y']
    print(f"  Loaded from checkpoint: {len(X_dur)} samples")


# ── 7. Train spread durability classifier ────────────────────────────────────

print("\n Step 7: Train spread durability classifier")

CKPT_DUR_MODEL = load_ckpt("durability_model")

if CKPT_DUR_MODEL is None:
    X_tr, X_te, y_tr, y_te = train_test_split(X_dur, y_dur, test_size=0.2, random_state=42)

    dur_scaler = StandardScaler()
    X_tr_s = dur_scaler.fit_transform(X_tr)
    X_te_s  = dur_scaler.transform(X_te)

    dur_model = RandomForestClassifier(
        n_estimators=200, max_depth=6, class_weight='balanced',
        random_state=42, n_jobs=-1,
    )
    dur_model.fit(X_tr_s, y_tr)

    auc = roc_auc_score(y_te, dur_model.predict_proba(X_te_s)[:, 1])
    print(f"  Durability model AUC: {auc:.4f}")
    save_ckpt("durability_model", {'model': dur_model, 'scaler': dur_scaler, 'auc': auc})
else:
    dur_model  = CKPT_DUR_MODEL['model']
    dur_scaler = CKPT_DUR_MODEL['scaler']
    print(f"  Loaded from checkpoint (AUC={CKPT_DUR_MODEL['auc']:.4f})")


# ── 8. Save production files ──────────────────────────────────────────────────

print("\n Step 8: Save production model files")

MODEL_OUT.mkdir(parents=True, exist_ok=True)

with open(MODEL_OUT / "power_forecast_cache.pkl", "wb") as f:
    pickle.dump(forecast_cache, f)
print(f"  Saved: data/models/power_forecast_cache.pkl ({len(forecast_cache)} hubs)")

with open(MODEL_OUT / "power_durability.pkl", "wb") as f:
    pickle.dump((dur_model, dur_scaler), f)
print(f"  Saved: data/models/power_durability.pkl")

import shutil
for fname in ["power_forecast_cache.pkl", "power_durability.pkl"]:
    shutil.copy(MODEL_OUT / fname, f"{CKPT_DIR}/{fname}")
print(f"  Backed up to {CKPT_DIR}")

print("\n Power economics training complete!")
print("   backend/scoring/power.py loads these files automatically")
print(f"   Hubs in cache: {list(forecast_cache.keys())}")
