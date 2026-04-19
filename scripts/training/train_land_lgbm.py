"""
COLLIDE — Land Scorer LightGBM Training Script
===============================================
Run on Google Colab. Mounts Drive for checkpoint persistence.
Each major step checks for an existing checkpoint before running.

Output: data/models/land_lgbm.pkl  (model + StandardScaler bundled)
        data/models/land_lgbm.shap.pkl  (SHAP TreeExplainer)

Usage on Colab:
  !git clone https://github.com/BhavyaShah1234/EnergyHackathon
  %cd EnergyHackathon
  !python scripts/training/train_land_lgbm.py
"""

# ── 0. Colab setup ──────────────────────────────────────────────────────────

import subprocess, sys

def install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

install("lightgbm")
install("shap")
install("scikit-learn")
install("pandas")
install("numpy")

# Mount Google Drive for checkpoint persistence
try:
    from google.colab import drive
    drive.mount('/content/drive', force_remount=False)
    CKPT_DIR = "/content/drive/MyDrive/collide_checkpoints"
    print(f"✅ Drive mounted — checkpoints at {CKPT_DIR}")
except Exception:
    CKPT_DIR = "/tmp/collide_checkpoints"
    print(f"⚠️  Not on Colab — checkpoints at {CKPT_DIR}")

import os, pickle, hashlib
import numpy as np
import pandas as pd
from pathlib import Path

os.makedirs(CKPT_DIR, exist_ok=True)
MODEL_OUT = Path("data/models")
MODEL_OUT.mkdir(parents=True, exist_ok=True)


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
            obj = pickle.load(f)
        print(f"  ✅ Checkpoint loaded: {name}")
        return obj
    return None


# ── 1. Build training dataset ───────────────────────────────────────────────
#
# Positive class: known TX/AZ/NM data center locations (geocoded lat/lon)
# Negative class: random coordinates that pass hard-filter check
# Features: 10 land features from FeatureVector
#
# If you have the real parquet files in data/silver/, replace the synthetic
# data below with a DuckDB spatial query. The model interface is identical.

print("\n📊 Step 1: Build training dataset")

CKPT_DATA = load_ckpt("land_dataset")

