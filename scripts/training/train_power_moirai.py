"""
COLLIDE — Power Economics Forecaster: Moirai-2.0 + Baseline Rule Scorer
=========================================================================
Two-part script:

Part A: Pre-computes a 72-hour BTM spread forecast for each ERCOT/CAISO node
        using Moirai-2.0 (Salesforce/moirai-1.0-R-large from HuggingFace).
        Saves forecast cache to data/models/power_forecast_cache.pkl

Part B: Trains a spread durability estimator — a simple logistic regressor
        that predicts P(spread > 0) from regime + gas price + LMP features.
        Used as the rule-based power scorer fallback.
        Saves to data/models/power_durability.pkl

Google Colab: needs a GPU runtime for Moirai inference (Runtime → Change runtime → T4 GPU).
If GPU is unavailable, Part A falls back to an ARIMA baseline.

Run on Colab:
  !git clone https://github.com/BhavyaShah1234/EnergyHackathon
  %cd EnergyHackathon
  !pip install -q uni2ts transformers datasets accelerate
  !python scripts/training/train_power_moirai.py
"""

import subprocess, sys

def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

def install_if_missing(pkg, import_name=None):
    name = import_name or pkg.split("[")[0].replace("-", "_")
    try:
        __import__(name)
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--no-deps", pkg])

install_if_missing("scikit-learn", "sklearn")
install_if_missing("pandas")
install_if_missing("numpy")
install_if_missing("matplotlib")
install_if_missing("transformers")
install_if_missing("accelerate")

try:
    import uni2ts  # noqa: F401
    MOIRAI_AVAILABLE = True
except ImportError:
    try:
        # --no-deps avoids torch downgrade from uni2ts's torch<2.5 constraint
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "--no-deps", "uni2ts"])
        MOIRAI_AVAILABLE = True
    except Exception:
        MOIRAI_AVAILABLE = False
        print("⚠️  uni2ts not installed — Moirai will be skipped, using ARIMA baseline")

try:
    from google.colab import drive
    drive.mount('/content/drive', force_remount=False)
    CKPT_DIR = "/content/drive/MyDrive/collide_checkpoints"
    print(f"✅ Drive mounted — checkpoints at {CKPT_DIR}")
except Exception:
    CKPT_DIR = "/tmp/collide_checkpoints"
    print(f"⚠️  Not on Colab — checkpoints at {CKPT_DIR}")

import os, pickle, warnings
import numpy as np
import pandas as pd
from pathlib import Path

warnings.filterwarnings('ignore')
os.makedirs(CKPT_DIR, exist_ok=True)
MODEL_OUT = Path("data/models")
MODEL_OUT.mkdir(parents=True, exist_ok=True)

NODES = {
    'HB_WEST':          {'region': 'ERCOT', 'lat': 31.5, 'lon': -102.5},
    'HB_NORTH':         {'region': 'ERCOT', 'lat': 35.0, 'lon': -101.5},
    'HB_SOUTH':         {'region': 'ERCOT', 'lat': 29.5, 'lon': -98.5},
    'PALOVRDE_ASR-APND':{'region': 'CAISO', 'lat': 33.6, 'lon': -114.5},
}

HEAT_RATE = 8.5  # CCGT MMBtu/MWh — must match sub_c.py and power.py
OM_COST   = 3.0  # $/MWh


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


# ═══════════════════════════════════════════════════════════════════════════════
# PART A: 72-Hour LMP Forecast via Moirai-2.0
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("PART A: 72-Hour LMP Forecast (Moirai-2.0)")
print("="*60)


# ── A1. Build/load 90-day historical LMP data ───────────────────────────────

print("\n📊 A1: Build 90-day historical LMP series")

CKPT_LMP_HIST = load_ckpt("lmp_history_90d")