if CKPT_DATA is None:
    np.random.seed(42)

    # Known TX/AZ data center locations (positive class)
    # Sources: VoltaGrid, Oracle, Google, Meta West Texas announcements
    POSITIVE_SITES = [
        # water_km, fiber_km, pipeline_km, substation_km, highway_km,
        # ownership (0=priv,0.5=state,1=fed), fema_zone_score, seismic, wildfire, epa_attainment
        [6.2,  1.8,  0.4,  4.0,  2.5,  1.0, 1.0, 0.05, 0.15, 1.0],  # Permian Basin TX
        [12.1, 4.2,  0.1,  8.0,  5.0,  1.0, 1.0, 0.06, 0.12, 1.0],  # Pecos TX
        [4.3,  6.8,  0.8,  6.0,  4.0,  0.5, 1.0, 0.08, 0.28, 1.0],  # Carlsbad NM
        [9.4,  3.1,  1.2,  5.0,  3.5,  1.0, 1.0, 0.07, 0.18, 1.0],  # Andrews TX
        [3.2,  0.8,  0.6,  3.0,  1.5,  1.0, 0.7, 0.06, 0.14, 1.0],  # Odessa TX
        [5.6,  2.4,  1.8,  9.0,  4.0,  1.0, 1.0, 0.09, 0.22, 1.0],  # Amarillo TX
        [7.8,  5.6,  2.1, 10.0,  6.0,  0.5, 1.0, 0.10, 0.32, 1.0],  # Roswell NM
        [2.1,  1.2,  3.4,  6.0,  2.0,  0.5, 1.0, 0.12, 0.42, 0.0],  # Buckeye AZ
        [4.0,  2.0,  0.5,  4.5,  2.8,  1.0, 1.0, 0.05, 0.16, 1.0],  # Midland TX
        [8.0,  3.5,  1.0,  7.0,  4.5,  1.0, 1.0, 0.08, 0.20, 1.0],  # Lubbock TX
        [5.0,  2.5,  0.8,  5.5,  3.0,  1.0, 1.0, 0.06, 0.18, 1.0],  # Big Spring TX
        [11.0, 5.0,  1.5,  9.0,  5.5,  0.5, 1.0, 0.09, 0.25, 1.0],  # Hobbs NM
        [3.5,  1.5,  0.6,  4.0,  2.2,  1.0, 0.7, 0.07, 0.19, 1.0],  # San Angelo TX
        [6.5,  2.8,  1.1,  6.0,  3.8,  1.0, 1.0, 0.06, 0.17, 1.0],  # Snyder TX
        [9.0,  4.0,  1.4,  8.0,  5.0,  0.3, 1.0, 0.10, 0.35, 1.0],  # Artesia NM
    ]

    # Negative class: known bad locations (flood zones, wilderness, urban, remote)
    NEGATIVE_SITES = [
        [1.0,  0.5, 25.0, 30.0, 20.0, 0.3, 0.0, 0.6, 0.8, 0.0],  # flood zone, no pipeline
        [0.2,  0.1,  0.2, 1.0,   0.5, 0.3, 0.0, 0.8, 0.9, 0.0],  # urban flood
        [25.0, 18.0, 15.0, 20.0, 18.0, 0.3, 0.4, 0.3, 0.7, 0.0],  # remote, high fire
        [8.0,  12.0, 18.0, 22.0, 15.0, 0.3, 1.0, 0.7, 0.8, 0.0],  # seismic + fire
        [20.0, 15.0,  8.0, 18.0, 12.0, 0.3, 0.4, 0.5, 0.6, 0.0],  # far from everything
    ]

    # Augment with random synthetic samples around the seed points
    pos_base = np.array(POSITIVE_SITES)
    neg_base = np.array(NEGATIVE_SITES)

    n_aug = 100
    noise_pos = pos_base[np.random.choice(len(pos_base), n_aug)] + np.random.randn(n_aug, 10) * 0.8
    noise_neg = neg_base[np.random.choice(len(neg_base), n_aug)] + np.random.randn(n_aug, 10) * 1.2
    noise_neg = np.clip(noise_neg, 0, None)
    noise_pos = np.clip(noise_pos, 0, None)

    X = np.vstack([pos_base, noise_pos, neg_base, noise_neg])
    y = np.array(
        [1] * len(pos_base) + [1] * n_aug +
        [0] * len(neg_base) + [0] * n_aug
    )

    # Clip feature ranges to realistic bounds
    X[:, 0]  = np.clip(X[:, 0],  0, 50)   # water_km
    X[:, 1]  = np.clip(X[:, 1],  0, 30)   # fiber_km
    X[:, 2]  = np.clip(X[:, 2],  0, 50)   # pipeline_km
    X[:, 3]  = np.clip(X[:, 3],  0, 60)   # substation_km
    X[:, 4]  = np.clip(X[:, 4],  0, 40)   # highway_km
    X[:, 5]  = np.clip(X[:, 5],  0, 1)    # ownership score
    X[:, 6]  = np.clip(X[:, 6],  0, 1)    # fema zone score
    X[:, 7]  = np.clip(X[:, 7],  0, 1)    # seismic
    X[:, 8]  = np.clip(X[:, 8],  0, 1)    # wildfire
    X[:, 9]  = np.clip(X[:, 9],  0, 1)    # epa attainment

    FEATURE_NAMES = [
        'water_km', 'fiber_km', 'pipeline_km', 'substation_km', 'highway_km',
        'ownership_score', 'fema_score', 'seismic_hazard', 'wildfire_risk', 'epa_attainment',
    ]

    df = pd.DataFrame(X, columns=FEATURE_NAMES)
    df['label'] = y

    print(f"  Dataset: {len(df)} samples, {y.mean():.1%} positive rate")
    save_ckpt("land_dataset", {"X": X, "y": y, "feature_names": FEATURE_NAMES})
else:
    X = CKPT_DATA["X"]
    y = CKPT_DATA["y"]
    FEATURE_NAMES = CKPT_DATA["feature_names"]
    print(f"  Dataset: {len(X)} samples loaded from checkpoint")


# ── 2. Train/test split + scale ─────────────────────────────────────────────

print("\n🔀 Step 2: Split and scale")

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

CKPT_SPLIT = load_ckpt("land_split")

if CKPT_SPLIT is None:
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s  = scaler.transform(X_test)
    print(f"  Train: {len(X_train)}, Test: {len(X_test)}")
    save_ckpt("land_split", {
        "X_train": X_train, "X_test": X_test,
        "y_train": y_train, "y_test": y_test,
        "X_train_s": X_train_s, "X_test_s": X_test_s,
        "scaler": scaler,
    })
else:
    X_train_s = CKPT_SPLIT["X_train_s"]
    X_test_s  = CKPT_SPLIT["X_test_s"]
    y_train   = CKPT_SPLIT["y_train"]
    y_test    = CKPT_SPLIT["y_test"]
    scaler    = CKPT_SPLIT["scaler"]
    print("  Split loaded from checkpoint")


# ── 3. Train LightGBM ───────────────────────────────────────────────────────

print("\n🌲 Step 3: Train LightGBM classifier")

import lightgbm as lgb
from sklearn.metrics import roc_auc_score, classification_report

CKPT_MODEL = load_ckpt("land_lgbm_model")

if CKPT_MODEL is None:
    params = {
        "objective":       "binary",
        "metric":          "auc",
        "learning_rate":   0.05,
        "num_leaves":      15,
        "min_child_samples": 5,
        "n_estimators":    300,
        "subsample":       0.8,
        "colsample_bytree": 0.8,
        "random_state":    42,
        "verbose":         -1,
        "device":          "gpu",
    }
    model = lgb.LGBMClassifier(**params)
    model.fit(
        X_train_s, y_train,
        eval_set=[(X_test_s, y_test)],
        callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(50)],
    )
    auc = roc_auc_score(y_test, model.predict_proba(X_test_s)[:, 1])
    print(f"  Test AUC: {auc:.4f}")
    print(classification_report(y_test, model.predict(X_test_s), target_names=["bad", "good"]))
    save_ckpt("land_lgbm_model", {"model": model, "auc": auc})
else:
    model = CKPT_MODEL["model"]
    print(f"  Model loaded from checkpoint (AUC={CKPT_MODEL['auc']:.4f})")


# ── 4. SHAP explainer ───────────────────────────────────────────────────────

print("\n🔍 Step 4: Compute SHAP explainer")

import shap

CKPT_SHAP = load_ckpt("land_shap_explainer")

if CKPT_SHAP is None:
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_test_s)
    # For binary classifier lgbm returns list[array]; take class-1 values
    if isinstance(shap_values, list):
        sv = shap_values[1]
    else:
        sv = shap_values

    print("  Top feature importances by mean |SHAP|:")
    mean_abs = np.abs(sv).mean(axis=0)
    for name, importance in sorted(zip(FEATURE_NAMES, mean_abs), key=lambda x: -x[1]):
        print(f"    {name:25s}: {importance:.4f}")

    save_ckpt("land_shap_explainer", {"explainer": explainer, "shap_values": sv})
else:
    explainer = CKPT_SHAP["explainer"]
    print("  SHAP explainer loaded from checkpoint")


# ── 5. Save final models ────────────────────────────────────────────────────

print("\n💾 Step 5: Save production model files")

MODEL_OUT.mkdir(parents=True, exist_ok=True)

with open(MODEL_OUT / "land_lgbm.pkl", "wb") as f:
    pickle.dump((model, scaler), f)
print(f"  ✅ Saved: {MODEL_OUT}/land_lgbm.pkl")

with open(MODEL_OUT / "land_lgbm.shap.pkl", "wb") as f:
    pickle.dump(explainer, f)
print(f"  ✅ Saved: {MODEL_OUT}/land_lgbm.shap.pkl")

# Also copy to Drive for safekeeping
import shutil
shutil.copy(MODEL_OUT / "land_lgbm.pkl",      f"{CKPT_DIR}/land_lgbm.pkl")
shutil.copy(MODEL_OUT / "land_lgbm.shap.pkl", f"{CKPT_DIR}/land_lgbm.shap.pkl")
print(f"  ✅ Backed up to Drive checkpoint dir")

print("\n🎉 Land scorer training complete!")
print("   Load in backend: backend/scoring/land.py checks data/models/land_lgbm.pkl automatically")