if CKPT_LMP_HIST is None:
    # Load from silver parquet if available
    silver_lmp = Path("data/silver")
    lmp_history = {}

    loaded_from_parquet = False
    for node in NODES:
        parquet_files = list(silver_lmp.glob(f"**/*lmp*{node}*.parquet")) + \
                        list(silver_lmp.glob(f"**/ercot_lmp/*.parquet"))
        if parquet_files:
            try:
                df = pd.concat([pd.read_parquet(f) for f in parquet_files])
                if node in df.columns or 'lmp_mwh' in df.columns:
                    lmp_col = node if node in df.columns else 'lmp_mwh'
                    series = df[lmp_col].dropna().tail(90 * 24).values
                    lmp_history[node] = series
                    loaded_from_parquet = True
            except Exception as e:
                pass

    if not loaded_from_parquet:
        print("  Silver lake LMP data not found — generating synthetic 90-day series")
        np.random.seed(42)

        for node, info in NODES.items():
            # Base price by region
            base = 42.0 if info['region'] == 'ERCOT' else 38.5

            # Synthetic LMP: daily cycle + weekly pattern + noise + occasional spikes
            hours = 90 * 24
            t = np.arange(hours)

            daily_cycle  = 8 * np.sin(2 * np.pi * t / 24 - np.pi / 2)  # peak at 2pm
            weekly_cycle = 3 * np.sin(2 * np.pi * t / (24 * 7))
            noise        = np.random.normal(0, 5, hours)
            spikes       = np.zeros(hours)

            # Add 3 stress events (Uri-style or heat dome)
            for _ in range(3):
                spike_start = np.random.randint(24, hours - 72)
                spike_len   = np.random.randint(12, 48)
                spikes[spike_start:spike_start + spike_len] = np.random.uniform(80, 200)

            # Add 5 wind curtailment events
            for _ in range(5):
                curtail_start = np.random.randint(0, hours - 24)
                curtail_len   = np.random.randint(6, 20)
                spikes[curtail_start:curtail_start + curtail_len] -= np.random.uniform(15, 35)

            series = base + daily_cycle + weekly_cycle + noise + spikes
            series = np.clip(series, -50, 400)
            lmp_history[node] = series.astype(np.float32)

            print(f"  {node}: mean=${series.mean():.1f}, max=${series.max():.0f}, "
                  f"min=${series.min():.0f} (synthetic)")

    save_ckpt("lmp_history_90d", lmp_history)
else:
    lmp_history = CKPT_LMP_HIST
    print(f"  Loaded {len(lmp_history)} node series from checkpoint")


# ── A2. Moirai-2.0 inference ─────────────────────────────────────────────────

print("\n🤖 A2: Moirai-2.0 72-hour forecast inference")

CKPT_FORECAST = load_ckpt("moirai_forecasts")

if CKPT_FORECAST is None:
    forecasts = {}

    if MOIRAI_AVAILABLE:
        print("  Loading Salesforce/moirai-1.0-R-large from HuggingFace...")
        print("  (First run downloads ~1.5GB — subsequent runs use cache)")
        try:
            import torch
            from uni2ts.model.moirai import MoiraiForecast, MoiraiModule

            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"  Using device: {device}")

            # Load pre-trained Moirai-large
            # Use direct constructor (load_from_checkpoint API changed in newer Lightning)
            model = MoiraiForecast(
                module=MoiraiModule.from_pretrained("Salesforce/moirai-1.0-R-large"),
                prediction_length=72,
                context_length=720,  # 30 days of context
                patch_size=32,
                num_samples=100,     # for P10/P50/P90
                target_dim=1,
                feat_dynamic_real_dim=0,
                past_feat_dynamic_real_dim=0,
            )

            save_ckpt("moirai_model_loaded", True)  # mark as loaded

            from gluonts.dataset.pandas import PandasDataset

            model = model.to(device)
            predictor = model.create_predictor(batch_size=32)

            for node, series in lmp_history.items():
                print(f"  Forecasting {node}...")

                # Build a GluonTS-compatible PandasDataset from the last 720h context
                idx = pd.date_range("2020-01-01", periods=720, freq="h")
                df_node = pd.DataFrame({"target": series[-720:].astype(float)}, index=idx)
                ds = PandasDataset(df_node, target="target")

                fc_list = list(predictor.predict(ds))
                samples = fc_list[0].samples  # (num_samples, 72)

                forecasts[node] = {
                    'p10': np.percentile(samples, 10, axis=0),
                    'p50': np.percentile(samples, 50, axis=0),
                    'p90': np.percentile(samples, 90, axis=0),
                    'method': 'moirai-1.0-R-large',
                }
                print(f"    P50 next 24h: ${forecasts[node]['p50'][:24].mean():.1f}/MWh")

        except Exception as e:
            print(f"  Moirai inference failed: {e}")
            print("  Falling back to ARIMA baseline...")
            MOIRAI_AVAILABLE = False

    if not MOIRAI_AVAILABLE:
        print("  Using ARIMA(2,1,2) as fallback forecaster")
        try:
            install("statsmodels")
            from statsmodels.tsa.arima.model import ARIMA

            for node, series in lmp_history.items():
                print(f"  ARIMA forecast for {node}...")
                # Use last 2 weeks for faster fitting
                train = series[-336:]
                try:
                    arima = ARIMA(train, order=(2, 1, 2)).fit()
                    fc = np.asarray(arima.forecast(steps=72))
                    ci = arima.get_forecast(steps=72).conf_int(alpha=0.2)
                    ci = np.asarray(ci)  # works whether conf_int returns DataFrame or ndarray
                    forecasts[node] = {
                        'p10': ci[:, 0],
                        'p50': fc,
                        'p90': ci[:, 1],
                        'method': 'ARIMA(2,1,2)',
                    }
                    print(f"    P50 next 24h: ${fc[:24].mean():.1f}/MWh")
                except Exception as e2:
                    print(f"    ARIMA failed for {node}: {e2} — using rolling mean")
                    mu = train[-168:].mean()
                    forecasts[node] = {
                        'p10': np.full(72, mu * 0.8),
                        'p50': np.full(72, mu),
                        'p90': np.full(72, mu * 1.2),
                        'method': 'rolling_mean',
                    }
        except Exception as e:
            print(f"  ARIMA install failed: {e} — using constant fallback")
            for node, series in lmp_history.items():
                mu = series[-168:].mean()
                forecasts[node] = {
                    'p10': np.full(72, mu * 0.8),
                    'p50': np.full(72, mu),
                    'p90': np.full(72, mu * 1.2),
                    'method': 'constant',
                }

    save_ckpt("moirai_forecasts", forecasts)
else:
    forecasts = CKPT_FORECAST
    print(f"  Loaded forecasts for {len(forecasts)} nodes from checkpoint")
    for node, fc in forecasts.items():
        print(f"  {node}: method={fc['method']}, P50 24h avg=${fc['p50'][:24].mean():.1f}")


# ── A3. Compute BTM spread forecasts ─────────────────────────────────────────

print("\n📉 A3: Compute BTM spread forecasts")

WAHA_PRICE = 1.84  # Use live value from API in production

spread_forecasts = {}
for node, fc in forecasts.items():
    btm_cost = WAHA_PRICE * HEAT_RATE + OM_COST
    spread_forecasts[node] = {
        'p10':             fc['p10'] - btm_cost,
        'p50':             fc['p50'] - btm_cost,
        'p90':             fc['p90'] - btm_cost,
        'btm_cost_mwh':    btm_cost,
        'spread_durability': float((fc['p50'] > 0).mean()),
        'method':          fc['method'],
    }
    print(f"  {node}: spread P50 avg=${spread_forecasts[node]['p50'].mean():.1f}/MWh, "
          f"durability={spread_forecasts[node]['spread_durability']:.1%}")


# ═══════════════════════════════════════════════════════════════════════════════
# PART B: Spread Durability Estimator
# ═══════════════════════════════════════════════════════════════════════════════

print("\n" + "="*60)
print("PART B: Spread Durability Logistic Regressor")
print("="*60)

# Predicts: P(BTM spread > 0) given [lmp_mwh, waha_price, regime_label, wind_pct, demand_mw]
# This is the fast rule-based component used at inference time (no Moirai call needed)

print("\n📊 B1: Build spread durability training set")

CKPT_DUR = load_ckpt("durability_dataset")

if CKPT_DUR is None:
    np.random.seed(99)
    n = 2000

    # Sample ERCOT/CAISO historical conditions
    lmp_mwh    = np.clip(np.random.exponential(45, n), 5, 500)
    waha_price = np.clip(np.random.normal(2.0, 0.8, n), 0.5, 6.0)
    regime     = np.random.choice([0, 1, 2], n, p=[0.70, 0.15, 0.15])
    wind_pct   = np.clip(np.random.normal(0.28, 0.15, n), 0, 0.8)
    demand_mw  = np.clip(np.random.normal(55000, 12000, n), 20000, 85000)

    # True spread durability (fraction of trailing 90d with positive spread)
    # Modelled as: P(spread>0) = sigmoid(lmp_mean - btm_cost - regime_adjustment)
    from scipy.special import expit
    btm_cost  = waha_price * HEAT_RATE + OM_COST
    base_spread = lmp_mwh - btm_cost
    regime_adj = np.where(regime == 1, 20, np.where(regime == 2, -15, 0))
    durability = expit((base_spread + regime_adj) / 15.0)
    durability = np.clip(durability, 0.05, 0.95)

    X_dur = np.column_stack([lmp_mwh, waha_price, regime, wind_pct, demand_mw / 1000])
    y_dur = (durability > 0.5).astype(int)

    print(f"  Dataset: {n} samples, {y_dur.mean():.1%} positive (durable spread)")
    save_ckpt("durability_dataset", {"X": X_dur, "y": y_dur, "durability": durability})
else:
    X_dur      = CKPT_DUR["X"]
    y_dur      = CKPT_DUR["y"]
    durability = CKPT_DUR["durability"]
    print(f"  Loaded {len(X_dur)} samples from checkpoint")

print("\n🔧 B2: Train durability logistic regressor")

from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import cross_val_score

CKPT_DUR_MODEL = load_ckpt("durability_model")

if CKPT_DUR_MODEL is None:
    scaler_dur = StandardScaler()
    X_dur_s = scaler_dur.fit_transform(X_dur)

    lr = LogisticRegression(C=1.0, max_iter=500, random_state=42)
    cv_scores = cross_val_score(lr, X_dur_s, y_dur, cv=5, scoring='roc_auc')
    lr.fit(X_dur_s, y_dur)

    print(f"  Cross-val AUC: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
    save_ckpt("durability_model", {"model": lr, "scaler": scaler_dur})
else:
    lr         = CKPT_DUR_MODEL["model"]
    scaler_dur = CKPT_DUR_MODEL["scaler"]
    print("  Model loaded from checkpoint")


# ── Save all output models ────────────────────────────────────────────────────

print("\n💾 Saving all production model files")

# Forecast cache
with open(MODEL_OUT / "power_forecast_cache.pkl", "wb") as f:
    pickle.dump(spread_forecasts, f)
print(f"  ✅ {MODEL_OUT}/power_forecast_cache.pkl")

# Durability model
with open(MODEL_OUT / "power_durability.pkl", "wb") as f:
    pickle.dump((lr, scaler_dur), f)
print(f"  ✅ {MODEL_OUT}/power_durability.pkl")

# Back up to Drive
import shutil
for fname in ("power_forecast_cache.pkl", "power_durability.pkl"):
    shutil.copy(MODEL_OUT / fname, f"{CKPT_DIR}/{fname}")
print(f"  ✅ Backed up to Drive")

print("\n🎉 Power forecaster training complete!")
print()
print("   Update backend/scoring/power.py to load power_forecast_cache.pkl")
print("   for actual Moirai-derived spread forecasts per node.")
print()
print("   Inference snippet:")
print("   cache = pickle.load(open('data/models/power_forecast_cache.pkl','rb'))")
print("   fc = cache.get(ercot_node, cache['HB_WEST'])")
print("   spread_p50 = fc['p50'][0]  # next hour forecast")
print("   durability = fc['spread_durability']")
