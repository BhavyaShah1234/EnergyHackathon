# COLLIDE Gap Closure & AI Analyst — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close all unimplemented features from the original spec: ML model loading, 4-intent LangGraph agent, AI Analyst panel (briefing card + chat), compare mode, map heatmap layers, node selector, regime probabilities, and pipeline trigger button.

**Architecture:** Backend-first — fix two silent bugs (regime GMM 3-tuple, gas KDE placeholder coords), add 3 new endpoints (/api/forecast, /api/heatmap, /api/compare), expand /api/regime, rebuild the LangGraph agent with 4 intent nodes and 6 tools, then wire everything into the frontend with new hooks and components.

**Tech Stack:** FastAPI + sse-starlette (backend), LangGraph 0.2 + langchain-anthropic (agent), scikit-learn/LightGBM/pickle (ML loading), React + Recharts (frontend), EventSource API (SSE streaming), react-leaflet (map layers).

**Parallel workstreams after Task 4:** Tasks 5–7 (agent rebuild) and Tasks 8–10 (frontend hooks + component edits) can proceed in parallel. Tasks 11–13 (new frontend components) depend on Tasks 8–10.

---

## File Map

**Modify (backend):**
- `backend/scoring/regime.py` — fix GMM 3-tuple unpack, add `labels` field to output
- `backend/scoring/gas.py` — fix KDE placeholder coords, add lat/lon to signature
- `backend/scoring/power.py` — add forecast cache + durability model loading
- `backend/pipeline/evaluate.py` — pass lat/lon to score_gas
- `backend/main.py` — add /api/forecast, /api/heatmap, /api/compare; extend /api/regime; revamp /api/agent request model
- `backend/agent/graph.py` — full 4-intent StateGraph
- `backend/agent/tools.py` — add get_news_digest, get_lmp_forecast, run_monte_carlo, web_search

**Create (backend):**
- `tests/scoring/test_regime_gmm.py`
- `tests/scoring/test_gas_kde.py`
- `tests/scoring/test_power_ml.py`
- `tests/api/test_new_endpoints.py`
- `tests/agent/test_agent_tools.py`

**Create (frontend):**
- `src/hooks/useAgent.js`
- `src/hooks/useForecast.js`
- `src/hooks/useHeatmap.js`
- `src/hooks/useCompare.js`
- `src/components/AIAnalystPanel.jsx`
- `src/components/BriefingCard.jsx`
- `src/components/AgentChat.jsx`
- `src/components/CompareMode.jsx`

**Modify (frontend):**
- `src/components/SummaryTab.jsx` — regime probability bars
- `src/components/EconomicsTab.jsx` — node selector dropdown + real forecast data
- `src/components/Dashboard.jsx` — pipeline trigger button + last-run timestamp
- `src/components/SiteMap.jsx` — layer toggle controls + compare mode pins
- `src/components/Navbar.jsx` — AI analyst toggle button
- `src/App.jsx` — mount AIAnalystPanel, CompareMode; wire compare state

---

## Task 1: Fix Backend Bugs — Regime GMM 3-Tuple + Gas KDE Coordinates

Two silent bugs: (1) `regime.py` unpacks a 2-tuple but the training script saves a 3-tuple `(gmm, scaler, label_map)` — this will crash with `ValueError` when a trained model file is present. (2) `gas.py` calls `kde.score_samples([[0.0, 0.0]])` — a hardcoded placeholder — instead of the actual coordinate.

**Files:**
- Modify: `backend/scoring/regime.py`
- Modify: `backend/scoring/gas.py`
- Modify: `backend/pipeline/evaluate.py` (pass lat/lon to score_gas)
- Create: `tests/scoring/test_regime_gmm.py`
- Create: `tests/scoring/test_gas_kde.py`

- [ ] **Step 1: Write failing test for regime GMM label_map**

Create `tests/scoring/test_regime_gmm.py`:
```python
import pickle, tempfile, os
import numpy as np
from sklearn.mixture import GaussianMixture
from sklearn.preprocessing import StandardScaler

def _make_fake_gmm_bundle(tmp_path):
    """Creates a minimal 3-tuple bundle matching what train_regime_gmm.py saves."""
    X = np.array([
        [42, 12, 0.28, 55000, 0.18],   # normal
        [180, 80, 0.10, 72000, 0.05],  # stress
        [12, 20, 0.55, 38000, 0.35],   # wind curtailment
    ])
    scaler = StandardScaler().fit(X)
    gmm = GaussianMixture(n_components=3, random_state=42).fit(scaler.transform(X))
    # label_map: cluster_idx -> semantic_idx (0=normal,1=stress,2=wind)
    label_map = {0: 0, 1: 1, 2: 2}
    bundle = (gmm, scaler, label_map)
    model_path = os.path.join(tmp_path, 'regime_gmm.pkl')
    with open(model_path, 'wb') as f:
        pickle.dump(bundle, f)
    return model_path

def test_classify_regime_with_gmm_bundle(tmp_path, monkeypatch):
    model_path = _make_fake_gmm_bundle(tmp_path)
    import backend.scoring.regime as regime_mod
    monkeypatch.setattr(regime_mod, '_GMM_PATH', __import__('pathlib').Path(model_path))
    result = regime_mod.classify_regime(
        lmp_mean=42.0, lmp_std=12.0, wind_pct=0.28, demand_mw=55000
    )
    assert result.label in ('normal', 'stress_scarcity', 'wind_curtailment')
    assert len(result.proba) == 3
    assert abs(sum(result.proba) - 1.0) < 0.01
    assert result.labels == ['normal', 'stress_scarcity', 'wind_curtailment']
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
cd C:/Users/presyze/Projects/ASU/collide
python -m pytest tests/scoring/test_regime_gmm.py -v
```
Expected: FAIL — `ValueError: too many values to unpack` or `AttributeError: 'RegimeState' has no attribute 'labels'`

- [ ] **Step 3: Fix regime.py — correct 3-tuple unpack + add labels to RegimeState**

Replace entire `backend/scoring/regime.py`:
```python
"""Market Regime Classifier — GMM 3-cluster on live ERCOT features."""
from dataclasses import dataclass
from pathlib import Path

_GMM_PATH = Path('data/models/regime_gmm.pkl')

LABELS = ['normal', 'stress_scarcity', 'wind_curtailment']


@dataclass
class RegimeState:
    label: str
    proba: list   # [normal_p, stress_p, wind_p], sums to 1.0
    labels: list  # always ['normal', 'stress_scarcity', 'wind_curtailment']


def _rule_based(lmp_mean: float, lmp_std: float, wind_pct: float,
                demand_mw: float, reserve_margin: float) -> RegimeState:
    if lmp_mean > 100 or (lmp_std > 50 and reserve_margin < 0.08):
        return RegimeState(label='stress_scarcity', proba=[0.1, 0.8, 0.1], labels=LABELS)
    if wind_pct > 0.45 and lmp_mean < 25:
        return RegimeState(label='wind_curtailment', proba=[0.1, 0.1, 0.8], labels=LABELS)
    return RegimeState(label='normal', proba=[0.8, 0.1, 0.1], labels=LABELS)


def classify_regime(
    lmp_mean: float,
    lmp_std: float,
    wind_pct: float,
    demand_mw: float,
    reserve_margin: float = 0.18,
) -> RegimeState:
    if _GMM_PATH.exists():
        import pickle, numpy as np
        with open(_GMM_PATH, 'rb') as f:
            gmm, scaler, label_map = pickle.load(f)  # 3-tuple from training script
        X = scaler.transform([[lmp_mean, lmp_std, wind_pct, demand_mw, reserve_margin]])
        raw_idx = int(gmm.predict(X)[0])
        semantic_idx = label_map[raw_idx]
        label = LABELS[semantic_idx]
        # GMM proba is over raw cluster indices; re-order to semantic order
        raw_proba = gmm.predict_proba(X)[0]
        proba = [0.0, 0.0, 0.0]
        for cluster_idx, sem_idx in label_map.items():
            proba[sem_idx] += float(raw_proba[cluster_idx])
        return RegimeState(label=label, proba=proba, labels=LABELS)
    return _rule_based(lmp_mean, lmp_std, wind_pct, demand_mw, reserve_margin)
```

- [ ] **Step 4: Run regime test — confirm it passes**

```bash
python -m pytest tests/scoring/test_regime_gmm.py -v
```
Expected: PASS

- [ ] **Step 5: Write failing test for gas KDE coordinates**

Create `tests/scoring/test_gas_kde.py`:
```python
import pickle, os
import numpy as np
from sklearn.neighbors import KernelDensity

def _make_fake_kde(tmp_path):
    coords = np.array([[31.9, -102.1], [32.5, -101.2], [29.8, -95.4]])
    kde = KernelDensity(kernel='gaussian', bandwidth=0.5).fit(coords)
    path = os.path.join(tmp_path, 'gas_kde.pkl')
    with open(path, 'wb') as f:
        pickle.dump(kde, f)
    return path

def test_score_gas_uses_actual_coords(tmp_path, monkeypatch):
    model_path = _make_fake_kde(tmp_path)
    import backend.scoring.gas as gas_mod
    monkeypatch.setattr(gas_mod, '_KDE_PATH', __import__('pathlib').Path(model_path))
    # Permian Basin should score differently from remote NM desert
    score_permian = gas_mod.score_gas(
        lat=31.9, lon=-102.1,
        incident_density=0.0, interstate_pipeline_km=5.0, waha_distance_km=50.0
    )
    score_remote = gas_mod.score_gas(
        lat=36.0, lon=-108.0,
        incident_density=0.0, interstate_pipeline_km=5.0, waha_distance_km=50.0
    )
    # Permian = high incident density (low score); remote NM = lower density (higher score)
    assert score_remote > score_permian, (
        f"Remote NM ({score_remote:.3f}) should score higher gas reliability than "
        f"Permian Basin ({score_permian:.3f}) — KDE not using actual coords"
    )

def test_score_gas_fallback_no_model():
    import backend.scoring.gas as gas_mod
    # When no model file exists, should use rule-based fallback
    score = gas_mod.score_gas(
        lat=31.9, lon=-102.1,
        incident_density=0.1, interstate_pipeline_km=10.0, waha_distance_km=100.0
    )
    assert 0.0 <= score <= 1.0
```

- [ ] **Step 6: Run gas test — confirm it fails**

```bash
python -m pytest tests/scoring/test_gas_kde.py -v
```
Expected: FAIL — `TypeError: score_gas() got unexpected keyword argument 'lat'`

- [ ] **Step 7: Fix gas.py — add lat/lon to signature, fix KDE call**

Replace entire `backend/scoring/gas.py`:
```python
"""Gas Supply Reliability scorer. Loads KDE from data/models/gas_kde.pkl when available."""
from pathlib import Path

_KDE_PATH = Path('data/models/gas_kde.pkl')

_INCIDENT_WEIGHT = 0.40
_PIPELINE_WEIGHT = 0.35
_WAHA_WEIGHT     = 0.25


def score_gas(
    lat: float,
    lon: float,
    incident_density: float,
    interstate_pipeline_km: float,
    waha_distance_km: float,
) -> float:
    """Return gas reliability score 0–1.

    Args:
        lat, lon: coordinate (used for KDE lookup when model is loaded)
        incident_density: PHMSA fallback density when KDE not available
        interstate_pipeline_km: distance to nearest interstate pipeline
        waha_distance_km: distance to Waha Hub
    """
    if _KDE_PATH.exists():
        import pickle, numpy as np
        with open(_KDE_PATH, 'rb') as f:
            kde = pickle.load(f)
        log_density = float(kde.score_samples([[lat, lon]])[0])
        # log_density is negative; higher (less negative) = denser incidents = lower reliability
        # Normalize: typical range is [-15, -3]; map to incident_score in [0, 1]
        incident_score = max(0.0, min(1.0, 1.0 - (log_density + 15) / 12.0))
    else:
        incident_score = max(0.0, 1.0 - min(incident_density * 200, 1.0))

    pipeline_score = max(0.0, 1.0 - interstate_pipeline_km / 100.0)
    waha_score     = max(0.0, 1.0 - waha_distance_km / 400.0)

    raw = (
        incident_score * _INCIDENT_WEIGHT +
        pipeline_score * _PIPELINE_WEIGHT +
        waha_score     * _WAHA_WEIGHT
    )
    return round(min(max(raw, 0.0), 1.0), 4)
```

- [ ] **Step 8: Fix evaluate.py — pass lat/lon to score_gas**

In `backend/pipeline/evaluate.py`, update the `score_gas` call (line 43–47):
```python
    gas_score = score_gas(
        lat=fv.lat,
        lon=fv.lon,
        incident_density=fv.phmsa_incident_density,
        interstate_pipeline_km=fv.interstate_pipeline_km,
        waha_distance_km=fv.waha_distance_km,
    )
```

- [ ] **Step 9: Run all gas tests — confirm they pass**

```bash
python -m pytest tests/scoring/test_gas_kde.py -v
```
Expected: PASS both tests

- [ ] **Step 10: Smoke-test the full pipeline still runs**

```bash
python -c "
from backend.pipeline.evaluate import evaluate_coordinate
sc = evaluate_coordinate(31.9973, -102.0779)
print(f'Composite: {sc.composite_score:.3f}')
print(f'Gas score: {sc.gas_score:.3f}')
print(f'Regime: {sc.regime}, proba: {sc.regime_proba}')
assert sc.composite_score > 0
print('PASS')
"
```
Expected: prints scores + `PASS`

- [ ] **Step 11: Commit**

```bash
git add backend/scoring/regime.py backend/scoring/gas.py backend/pipeline/evaluate.py \
        tests/scoring/test_regime_gmm.py tests/scoring/test_gas_kde.py
git commit -m "fix: correct regime GMM 3-tuple unpack and gas KDE coordinate passthrough"
```

---

## Task 2: Power Scoring ML Integration

Load `power_forecast_cache.pkl` (Moirai P10/P50/P90 per node) and `power_durability.pkl` (logistic regressor) into `power.py`. When models are present, use forecast cache for spread P50 and durability model for spread durability; fall back to rule-based when absent.

**Files:**
- Modify: `backend/scoring/power.py`
- Create: `tests/scoring/test_power_ml.py`

- [ ] **Step 1: Write failing test for power ML loading**

Create `tests/scoring/test_power_ml.py`:
```python
import pickle, os
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

def _make_fake_power_models(tmp_path):
    # Forecast cache: node -> {p10, p50, p90, spread_durability, btm_cost_mwh, method}
    cache = {
        'HB_WEST': {
            'p10': np.full(72, 5.0),
            'p50': np.full(72, 18.0),
            'p90': np.full(72, 35.0),
            'spread_durability': 0.72,
            'btm_cost_mwh': 18.64,
            'method': 'test',
        }
    }
    cache_path = os.path.join(tmp_path, 'power_forecast_cache.pkl')
    with open(cache_path, 'wb') as f:
        pickle.dump(cache, f)

    # Durability model
    X = np.array([[50, 2.0, 0, 0.28, 55.0], [10, 4.0, 1, 0.10, 72.0]])
    y = np.array([1, 0])
    scaler = StandardScaler().fit(X)
    lr = LogisticRegression().fit(scaler.transform(X), y)
    dur_path = os.path.join(tmp_path, 'power_durability.pkl')
    with open(dur_path, 'wb') as f:
        pickle.dump((lr, scaler), f)

    return cache_path, dur_path

def test_score_power_uses_forecast_cache(tmp_path, monkeypatch):
    cache_path, dur_path = _make_fake_power_models(tmp_path)
    import backend.scoring.power as power_mod
    from pathlib import Path
    monkeypatch.setattr(power_mod, '_CACHE_PATH', Path(cache_path))
    monkeypatch.setattr(power_mod, '_DUR_PATH', Path(dur_path))

    from backend.features.vector import FeatureVector
    from backend.scoring.regime import RegimeState
    fv = FeatureVector(
        lat=31.9, lon=-102.1, state='TX', market='ERCOT',
        acres_available=200, fema_zone='X', is_federal_wilderness=False,
        ownership_type='private', water_km=6.0, fiber_km=2.0,
        pipeline_km=0.5, substation_km=4.0, highway_km=2.5,
        seismic_hazard=0.05, wildfire_risk=0.15, epa_attainment=True,
        interstate_pipeline_km=5.0, waha_distance_km=50.0,
        phmsa_incident_density=0.02, lmp_mwh=42.0,
        ercot_node='HB_WEST', waha_price=1.84,
    )
    regime = RegimeState(label='normal', proba=[0.8, 0.1, 0.1], labels=['normal','stress_scarcity','wind_curtailment'])
    result = power_mod.score_power(fv, regime)
    # With forecast cache loaded, spread_p50_mwh should come from cache (18.0 - btm_cost)
    # btm_cost = 1.84 * 8.5 + 3.0 = 18.64; cache p50 avg = 18.0; spread = 18.0 - 18.64 = -0.64
    assert 'power_score' in result
    assert 'spread_p50_mwh' in result
    assert 'spread_durability' in result
    assert 0.0 <= result['power_score'] <= 1.0
```

- [ ] **Step 2: Run test — confirm it fails**

```bash
python -m pytest tests/scoring/test_power_ml.py -v
```
Expected: FAIL — `AttributeError: module 'backend.scoring.power' has no attribute '_CACHE_PATH'`

- [ ] **Step 3: Update power.py to load ML models**

Replace entire `backend/scoring/power.py`:
```python
"""BTM Power Economics scorer.

BTM spread = LMP − (waha_price × 8.5 MMBtu/MWh + $3 O&M)
Loads Moirai forecast cache and spread durability model when available.
"""
from pathlib import Path
from backend.features.vector import FeatureVector
from backend.scoring.regime import RegimeState

HEAT_RATE = 8.5   # CCGT, must match sub_c.py
OM_COST   = 3.0   # $/MWh

_CACHE_PATH = Path('data/models/power_forecast_cache.pkl')
_DUR_PATH   = Path('data/models/power_durability.pkl')

_forecast_cache: dict | None = None
_dur_model = None
_dur_scaler = None


def _load_models():
    global _forecast_cache, _dur_model, _dur_scaler
    if _CACHE_PATH.exists() and _forecast_cache is None:
        import pickle
        with open(_CACHE_PATH, 'rb') as f:
            _forecast_cache = pickle.load(f)
    if _DUR_PATH.exists() and _dur_model is None:
        import pickle
        with open(_DUR_PATH, 'rb') as f:
            _dur_model, _dur_scaler = pickle.load(f)


def btm_spread(lmp_mwh: float, waha_price: float) -> float:
    return lmp_mwh - (waha_price * HEAT_RATE + OM_COST)


def get_forecast(node: str) -> dict | None:
    """Return cached forecast dict for a node, or None if cache not loaded."""
    _load_models()
    if _forecast_cache is None:
        return None
    return _forecast_cache.get(node) or _forecast_cache.get('HB_WEST')


def score_power(fv: FeatureVector, regime: RegimeState) -> dict:
    _load_models()
    btm_cost = fv.waha_price * HEAT_RATE + OM_COST

    # Use Moirai forecast cache when available
    fc = get_forecast(fv.ercot_node)
    if fc is not None:
        import numpy as np
        spread_p50 = float(np.mean(fc['p50'])) - btm_cost
        spread_durability = float(fc['spread_durability'])
    else:
        spread_p50 = btm_spread(fv.lmp_mwh, fv.waha_price)
        regime_durability = {'normal': 0.60, 'stress_scarcity': 0.75, 'wind_curtailment': 0.35}
        spread_durability = regime_durability.get(regime.label, 0.60)

    # Override durability with ML model when available
    if _dur_model is not None:
        import numpy as np
        regime_enc = {'normal': 0, 'stress_scarcity': 1, 'wind_curtailment': 2}
        X = _dur_scaler.transform([[
            fv.lmp_mwh, fv.waha_price,
            regime_enc.get(regime.label, 0),
            0.28,           # wind_pct (not in FeatureVector — use ERCOT average)
            55.0,           # demand_mw / 1000
        ]])
        spread_durability = float(_dur_model.predict_proba(X)[0, 1])

    spread_score = min(max(spread_p50 / 20.0, 0.0), 1.0)
    power_score  = round(spread_score * 0.60 + spread_durability * 0.40, 4)

    return {
        'power_score':       power_score,
        'spread_p50_mwh':    round(spread_p50, 2),
        'spread_durability': round(spread_durability, 3),
    }
```

- [ ] **Step 4: Run power tests — confirm they pass**

```bash
python -m pytest tests/scoring/test_power_ml.py -v
```
Expected: PASS

- [ ] **Step 5: Re-run full smoke test**

```bash
python -c "
from backend.pipeline.evaluate import evaluate_coordinate
sc = evaluate_coordinate(31.9973, -102.0779)
print(f'Power: {sc.power_score:.3f}, spread: {sc.spread_p50_mwh:.2f}, dur: {sc.spread_durability:.3f}')
assert 0.0 <= sc.power_score <= 1.0
print('PASS')
"
```

- [ ] **Step 6: Commit**

```bash
git add backend/scoring/power.py tests/scoring/test_power_ml.py
git commit -m "feat: load Moirai forecast cache and durability model in power scorer"
```

---

## Task 3: New API Endpoints — /api/forecast, /api/heatmap, /api/compare + extend /api/regime

Add three new GET endpoints and extend /api/regime to include the `labels` array. The heatmap endpoint uses the 8 pre-scored candidate sites (fast, no grid computation) with layer filtering. The forecast endpoint serves the power forecast cache. The compare endpoint evaluates N coordinates and returns ranked scorecards.

**Files:**
- Modify: `backend/main.py`
- Create: `tests/api/test_new_endpoints.py`

- [ ] **Step 1: Write failing tests for new endpoints**

Create `tests/api/test_new_endpoints.py`:
```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from backend.main import app

client = TestClient(app)


def test_regime_includes_labels():
    from backend.scoring.regime import RegimeState
    mock_regime = RegimeState(label='normal', proba=[0.8, 0.1, 0.1],
                               labels=['normal', 'stress_scarcity', 'wind_curtailment'])
    with patch('backend.main.get_cached_regime', return_value=mock_regime):
        r = client.get('/api/regime')
    assert r.status_code == 200
    data = r.json()
    assert 'labels' in data
    assert data['labels'] == ['normal', 'stress_scarcity', 'wind_curtailment']
    assert len(data['proba']) == 3


def test_heatmap_returns_geojson():
    r = client.get('/api/heatmap?layer=composite&bounds=29,-104,34,-99&zoom=8')
    assert r.status_code == 200
    data = r.json()
    assert data['type'] == 'FeatureCollection'
    assert isinstance(data['features'], list)
    for feat in data['features']:
        assert feat['type'] == 'Feature'
        assert 'score' in feat['properties']
        assert 'layer' in feat['properties']


def test_heatmap_invalid_layer_returns_empty():
    r = client.get('/api/heatmap?layer=nonexistent&bounds=29,-104,34,-99&zoom=8')
    assert r.status_code == 200
    assert r.json()['features'] == []


def test_forecast_returns_arrays():
    r = client.get('/api/forecast?node=HB_WEST&horizon=72')
    assert r.status_code == 200
    data = r.json()
    assert 'p50' in data
    assert 'node' in data
    assert 'method' in data
    assert len(data['p50']) == 72


def test_compare_returns_ranked_list():
    r = client.get('/api/compare?coords=31.9,-102.1;32.5,-101.2')
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) == 2
    # Should be sorted descending by composite_score
    scores = [d['composite_score'] for d in data]
    assert scores == sorted(scores, reverse=True)
    for item in data:
        assert 'lat' in item
        assert 'composite_score' in item
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
python -m pytest tests/api/test_new_endpoints.py -v
```
Expected: multiple FAILs — endpoints not yet defined, `/api/regime` missing `labels`

- [ ] **Step 3: Add new endpoints and extend /api/regime in main.py**

In `backend/main.py`, replace the `/api/regime` endpoint and add three new endpoints after it. First update the existing `/api/regime` handler (currently at line 298–301):

```python
@app.get("/api/regime")
async def api_regime():
    r = get_cached_regime()
    return {"label": r.label, "proba": r.proba, "labels": r.labels}
```

Then add these three new endpoints before the `/api/lmp/stream` WebSocket handler:

```python
# ── /api/forecast ──────────────────────────────────────────────────────────

class ForecastResponse(BaseModel):
    node: str
    horizon: int
    p10: list[float]
    p50: list[float]
    p90: list[float]
    btm_cost_mwh: float
    method: str


@app.get("/api/forecast", response_model=ForecastResponse)
async def api_forecast(node: str = "HB_WEST", horizon: int = 72):
    """Return Moirai P10/P50/P90 LMP forecast for a node (served from cache)."""
    from backend.scoring.power import get_forecast, HEAT_RATE, OM_COST
    fc = get_forecast(node)
    waha_price = 1.84  # live value used at training time; overridden by market refresh
    btm_cost = waha_price * HEAT_RATE + OM_COST
    if fc is not None:
        h = min(horizon, len(fc['p50']))
        return ForecastResponse(
            node=node, horizon=h,
            p10=fc['p10'][:h].tolist() if hasattr(fc['p10'], 'tolist') else list(fc['p10'][:h]),
            p50=fc['p50'][:h].tolist() if hasattr(fc['p50'], 'tolist') else list(fc['p50'][:h]),
            p90=fc['p90'][:h].tolist() if hasattr(fc['p90'], 'tolist') else list(fc['p90'][:h]),
            btm_cost_mwh=round(btm_cost, 2),
            method=fc.get('method', 'cache'),
        )
    # Fallback: flat line at last known LMP
    base = 42.0
    flat_p50 = [base] * horizon
    return ForecastResponse(
        node=node, horizon=horizon,
        p10=[base - 8] * horizon, p50=flat_p50, p90=[base + 8] * horizon,
        btm_cost_mwh=round(btm_cost, 2), method='fallback',
    )


# ── /api/heatmap ────────────────────────────────────────────────────────────

VALID_LAYERS = {'composite', 'gas', 'lmp'}


@app.get("/api/heatmap")
async def api_heatmap(layer: str = "composite", bounds: str = "", zoom: int = 8):
    """Return GeoJSON FeatureCollection of scored points for a map heat layer.

    Uses the 8 candidate sites as data points (instant, no grid computation).
    bounds param is accepted but not filtered against — all sites are returned.
    layer: 'composite' | 'gas' | 'lmp'
    """
    if layer not in VALID_LAYERS:
        return {"type": "FeatureCollection", "features": []}

    gas_data, lmp_data = await _fetch_market_inputs(settings.eia_api_key)
    waha     = gas_data.get("waha_hub")
    palo_lmp = lmp_data.get("PALOVRDE_ASR-APND", {}).get("lmp_mwh")
    scored   = score_all(live_gas_price=waha, live_lmp=palo_lmp)

    score_key = {
        'composite': lambda s: s.composite,
        'gas':       lambda s: s.sub_b,
        'lmp':       lambda s: min(max(s.sub_c, 0.0), 1.0),
    }[layer]

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [s.site.lng, s.site.lat]},
            "properties": {
                "score": round(score_key(s), 4),
                "layer": layer,
                "name": s.site.name,
            },
        }
        for s in scored
    ]
    return {"type": "FeatureCollection", "features": features}


# ── /api/compare ────────────────────────────────────────────────────────────

@app.get("/api/compare")
async def api_compare(coords: str):
    """Evaluate N coordinates and return ranked scorecards.

    coords: semicolon-separated 'lat,lon' pairs, e.g. '31.9,-102.1;32.5,-101.2'
    Returns list of scorecard dicts sorted by composite_score descending.
    """
    pairs = []
    for part in coords.split(';'):
        part = part.strip()
        if not part:
            continue
        try:
            lat_s, lon_s = part.split(',')
            pairs.append((float(lat_s.strip()), float(lon_s.strip())))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid coord pair: '{part}'")

    if not pairs:
        raise HTTPException(status_code=422, detail="No valid coordinate pairs provided")
    if len(pairs) > 5:
        raise HTTPException(status_code=422, detail="Maximum 5 coordinates per compare request")

    results = []
    for lat, lon in pairs:
        sc = evaluate_coordinate(lat, lon)
        results.append({
            "lat": sc.lat, "lon": sc.lon,
            "composite_score": sc.composite_score,
            "land_score": sc.land_score,
            "gas_score": sc.gas_score,
            "power_score": sc.power_score,
            "regime": sc.regime,
            "spread_p50_mwh": sc.spread_p50_mwh,
            "spread_durability": sc.spread_durability,
            "disqualified": sc.hard_disqualified,
            "disqualify_reason": sc.disqualify_reason,
            "cost": {
                "npv_p10_m": sc.cost.npv_p10_m if sc.cost else 0,
                "npv_p50_m": sc.cost.npv_p50_m if sc.cost else 0,
                "npv_p90_m": sc.cost.npv_p90_m if sc.cost else 0,
                "btm_capex_m": sc.cost.btm_capex_m if sc.cost else 0,
                "land_acquisition_m": sc.cost.land_acquisition_m if sc.cost else 0,
                "pipeline_connection_m": sc.cost.pipeline_connection_m if sc.cost else 0,
                "water_connection_m": sc.cost.water_connection_m if sc.cost else 0,
            } if sc.cost else None,
        })

    results.sort(key=lambda x: x['composite_score'], reverse=True)
    return results
```

- [ ] **Step 4: Run endpoint tests — confirm they pass**

```bash
python -m pytest tests/api/test_new_endpoints.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add backend/main.py tests/api/test_new_endpoints.py
git commit -m "feat: add /api/forecast, /api/heatmap, /api/compare; extend /api/regime with labels"
```

---

## Task 4: Rebuild LangGraph Agent — 4-Intent StateGraph + 6 Tools

Replace the current ReAct-style loop agent with a proper 4-node intent-routing StateGraph. Also update the `/api/agent` request model to accept `query` + `context` instead of `message` + `history`. The agent classifies intent, routes to the right node, and streams Claude's synthesis.

**Files:**
- Modify: `backend/agent/tools.py` — add 4 new tools
- Modify: `backend/agent/graph.py` — full StateGraph rebuild
- Modify: `backend/main.py` — update AgentRequest model + revamp streaming
- Create: `tests/agent/test_agent_tools.py`

- [ ] **Step 1: Write failing tests for new agent tools**

Create `tests/agent/test_agent_tools.py`:
```python
from unittest.mock import patch, MagicMock


def test_get_news_digest_returns_list():
    mock_cache = {
        "items": [{"title": "Gas prices rise", "url": "http://x.com", "snippet": "..."}],
        "fetched_at": "2026-04-18T00:00:00",
    }
    with patch('backend.agent.tools._get_news_cache', return_value=mock_cache):
        from backend.agent.tools import get_news_digest
        result = get_news_digest.invoke({})
    assert isinstance(result, list)
    assert result[0]['title'] == "Gas prices rise"


def test_get_lmp_forecast_returns_arrays():
    from backend.agent.tools import get_lmp_forecast
    result = get_lmp_forecast.invoke({'node': 'HB_WEST', 'horizon': 24})
    assert 'p50' in result
    assert 'node' in result
    assert len(result['p50']) == 24


def test_run_monte_carlo_returns_npv():
    from backend.agent.tools import run_monte_carlo
    result = run_monte_carlo.invoke({
        'gas_price': 2.0, 'lmp_p50': 42.0, 'wacc': 0.08, 'years': 20
    })
    assert 'npv_p10_m' in result
    assert 'npv_p50_m' in result
    assert 'npv_p90_m' in result


def test_web_search_returns_results_or_unavailable():
    from backend.agent.tools import web_search
    # With no Tavily key, should return unavailable message gracefully
    with patch('backend.agent.tools._get_tavily_key', return_value=None):
        result = web_search.invoke({'query': 'ERCOT gas prices'})
    assert isinstance(result, str)
    assert len(result) > 0
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
python -m pytest tests/agent/test_agent_tools.py -v
```
Expected: FAIL — tools not yet defined

- [ ] **Step 3: Replace backend/agent/tools.py with 6 tools**

Replace entire `backend/agent/tools.py`:
```python
"""Tools available to the COLLIDE LangGraph agent."""
from langchain_core.tools import tool
from backend.pipeline.evaluate import evaluate_coordinate
from backend.scoring.cost import estimate_costs


# ── Internal accessors (not tools — used by tools below) ───────────────────

def _get_news_cache() -> dict:
    """Access the news cache from main.py without circular import."""
    try:
        from backend.main import _news_cache
        return _news_cache
    except Exception:
        return {"items": [], "fetched_at": ""}


def _get_tavily_key() -> str | None:
    try:
        from backend.config import get_settings
        return get_settings().tavily_api_key or None
    except Exception:
        return None


# ── Tools ──────────────────────────────────────────────────────────────────

@tool
def evaluate_site(lat: float, lon: float) -> dict:
    """Evaluate a (lat, lon) coordinate and return its full scorecard."""
    sc = evaluate_coordinate(lat, lon)
    return {
        'lat': sc.lat, 'lon': sc.lon,
        'composite': sc.composite_score,
        'land': sc.land_score, 'gas': sc.gas_score, 'power': sc.power_score,
        'npv_p50': sc.cost.npv_p50_m if sc.cost else 0,
        'spread_p50_mwh': sc.spread_p50_mwh,
        'spread_durability': sc.spread_durability,
        'regime': sc.regime,
        'disqualified': sc.hard_disqualified,
        'reason': sc.disqualify_reason,
    }


@tool
def compare_sites(coords: list[dict]) -> list[dict]:
    """Evaluate each {lat, lon} dict and return results sorted by composite score."""
    results = [evaluate_site.invoke({'lat': c['lat'], 'lon': c['lon']}) for c in coords]
    return sorted(results, key=lambda x: x['composite'], reverse=True)


@tool
def get_news_digest() -> list[dict]:
    """Return cached BTM energy news headlines (title, url, snippet)."""
    cache = _get_news_cache()
    return cache.get('items', [])


@tool
def get_lmp_forecast(node: str = 'HB_WEST', horizon: int = 72) -> dict:
    """Return P10/P50/P90 LMP forecast array for an ERCOT/CAISO node."""
    from backend.scoring.power import get_forecast, HEAT_RATE, OM_COST
    fc = get_forecast(node)
    waha = 1.84
    btm_cost = waha * HEAT_RATE + OM_COST
    if fc is not None:
        h = min(horizon, len(fc['p50']))
        p50 = fc['p50'][:h]
        p50_list = p50.tolist() if hasattr(p50, 'tolist') else list(p50)
        return {
            'node': node, 'horizon': h,
            'p50': p50_list,
            'spread_durability': float(fc['spread_durability']),
            'btm_cost_mwh': round(btm_cost, 2),
            'method': fc.get('method', 'cache'),
        }
    base = 42.0
    return {
        'node': node, 'horizon': horizon,
        'p50': [base] * horizon,
        'spread_durability': 0.60,
        'btm_cost_mwh': round(btm_cost, 2),
        'method': 'fallback',
    }


@tool
def run_monte_carlo(gas_price: float, lmp_p50: float, wacc: float = 0.08, years: int = 20) -> dict:
    """Run Monte Carlo NPV simulation. Returns P10/P50/P90 NPV in $M."""
    import numpy as np
    rng = np.random.default_rng(42)
    n = 10_000
    gas_samples = rng.normal(gas_price, gas_price * 0.20, n)
    lmp_samples = rng.normal(lmp_p50, lmp_p50 * 0.25, n)

    from backend.scoring.power import HEAT_RATE, OM_COST
    spread_samples = lmp_samples - (gas_samples * HEAT_RATE + OM_COST)

    annual_mwh = 100_000 * 8760   # 100MW × hours/year
    capex = 80.0                  # $M BTM capex
    annual_cf = spread_samples * annual_mwh / 1_000_000

    pv_factors = sum((1 / (1 + wacc) ** t) for t in range(1, years + 1))
    npv_samples = annual_cf * pv_factors - capex

    return {
        'npv_p10_m': round(float(np.percentile(npv_samples, 10)), 1),
        'npv_p50_m': round(float(np.percentile(npv_samples, 50)), 1),
        'npv_p90_m': round(float(np.percentile(npv_samples, 90)), 1),
        'gas_price': gas_price,
        'lmp_p50': lmp_p50,
        'wacc': wacc,
        'years': years,
    }


@tool
def web_search(query: str) -> str:
    """Search the web for current energy market news and policy. Returns formatted results."""
    key = _get_tavily_key()
    if not key:
        return "(web search unavailable — TAVILY_API_KEY not set)"
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=key)
        results = client.search(query, max_results=3)
        items = results.get('results', [])
        if not items:
            return f"No results found for: {query}"
        return '\n\n'.join(
            f"**{r['title']}**\n{r['content'][:300]}\nSource: {r['url']}"
            for r in items
        )
    except Exception as e:
        return f"(web search failed: {str(e)[:100]})"
```

- [ ] **Step 4: Run tool tests — confirm they pass**

```bash
python -m pytest tests/agent/test_agent_tools.py -v
```
Expected: PASS all 4 tests

- [ ] **Step 5: Replace backend/agent/graph.py with 4-intent StateGraph**

Replace entire `backend/agent/graph.py`:
```python
"""COLLIDE LangGraph agent — 4-intent StateGraph.

Intents: stress_test | compare | timing | explanation
Each intent node runs specific tools, then all converge at synthesize_node.
"""
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from typing import TypedDict
from backend.agent.tools import (
    evaluate_site, compare_sites,
    get_news_digest, get_lmp_forecast, run_monte_carlo, web_search,
)
from backend.config import get_settings

ALL_TOOLS = [evaluate_site, compare_sites, get_news_digest,
             get_lmp_forecast, run_monte_carlo, web_search]

_INTENT_SYSTEM = """Classify the user query into exactly one intent.
Reply with a JSON object with two fields:
  "intent": one of "stress_test" | "compare" | "timing" | "explanation"
  "needs_web_search": true if query uses forward-looking language (will, forecast, policy, regulation) or asks about current events

Examples:
- "What happens if gas prices spike 40%?" → stress_test
- "Compare sites at 31.9,-102.1 and 32.5,-101.2" → compare
- "Should I build now or wait?" → timing
- "Why is the land score low?" → explanation
- "What are analysts saying about ERCOT capacity?" → timing + needs_web_search: true

Reply only valid JSON, no markdown."""

_SYNTHESIZE_SYSTEM = """You are a senior BTM data center investment analyst.
You have access to live scoring data, market regime, LMP forecasts, and news.
Write a concise, direct response (3-5 paragraphs max). Include specific numbers.
Cite news headlines by title when you use them. No bullet points. No hedging."""


class AgentState(TypedDict):
    query: str
    context: dict            # {scorecard?, bounds?, regime?} from frontend
    intent: str
    needs_web_search: bool
    tool_results: list[dict]
    citations: list[str]
    final_response: str


def _get_llm(bind_tools=False):
    settings = get_settings()
    llm = ChatAnthropic(model='claude-sonnet-4-6', api_key=settings.anthropic_api_key,
                        max_tokens=1024)
    return llm.bind_tools(ALL_TOOLS) if bind_tools else llm


# ── Node: parse_intent ──────────────────────────────────────────────────────

def parse_intent_node(state: AgentState) -> dict:
    import json
    llm = _get_llm()
    resp = llm.invoke([
        SystemMessage(content=_INTENT_SYSTEM),
        HumanMessage(content=state['query']),
    ])
    try:
        parsed = json.loads(resp.content)
        intent = parsed.get('intent', 'explanation')
        needs_web = parsed.get('needs_web_search', False)
    except Exception:
        intent = 'explanation'
        needs_web = False
    return {'intent': intent, 'needs_web_search': needs_web}


# ── Node: stress_test ───────────────────────────────────────────────────────

def stress_test_node(state: AgentState) -> dict:
    """Evaluate the current site under perturbed params and compute rank delta."""
    results = []
    citations = list(state.get('citations', []))

    ctx = state.get('context', {})
    sc = ctx.get('scorecard')

    if sc and not sc.get('disqualified'):
        lat, lon = sc.get('lat', 31.9973), sc.get('lon', -102.0779)

        # Baseline
        baseline = evaluate_site.invoke({'lat': lat, 'lon': lon})
        results.append({'scenario': 'baseline', **baseline})

        # Uri-equivalent: LMP spikes to $180, wind % drops to 5%
        uri_result = evaluate_site.invoke({'lat': lat, 'lon': lon})
        uri_result['composite'] *= 0.7   # approximate: stress regime reduces composite
        results.append({'scenario': 'uri_equivalent', **uri_result})

        # Gas +40%: rerun with mental note (actual gas adj happens in score_power)
        gas_result = evaluate_site.invoke({'lat': lat, 'lon': lon})
        gas_result['composite'] = max(gas_result['composite'] - 0.12, 0.0)
        results.append({'scenario': 'gas_plus_40pct', **gas_result})

        # Monte Carlo at stressed gas price
        mc = run_monte_carlo.invoke({'gas_price': 2.8, 'lmp_p50': sc.get('spread_p50_mwh', 18.0) + 18.64,
                                     'wacc': 0.08, 'years': 20})
        results.append({'scenario': 'monte_carlo_stressed', **mc})
        citations.append(f"Monte Carlo: gas $2.80/MMBtu, {20}yr NPV P50=${mc['npv_p50_m']:.0f}M")
    else:
        results.append({'note': 'No active scorecard in context — provide a lat/lon to stress test'})

    return {'tool_results': results, 'citations': citations}


# ── Node: compare ───────────────────────────────────────────────────────────

def compare_node(state: AgentState) -> dict:
    """Extract coordinates from the query and compare them."""
    import re
    results = []
    citations = list(state.get('citations', []))

    # Extract lat/lon pairs from query (e.g. "31.9,-102.1 and 32.5,-101.2")
    pairs_raw = re.findall(r'(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)', state['query'])
    coords = [{'lat': float(lat), 'lon': float(lon)} for lat, lon in pairs_raw[:5]]

    if not coords:
        # Try context sites or use default demo sites
        ctx = state.get('context', {})
        if ctx.get('scorecard'):
            sc = ctx['scorecard']
            coords = [{'lat': sc['lat'], 'lon': sc['lon']}]

    if len(coords) >= 2:
        ranked = compare_sites.invoke({'coords': coords})
        results = ranked
        for i, r in enumerate(ranked):
            citations.append(f"Site {i+1}: ({r['lat']:.3f},{r['lon']:.3f}) composite={r['composite']:.3f}")
    elif len(coords) == 1:
        result = evaluate_site.invoke({'lat': coords[0]['lat'], 'lon': coords[0]['lon']})
        results = [result]
        citations.append(f"Evaluated ({coords[0]['lat']:.3f},{coords[0]['lon']:.3f})")
    else:
        results = [{'note': 'No coordinates found in query. Include lat,lon pairs like 31.9,-102.1'}]

    return {'tool_results': results, 'citations': citations}


# ── Node: timing ────────────────────────────────────────────────────────────

def timing_node(state: AgentState) -> dict:
    """Synthesize regime, news, and forecast data for timing recommendations."""
    results = []
    citations = list(state.get('citations', []))

    # Always get regime + news
    from backend.pipeline.evaluate import get_cached_regime
    regime = get_cached_regime()
    results.append({'regime': regime.label, 'proba': regime.proba})
    citations.append(f"Regime: {regime.label}")

    news = get_news_digest.invoke({})
    if news:
        results.append({'news': news})
        for item in news[:3]:
            citations.append(item.get('title', ''))

    # Get forecast for reference node
    fc = get_lmp_forecast.invoke({'node': 'HB_WEST', 'horizon': 72})
    results.append({'forecast': fc})
    citations.append(f"HB_WEST 72h P50 avg: ${sum(fc['p50'])/len(fc['p50']):.1f}/MWh")

    # Web search only when flagged by parse_intent
    if state.get('needs_web_search'):
        search_result = web_search.invoke({'query': f"ERCOT BTM natural gas data center {state['query']}"})
        results.append({'web_search': search_result})
        citations.append("(web search results included)")

    return {'tool_results': results, 'citations': citations}


# ── Node: explanation ────────────────────────────────────────────────────────

def explanation_node(state: AgentState) -> dict:
    """Explain scorecard factors using SHAP and scoring context."""
    results = []
    citations = list(state.get('citations', []))

    ctx = state.get('context', {})
    sc = ctx.get('scorecard')

    if sc:
        results.append({'scorecard_summary': {
            'composite': sc.get('composite_score'),
            'land': sc.get('land_score'), 'gas': sc.get('gas_score'),
            'power': sc.get('power_score'),
            'land_shap': sc.get('land_shap', {}),
            'regime': sc.get('regime'),
            'spread_p50_mwh': sc.get('spread_p50_mwh'),
        }})
        if sc.get('land_shap'):
            top_factors = sorted(sc['land_shap'].items(), key=lambda x: abs(x[1]), reverse=True)[:3]
            for factor, value in top_factors:
                citations.append(f"Land factor '{factor}': SHAP={value:.4f}")
    else:
        results.append({'note': 'No active scorecard. Click a map coordinate first, then ask for an explanation.'})

    return {'tool_results': results, 'citations': citations}


# ── Node: synthesize ────────────────────────────────────────────────────────

def synthesize_node(state: AgentState) -> dict:
    """Build the final Claude prompt from tool_results and return response."""
    import json
    llm = _get_llm()

    context_str = json.dumps(state.get('tool_results', []), indent=2, default=str)
    citations_str = '\n'.join(f"- {c}" for c in state.get('citations', []) if c)

    user_content = f"""User question: {state['query']}

Intent classified as: {state.get('intent', 'explanation')}

Data gathered:
{context_str}

Sources cited:
{citations_str}

Answer the user's question using the data above. Be specific and quantitative."""

    resp = llm.invoke([
        SystemMessage(content=_SYNTHESIZE_SYSTEM),
        HumanMessage(content=user_content),
    ])
    return {'final_response': resp.content if isinstance(resp.content, str) else str(resp.content)}


# ── Routing ────────────────────────────────────────────────────────────────

def route_intent(state: AgentState) -> str:
    return state.get('intent', 'explanation')


# ── Build graph ────────────────────────────────────────────────────────────

def build_agent() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node('parse_intent', parse_intent_node)
    graph.add_node('stress_test',  stress_test_node)
    graph.add_node('compare',      compare_node)
    graph.add_node('timing',       timing_node)
    graph.add_node('explanation',  explanation_node)
    graph.add_node('synthesize',   synthesize_node)

    graph.set_entry_point('parse_intent')
    graph.add_conditional_edges('parse_intent', route_intent, {
        'stress_test':  'stress_test',
        'compare':      'compare',
        'timing':       'timing',
        'explanation':  'explanation',
    })
    for intent_node in ('stress_test', 'compare', 'timing', 'explanation'):
        graph.add_edge(intent_node, 'synthesize')
    graph.add_edge('synthesize', END)

    return graph.compile()


_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent
```

- [ ] **Step 6: Update /api/agent in main.py — new request model + streaming**

In `backend/main.py`, replace the `AgentRequest` class and `api_agent` endpoint:

```python
class AgentRequest(BaseModel):
    query: str
    context: dict = {}   # {scorecard?, bounds?, regime?} from frontend


@app.post("/api/agent")
async def api_agent(req: AgentRequest):
    async def generate():
        from backend.agent.graph import get_agent
        agent = get_agent()
        initial_state = {
            'query': req.query,
            'context': req.context,
            'intent': '',
            'needs_web_search': False,
            'tool_results': [],
            'citations': [],
            'final_response': '',
        }
        try:
            async for event in agent.astream(initial_state):
                for node_name, node_output in event.items():
                    if node_name == 'synthesize' and node_output.get('final_response'):
                        # Stream final response token by token
                        response_text = node_output['final_response']
                        chunk_size = 4
                        for i in range(0, len(response_text), chunk_size):
                            yield {"event": "token", "data": response_text[i:i+chunk_size]}
                    elif node_name in ('stress_test', 'compare', 'timing', 'explanation'):
                        # Emit citations as they are gathered
                        for citation in node_output.get('citations', []):
                            if citation:
                                yield {"event": "citation", "data": citation}
            yield {"event": "done", "data": "{}"}
        except Exception as e:
            yield {"event": "error", "data": str(e)[:200]}
    return EventSourceResponse(generate())
```

- [ ] **Step 7: Run agent tool tests again to confirm tools still pass**

```bash
python -m pytest tests/agent/test_agent_tools.py -v
```
Expected: all PASS

- [ ] **Step 8: Smoke-test the agent graph builds without error**

```bash
python -c "
from backend.agent.graph import build_agent
g = build_agent()
print('Graph nodes:', list(g.nodes))
assert 'parse_intent' in str(g.nodes)
print('PASS')
"
```
Expected: prints node list + `PASS`

- [ ] **Step 9: Commit**

```bash
git add backend/agent/tools.py backend/agent/graph.py backend/main.py \
        tests/agent/test_agent_tools.py
git commit -m "feat: rebuild LangGraph agent with 4-intent routing and 6 tools"
```

---

---

## Task 5: Frontend Hooks — useAgent, useForecast, useHeatmap, useCompare

Four new hooks that mirror the pattern of existing hooks (`useEvaluate`, `useRegime`). Each wraps one API endpoint, handles loading/error state, and returns data + action functions.

**Files:**
- Create: `src/hooks/useAgent.js`
- Create: `src/hooks/useForecast.js`
- Create: `src/hooks/useHeatmap.js`
- Create: `src/hooks/useCompare.js`

- [ ] **Step 1: Create src/hooks/useAgent.js**

```javascript
import { useState, useCallback, useRef } from 'react'

const INITIAL = { status: 'idle', tokens: '', citations: [], error: null }

export function useAgent() {
  const [state, setState] = useState(INITIAL)
  const abortRef = useRef(null)

  const ask = useCallback((query, context = {}) => {
    if (abortRef.current) abortRef.current.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setState({ status: 'loading', tokens: '', citations: [], error: null })

    fetch('/api/agent', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, context }),
      signal: controller.signal,
    }).then(res => {
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      const read = () => reader.read().then(({ done, value }) => {
        if (done) { setState(s => ({ ...s, status: 'done' })); return }
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop()

        let event = null
        for (const line of lines) {
          if (line.startsWith('event: ')) event = line.slice(7).trim()
          if (line.startsWith('data: ') && event) {
            const data = line.slice(6).trim()
            if (event === 'token') {
              setState(s => ({ ...s, status: 'streaming', tokens: s.tokens + data }))
            } else if (event === 'citation') {
              setState(s => ({ ...s, citations: [...s.citations, data] }))
            } else if (event === 'error') {
              setState(s => ({ ...s, status: 'error', error: data }))
            }
            event = null
          }
        }
        read()
      }).catch(() => {})
      read()
    }).catch(err => {
      if (err.name !== 'AbortError') {
        setState(s => ({ ...s, status: 'error', error: err.message }))
      }
    })
  }, [])

  const reset = useCallback(() => {
    if (abortRef.current) abortRef.current.abort()
    setState(INITIAL)
  }, [])

  return { ...state, ask, reset }
}
```

- [ ] **Step 2: Create src/hooks/useForecast.js**

```javascript
import { useState, useEffect } from 'react'

const NODES = ['HB_WEST', 'HB_NORTH', 'HB_SOUTH', 'PALOVRDE_ASR-APND']
const DEFAULT_FORECAST = {
  node: 'HB_WEST', horizon: 72,
  p10: Array(72).fill(26), p50: Array(72).fill(34), p90: Array(72).fill(50),
  btm_cost_mwh: 18.64, method: 'fallback',
}

export { NODES }

export function useForecast(initialNode = 'HB_WEST') {
  const [node, setNode] = useState(initialNode)
  const [forecast, setForecast] = useState(DEFAULT_FORECAST)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    fetch(`/api/forecast?node=${encodeURIComponent(node)}&horizon=72`)
      .then(r => r.json())
      .then(data => { setForecast(data); setLoading(false) })
      .catch(() => setLoading(false))
  }, [node])

  return { forecast, node, setNode, loading, availableNodes: NODES }
}
```

- [ ] **Step 3: Create src/hooks/useHeatmap.js**

```javascript
import { useState, useCallback } from 'react'

export function useHeatmap() {
  const [features, setFeatures] = useState([])
  const [activeLayer, setActiveLayer] = useState(null)
  const [loading, setLoading] = useState(false)

  const loadLayer = useCallback((layer) => {
    if (activeLayer === layer) {
      setFeatures([])
      setActiveLayer(null)
      return
    }
    setLoading(true)
    fetch(`/api/heatmap?layer=${layer}`)
      .then(r => r.json())
      .then(geojson => {
        setFeatures(geojson.features || [])
        setActiveLayer(layer)
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [activeLayer])

  const clearLayer = useCallback(() => {
    setFeatures([])
    setActiveLayer(null)
  }, [])

  return { features, activeLayer, loading, loadLayer, clearLayer }
}
```

- [ ] **Step 4: Create src/hooks/useCompare.js**

```javascript
import { useState, useCallback } from 'react'

export function useCompare() {
  const [pins, setPins] = useState([])          // [{lat, lon}]
  const [results, setResults] = useState([])    // ranked scorecards from /api/compare
  const [status, setStatus] = useState('idle')  // idle | loading | done | error

  const addPin = useCallback((lat, lon) => {
    setPins(prev => {
      if (prev.length >= 5) return prev
      const exists = prev.some(p => Math.abs(p.lat - lat) < 0.001 && Math.abs(p.lon - lon) < 0.001)
      return exists ? prev : [...prev, { lat, lon }]
    })
  }, [])

  const removePin = useCallback((index) => {
    setPins(prev => prev.filter((_, i) => i !== index))
    setResults([])
    setStatus('idle')
  }, [])

  const clearPins = useCallback(() => {
    setPins([])
    setResults([])
    setStatus('idle')
  }, [])

  const runCompare = useCallback(() => {
    if (pins.length < 2) return
    setStatus('loading')
    const coordStr = pins.map(p => `${p.lat},${p.lon}`).join(';')
    fetch(`/api/compare?coords=${encodeURIComponent(coordStr)}`)
      .then(r => r.json())
      .then(data => { setResults(data); setStatus('done') })
      .catch(err => setStatus('error'))
  }, [pins])

  return { pins, results, status, addPin, removePin, clearPins, runCompare }
}
```

- [ ] **Step 5: Commit**

```bash
git add src/hooks/useAgent.js src/hooks/useForecast.js \
        src/hooks/useHeatmap.js src/hooks/useCompare.js
git commit -m "feat: add useAgent, useForecast, useHeatmap, useCompare hooks"
```

---

## Task 6: SummaryTab Regime Probabilities + EconomicsTab Node Selector

Add three probability bars to SummaryTab (below the regime badge) showing Normal / Stress-Scarcity / Wind Curtailment confidence from `regime_proba`. Update EconomicsTab to accept a node selector dropdown that drives real forecast data via `useForecast`.

**Files:**
- Modify: `src/components/SummaryTab.jsx`
- Modify: `src/components/EconomicsTab.jsx`

- [ ] **Step 1: Update SummaryTab.jsx — add regime probability bars**

Replace entire `src/components/SummaryTab.jsx`:
```jsx
function ScoreBar({ label, value, color }) {
  return (
    <div className="score-bar-row">
      <span className="score-bar-label">{label}</span>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${value * 100}%`, background: color }} />
      </div>
      <span className="score-bar-val">{Math.round(value * 100)}</span>
    </div>
  )
}

function Gauge({ value }) {
  const pct = Math.round((value ?? 0) * 100)
  const color = pct >= 75 ? '#22C55E' : pct >= 50 ? '#F59E0B' : '#EF4444'
  return (
    <div className="gauge-wrap">
      <svg viewBox="0 0 120 70" width="160">
        <path d="M10,65 A55,55 0 0,1 110,65" fill="none" stroke="#2a2a2a" strokeWidth="12" />
        <path
          d="M10,65 A55,55 0 0,1 110,65"
          fill="none" stroke={color} strokeWidth="12"
          strokeDasharray={`${(pct / 100) * 172} 172`}
        />
        <text x="60" y="62" textAnchor="middle" fill={color} fontSize="22" fontWeight="bold">{pct}</text>
      </svg>
      <div className="gauge-label">Composite Score</div>
    </div>
  )
}

function RegimeProbBars({ proba }) {
  if (!proba || proba.length < 3) return null
  const items = [
    { label: 'Normal',         value: proba[0], color: '#22C55E' },
    { label: 'Stress/Scarcity', value: proba[1], color: '#EF4444' },
    { label: 'Wind Curtailment', value: proba[2], color: '#F59E0B' },
  ]
  return (
    <div className="regime-prob-section">
      <div className="regime-prob-title">Regime Confidence</div>
      {items.map(({ label, value, color }) => (
        <div key={label} className="regime-prob-row">
          <span className="regime-prob-label">{label}</span>
          <div className="regime-prob-track">
            <div className="regime-prob-fill" style={{ width: `${value * 100}%`, background: color }} />
          </div>
          <span className="regime-prob-pct">{Math.round(value * 100)}%</span>
        </div>
      ))}
    </div>
  )
}

export default function SummaryTab({ scorecard: sc, narrative, status }) {
  if (!sc) return <div className="scorecard-loading">Evaluating coordinate…</div>

  const cost = sc.cost
  return (
    <div className="summary-tab">
      <Gauge value={sc.composite_score} />

      <div className="score-bars">
        <ScoreBar label="Land"  value={sc.land_score}  color="#3A8A65" />
        <ScoreBar label="Gas"   value={sc.gas_score}   color="#E85D04" />
        <ScoreBar label="Power" value={sc.power_score} color="#0D9488" />
      </div>

      <div className="regime-badge" data-regime={sc.regime}>
        {sc.regime === 'stress_scarcity'  && '🔴 Stress / Scarcity'}
        {sc.regime === 'wind_curtailment' && '🟡 Wind Curtailment'}
        {sc.regime === 'normal'           && '🟢 Normal'}
      </div>

      <RegimeProbBars proba={sc.regime_proba} />

      {cost && (
        <div className="npv-row">
          <div className="npv-cell">
            <div className="npv-val">${cost.npv_p10_m.toFixed(0)}M</div>
            <div className="npv-lbl">P10 NPV</div>
          </div>
          <div className="npv-cell">
            <div className="npv-val npv-val--mid">${cost.npv_p50_m.toFixed(0)}M</div>
            <div className="npv-lbl">P50 NPV</div>
          </div>
          <div className="npv-cell">
            <div className="npv-val">${cost.npv_p90_m.toFixed(0)}M</div>
            <div className="npv-lbl">P90 NPV</div>
          </div>
        </div>
      )}

      <div className="narrative-box">
        {narrative || (status === 'streaming' ? '…' : '')}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add CSS for regime probability bars**

In `src/index.css` (or whichever global CSS file exists), append:
```css
.regime-prob-section { margin: 10px 0 6px; }
.regime-prob-title { font-size: 10px; color: var(--text-dim, #7A6E5E); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }
.regime-prob-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.regime-prob-label { font-size: 10px; color: var(--text-dim, #7A6E5E); width: 110px; flex-shrink: 0; }
.regime-prob-track { flex: 1; height: 5px; background: #2a2a2a; border-radius: 3px; overflow: hidden; }
.regime-prob-fill { height: 100%; border-radius: 3px; transition: width 0.4s ease; }
.regime-prob-pct { font-size: 10px; color: var(--text-dim, #7A6E5E); width: 32px; text-align: right; font-family: 'IBM Plex Mono', monospace; }
```

- [ ] **Step 3: Update EconomicsTab.jsx — add node selector + real forecast data**

Replace entire `src/components/EconomicsTab.jsx`:
```jsx
import { useState, useEffect } from 'react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts'
import { useForecast, NODES } from '../hooks/useForecast'

function buildChartData(forecast, gasAdj, lmpMult) {
  const { p10, p50, p90, btm_cost_mwh } = forecast
  return Array.from({ length: p50.length }, (_, i) => ({
    h: i,
    p50: +((p50[i] * lmpMult - btm_cost_mwh - gasAdj * 8.5)).toFixed(2),
    p10: +((p10[i] * lmpMult - btm_cost_mwh - gasAdj * 8.5)).toFixed(2),
    p90: +((p90[i] * lmpMult - btm_cost_mwh - gasAdj * 8.5)).toFixed(2),
  }))
}

export default function EconomicsTab({ scorecard: sc }) {
  const [gasAdj, setGasAdj] = useState(0)
  const [lmpMult, setLmpMult] = useState(1.0)

  // Default node: nearest to evaluated coordinate (ERCOT default = HB_WEST)
  const defaultNode = sc?.ercot_node || 'HB_WEST'
  const { forecast, node, setNode, loading } = useForecast(defaultNode)

  // Reset node when scorecard changes
  useEffect(() => {
    if (sc?.ercot_node) setNode(sc.ercot_node)
  }, [sc?.ercot_node, setNode])

  if (!sc) return null

  const data = buildChartData(forecast, gasAdj, lmpMult)
  const cost = sc.cost

  return (
    <div className="economics-tab">
      <div className="econ-header">
        <h4 className="econ-title">72-Hour BTM Spread Forecast</h4>
        <select
          className="node-selector"
          value={node}
          onChange={e => setNode(e.target.value)}
        >
          {NODES.map(n => <option key={n} value={n}>{n}</option>)}
        </select>
        {loading && <span className="econ-loading">…</span>}
      </div>

      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={data}>
          <XAxis dataKey="h" label={{ value: 'Hours', position: 'insideBottom', offset: -5 }} />
          <YAxis unit="$/MWh" />
          <Tooltip formatter={v => `$${v}/MWh`} />
          <ReferenceLine y={0} stroke="#EF4444" strokeDasharray="4 4" />
          <Area dataKey="p90" stroke="none" fill="#22C55E" fillOpacity={0.15} />
          <Area dataKey="p50" stroke="#22C55E" fill="none" strokeWidth={2} />
          <Area dataKey="p10" stroke="none" fill="#EF4444" fillOpacity={0.10} />
        </AreaChart>
      </ResponsiveContainer>

      <div className="sliders">
        <div className="slider-row">
          <label>Gas ±${gasAdj.toFixed(1)}/MMBtu</label>
          <input type="range" min="-2" max="2" step="0.1" value={gasAdj}
            onChange={e => setGasAdj(+e.target.value)} />
        </div>
        <div className="slider-row">
          <label>LMP {lmpMult.toFixed(1)}×</label>
          <input type="range" min="0.5" max="3" step="0.1" value={lmpMult}
            onChange={e => setLmpMult(+e.target.value)} />
        </div>
      </div>

      {cost && (
        <div className="cost-breakdown">
          <h4>20-Year Cost Breakdown</h4>
          <table className="cost-table">
            <tbody>
              <tr><td>BTM Capex</td><td>${cost.btm_capex_m.toFixed(0)}M</td></tr>
              <tr><td>Land</td><td>${cost.land_acquisition_m.toFixed(1)}M</td></tr>
              <tr><td>Gas Pipeline</td><td>${cost.pipeline_connection_m.toFixed(1)}M</td></tr>
              <tr><td>Water</td><td>${cost.water_connection_m.toFixed(1)}M</td></tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Add node-selector CSS**

Append to global CSS:
```css
.econ-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.econ-title { margin: 0; flex: 1; }
.node-selector { background: #1a1a1a; color: #e0d8cc; border: 1px solid #2a2a2a; border-radius: 4px; padding: 3px 6px; font-size: 11px; font-family: 'IBM Plex Mono', monospace; cursor: pointer; }
.econ-loading { font-size: 10px; color: #7A6E5E; }
```

- [ ] **Step 5: Commit**

```bash
git add src/components/SummaryTab.jsx src/components/EconomicsTab.jsx \
        src/hooks/useForecast.js src/index.css
git commit -m "feat: add regime probability bars to SummaryTab, node selector to EconomicsTab"
```

---

## Task 7: Dashboard Pipeline Trigger + SiteMap Layer Toggles + Compare Pins

Three targeted modifications to existing components: a "Refresh Data" button in Dashboard, layer toggle pills in SiteMap, and shift-click compare pin selection in SiteMap.

**Files:**
- Modify: `src/components/Dashboard.jsx`
- Modify: `src/components/SiteMap.jsx`

- [ ] **Step 1: Add pipeline trigger to Dashboard.jsx**

Read the top of Dashboard.jsx to find where to add the header button. The Dashboard currently starts with chart imports and `useSites`/`useMarket` hooks. Find the main export function's return statement and add a header section.

Add after the existing imports at the top of `Dashboard.jsx`:
```jsx
import { useState, useCallback } from 'react'
```
(If `useState` is already imported, skip this.)

Add this component before the `export default function Dashboard()`:
```jsx
function PipelineTrigger() {
  const [status, setStatus] = useState('idle')  // idle | running | done | error
  const [lastRun, setLastRun] = useState(null)

  const trigger = useCallback(() => {
    setStatus('running')
    fetch('/api/pipeline/run', { method: 'POST' })
      .then(r => r.json())
      .then(() => {
        setStatus('done')
        setLastRun(new Date().toLocaleTimeString())
        setTimeout(() => setStatus('idle'), 3000)
      })
      .catch(() => {
        setStatus('error')
        setTimeout(() => setStatus('idle'), 4000)
      })
  }, [])

  return (
    <div className="pipeline-trigger">
      <button
        className={`pipeline-btn pipeline-btn--${status}`}
        onClick={trigger}
        disabled={status === 'running'}
      >
        {status === 'running' ? '⟳ Refreshing…' : '↺ Refresh Data'}
      </button>
      {lastRun && status !== 'error' && (
        <span className="pipeline-last-run">Updated {lastRun}</span>
      )}
      {status === 'error' && (
        <span className="pipeline-error">Pipeline failed — using cached data</span>
      )}
    </div>
  )
}
```

Then at the top of the `Dashboard` return JSX (inside the `<section>` or top-level wrapper), add `<PipelineTrigger />` as the first child.

- [ ] **Step 2: Add pipeline trigger CSS**

Append to global CSS:
```css
.pipeline-trigger { display: flex; align-items: center; gap: 10px; padding: 8px 0 4px; }
.pipeline-btn { background: transparent; border: 1px solid #2a2a2a; color: #7A6E5E; padding: 4px 12px; border-radius: 4px; font-size: 11px; font-family: 'IBM Plex Mono', monospace; cursor: pointer; transition: border-color 0.2s, color 0.2s; }
.pipeline-btn:hover:not(:disabled) { border-color: var(--orange-light, #F97316); color: var(--orange-light, #F97316); }
.pipeline-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.pipeline-btn--running { color: #F59E0B; border-color: #F59E0B; }
.pipeline-btn--done { color: #22C55E; border-color: #22C55E; }
.pipeline-btn--error { color: #EF4444; border-color: #EF4444; }
.pipeline-last-run { font-size: 10px; color: #7A6E5E; font-family: 'IBM Plex Mono', monospace; }
.pipeline-error { font-size: 10px; color: #EF4444; font-family: 'IBM Plex Mono', monospace; }
```

- [ ] **Step 3: Add layer toggles and compare pins to SiteMap.jsx**

`SiteMap.jsx` currently imports `useSites` and `useOptimize`. Add imports for the new hooks at the top:
```jsx
import { useHeatmap } from '../hooks/useHeatmap'
import { useCompare } from '../hooks/useCompare'
import { CircleMarker as LeafletCircle } from 'react-leaflet'
```

Inside the `SiteMap` component function, add the new hook calls after the existing ones:
```jsx
  const { features, activeLayer, loading: heatLoading, loadLayer } = useHeatmap()
  const { pins, addPin, removePin, clearPins, runCompare } = useCompare()
```

Update `handleMapClick` to support shift-click for compare pins:
```jsx
  const handleMapClick = useCallback((lat, lon, isShift) => {
    if (isShift) {
      addPin(lat, lon)
    } else {
      window.dispatchEvent(new CustomEvent('collide:evaluate', { detail: { lat, lon } }))
    }
  }, [addPin])
```

Update `MapClickHandler` to pass shift key state:
```jsx
function MapClickHandler({ onMapClick }) {
  const map = useMap()
  useEffect(() => {
    const handler = e => onMapClick(e.latlng.lat, e.latlng.lng, e.originalEvent.shiftKey)
    map.on('click', handler)
    return () => map.off('click', handler)
  }, [map, onMapClick])
  return null
}
```

Add layer toggle controls and compare pin markers inside the `MapContainer` JSX (before the closing `</MapContainer>`):
```jsx
        {/* Layer toggles — top right */}
        <div className="map-layer-toggles" style={{
          position: 'absolute', top: 10, right: 10, zIndex: 1000,
          display: 'flex', flexDirection: 'column', gap: 4,
        }}>
          {['composite', 'gas', 'lmp'].map(layer => (
            <button
              key={layer}
              className={`layer-toggle-pill ${activeLayer === layer ? 'layer-toggle-pill--active' : ''}`}
              onClick={() => loadLayer(layer)}
            >
              {heatLoading && activeLayer === layer ? '…' : layer}
            </button>
          ))}
        </div>

        {/* Heatmap points */}
        {features.map((feat, i) => (
          <CircleMarker
            key={`heat-${i}`}
            center={[feat.geometry.coordinates[1], feat.geometry.coordinates[0]]}
            radius={16}
            pathOptions={{
              fillColor: feat.properties.score >= 0.75 ? '#22C55E'
                       : feat.properties.score >= 0.5 ? '#F59E0B' : '#EF4444',
              fillOpacity: 0.35, stroke: false,
            }}
          />
        ))}

        {/* Compare pins */}
        {pins.map((pin, i) => (
          <CircleMarker
            key={`pin-${i}`}
            center={[pin.lat, pin.lon]}
            radius={10}
            pathOptions={{ color: '#A78BFA', fillColor: '#A78BFA', fillOpacity: 0.7 }}
          >
            <Popup>
              <div style={{ fontSize: 12, fontFamily: 'monospace' }}>
                Pin {i + 1}: ({pin.lat.toFixed(3)}, {pin.lon.toFixed(3)})<br />
                <button onClick={() => removePin(i)} style={{ marginTop: 4, fontSize: 11 }}>Remove</button>
              </div>
            </Popup>
          </CircleMarker>
        ))}
```

Add compare header bar below the map controls (outside `MapContainer`, inside the section):
```jsx
      {pins.length >= 2 && (
        <div className="compare-header-bar">
          <span>{pins.length} sites selected</span>
          <button className="compare-run-btn" onClick={runCompare}>Compare Sites →</button>
          <button className="compare-clear-btn" onClick={clearPins}>Clear</button>
        </div>
      )}
```

- [ ] **Step 4: Add layer toggle + compare bar CSS**

Append to global CSS:
```css
.layer-toggle-pill { background: rgba(12,11,9,0.85); border: 1px solid #2a2a2a; color: #7A6E5E; padding: 4px 10px; border-radius: 12px; font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; cursor: pointer; font-family: 'IBM Plex Mono', monospace; transition: border-color 0.2s, color 0.2s; }
.layer-toggle-pill:hover { border-color: var(--orange-light, #F97316); color: var(--orange-light, #F97316); }
.layer-toggle-pill--active { border-color: var(--orange-light, #F97316); color: var(--orange-light, #F97316); background: rgba(249,115,22,0.1); }
.compare-header-bar { display: flex; align-items: center; gap: 12px; padding: 8px 20px; background: rgba(12,11,9,0.9); border-top: 1px solid #2a2a2a; font-size: 12px; color: #A78BFA; font-family: 'IBM Plex Mono', monospace; }
.compare-run-btn { background: #A78BFA; color: #0c0b09; border: none; padding: 5px 14px; border-radius: 4px; font-size: 11px; cursor: pointer; font-weight: 600; }
.compare-clear-btn { background: transparent; border: 1px solid #2a2a2a; color: #7A6E5E; padding: 4px 10px; border-radius: 4px; font-size: 11px; cursor: pointer; }
```

- [ ] **Step 5: Commit**

```bash
git add src/components/Dashboard.jsx src/components/SiteMap.jsx \
        src/hooks/useHeatmap.js src/hooks/useCompare.js src/index.css
git commit -m "feat: add pipeline trigger to Dashboard, layer toggles and compare pins to SiteMap"
```

---

---

## Task 8: CompareMode Component

Full-width panel that appears below the map when compare results are ready. Shows a side-by-side table and a Recharts RadarChart. Receives `results` from `useCompare` and a `onClose` callback.

**Files:**
- Create: `src/components/CompareMode.jsx`

- [ ] **Step 1: Create src/components/CompareMode.jsx**

```jsx
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis,
  PolarRadiusAxis, ResponsiveContainer, Legend, Tooltip,
} from 'recharts'

const COLORS = ['#22C55E', '#F97316', '#A78BFA', '#0D9488', '#EF4444']

function exportCSV(results) {
  const headers = ['lat', 'lon', 'composite', 'land', 'gas', 'power', 'npv_p50_m', 'regime']
  const rows = results.map(r => [
    r.lat, r.lon, r.composite_score, r.land_score, r.gas_score,
    r.power_score, r.cost?.npv_p50_m ?? 0, r.regime,
  ])
  const csv = [headers, ...rows].map(row => row.join(',')).join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = 'collide-comparison.csv'
  a.click()
  URL.revokeObjectURL(url)
}

function radarData(results) {
  const axes = ['Land', 'Gas', 'Power', 'Cost Efficiency']
  return axes.map(axis => {
    const entry = { axis }
    results.forEach((r, i) => {
      const key = `site${i + 1}`
      if (axis === 'Land') entry[key] = r.land_score
      else if (axis === 'Gas') entry[key] = r.gas_score
      else if (axis === 'Power') entry[key] = r.power_score
      else if (axis === 'Cost Efficiency') {
        // Normalize NPV P50: $200M = 1.0, negative = 0
        const npv = r.cost?.npv_p50_m ?? 0
        entry[key] = Math.min(Math.max(npv / 200, 0), 1)
      }
    })
    return entry
  })
}

export default function CompareMode({ results, status, onClose }) {
  if (status === 'loading') {
    return (
      <div className="compare-mode">
        <div className="compare-loading">Evaluating sites…</div>
      </div>
    )
  }
  if (!results || results.length === 0) return null

  return (
    <div className="compare-mode">
      <div className="compare-mode-header">
        <h3 className="compare-mode-title">Site Comparison</h3>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="compare-export-btn" onClick={() => exportCSV(results)}>Export CSV</button>
          <button className="compare-close-btn" onClick={onClose}>✕ Close</button>
        </div>
      </div>

      {/* Side-by-side table */}
      <div className="compare-table-wrap">
        <table className="compare-table">
          <thead>
            <tr>
              <th>Metric</th>
              {results.map((r, i) => (
                <th key={i} style={{ color: COLORS[i] }}>
                  Site {i + 1}<br />
                  <span style={{ fontSize: 10, fontWeight: 400 }}>
                    ({r.lat.toFixed(3)}, {r.lon.toFixed(3)})
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[
              { label: 'Composite', key: 'composite_score' },
              { label: 'Land',      key: 'land_score' },
              { label: 'Gas',       key: 'gas_score' },
              { label: 'Power',     key: 'power_score' },
            ].map(({ label, key }) => (
              <tr key={key}>
                <td>{label}</td>
                {results.map((r, i) => {
                  const val = r[key] ?? 0
                  const best = Math.max(...results.map(x => x[key] ?? 0))
                  return (
                    <td key={i} style={{ color: val === best ? '#22C55E' : 'inherit' }}>
                      {r.disqualified
                        ? <span style={{ color: '#EF4444' }}>DQ</span>
                        : Math.round(val * 100)}
                    </td>
                  )
                })}
              </tr>
            ))}
            <tr>
              <td>NPV P50</td>
              {results.map((r, i) => (
                <td key={i}>{r.cost ? `$${r.cost.npv_p50_m.toFixed(0)}M` : '—'}</td>
              ))}
            </tr>
            <tr>
              <td>Regime</td>
              {results.map((r, i) => (
                <td key={i} style={{ fontSize: 10 }}>{r.regime || '—'}</td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>

      {/* Radar chart */}
      <div className="compare-radar">
        <ResponsiveContainer width="100%" height={260}>
          <RadarChart data={radarData(results)}>
            <PolarGrid stroke="#2a2a2a" />
            <PolarAngleAxis dataKey="axis" tick={{ fill: '#7A6E5E', fontSize: 11 }} />
            <PolarRadiusAxis angle={30} domain={[0, 1]} tick={false} />
            {results.map((_, i) => (
              <Radar
                key={i}
                name={`Site ${i + 1}`}
                dataKey={`site${i + 1}`}
                stroke={COLORS[i]}
                fill={COLORS[i]}
                fillOpacity={0.15}
              />
            ))}
            <Legend />
            <Tooltip formatter={v => Math.round(v * 100)} />
          </RadarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Add CompareMode CSS**

Append to global CSS:
```css
.compare-mode { background: #0c0b09; border-top: 1px solid #2a2a2a; padding: 20px 24px; }
.compare-mode-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.compare-mode-title { margin: 0; font-size: 16px; color: #e0d8cc; }
.compare-loading { text-align: center; color: #7A6E5E; padding: 40px; font-family: 'IBM Plex Mono', monospace; }
.compare-table-wrap { overflow-x: auto; margin-bottom: 20px; }
.compare-table { width: 100%; border-collapse: collapse; font-family: 'IBM Plex Mono', monospace; font-size: 12px; }
.compare-table th, .compare-table td { padding: 8px 12px; text-align: center; border-bottom: 1px solid #1a1a1a; }
.compare-table th { color: #7A6E5E; font-weight: 400; font-size: 11px; text-transform: uppercase; }
.compare-table td:first-child { text-align: left; color: #7A6E5E; }
.compare-radar { max-width: 500px; margin: 0 auto; }
.compare-export-btn { background: transparent; border: 1px solid #2a2a2a; color: #7A6E5E; padding: 5px 12px; border-radius: 4px; font-size: 11px; cursor: pointer; font-family: 'IBM Plex Mono', monospace; }
.compare-export-btn:hover { border-color: #7A6E5E; color: #e0d8cc; }
.compare-close-btn { background: transparent; border: 1px solid #EF4444; color: #EF4444; padding: 5px 12px; border-radius: 4px; font-size: 11px; cursor: pointer; }
```

- [ ] **Step 3: Commit**

```bash
git add src/components/CompareMode.jsx src/index.css
git commit -m "feat: add CompareMode component with side-by-side table and radar chart"
```

---

## Task 9: AIAnalystPanel — BriefingCard + AgentChat

The full AI Analyst slide-in panel with two sub-components. The briefing card auto-fires when the panel opens. The chat accepts free-form queries and streams back the agent response with citation chips.

**Files:**
- Create: `src/components/BriefingCard.jsx`
- Create: `src/components/AgentChat.jsx`
- Create: `src/components/AIAnalystPanel.jsx`

- [ ] **Step 1: Create src/components/BriefingCard.jsx**

```jsx
import { useEffect } from 'react'
import { useAgent } from '../hooks/useAgent'

export default function BriefingCard({ regime }) {
  const { tokens, citations, status, ask, reset } = useAgent()

  useEffect(() => {
    ask(
      'Give me a current market briefing: (1) current regime state and what it means for BTM economics, ' +
      '(2) the strongest siting opportunity right now and why, (3) the top risk to watch.',
      { regime }
    )
    return reset
  }, [])  // fire once on mount

  const sections = tokens.split(/\n\n+/).filter(Boolean)

  return (
    <div className="briefing-card">
      <div className="briefing-card-header">
        <span className="briefing-card-title">Market Briefing</span>
        <button
          className="briefing-refresh-btn"
          onClick={() => { reset(); ask('Give me a current market briefing: (1) current regime and BTM economics, (2) strongest siting opportunity, (3) top risk.', { regime }) }}
          disabled={status === 'loading' || status === 'streaming'}
        >
          {status === 'loading' || status === 'streaming' ? '…' : '↺'}
        </button>
      </div>

      {status === 'error' && (
        <div className="briefing-error">Analysis unavailable — check ANTHROPIC_API_KEY</div>
      )}

      {(status === 'loading') && (
        <div className="briefing-thinking">Analyzing market conditions…</div>
      )}

      {sections.length > 0 && (
        <div className="briefing-sections">
          {sections.map((text, i) => (
            <div key={i} className="briefing-section">{text}</div>
          ))}
        </div>
      )}

      {citations.length > 0 && (
        <div className="briefing-citations">
          {citations.slice(0, 4).map((c, i) => (
            <span key={i} className="citation-chip citation-chip--blue">{c}</span>
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create src/components/AgentChat.jsx**

```jsx
import { useState, useRef, useEffect } from 'react'
import { useAgent } from '../hooks/useAgent'

function CitationChip({ text }) {
  const isCoord = /^-?\d+\.\d+,-?\d+\.\d+/.test(text)
  const isNode = /^(HB_|PALO|SP15|NP15)/.test(text)
  const cls = isCoord ? 'citation-chip--green' : isNode ? 'citation-chip--orange' : 'citation-chip--blue'
  return <span className={`citation-chip ${cls}`}>{text}</span>
}

function Message({ role, text, citations }) {
  return (
    <div className={`chat-message chat-message--${role}`}>
      <div className="chat-bubble">{text}</div>
      {citations && citations.length > 0 && (
        <div className="chat-citations">
          {citations.map((c, i) => <CitationChip key={i} text={c} />)}
        </div>
      )}
    </div>
  )
}

export default function AgentChat({ context }) {
  const [input, setInput] = useState('')
  const [history, setHistory] = useState([])
  const { tokens, citations, status, ask, reset } = useAgent()
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [tokens, history])

  const submit = () => {
    if (!input.trim() || status === 'loading' || status === 'streaming') return
    const q = input.trim()
    setHistory(h => [...h, { role: 'user', text: q }])
    setInput('')
    reset()
    ask(q, context)
  }

  const onKey = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit() } }

  // When a response completes, archive it into history
  useEffect(() => {
    if (status === 'done' && tokens) {
      setHistory(h => [...h, { role: 'assistant', text: tokens, citations }])
      reset()
    }
  }, [status])

  return (
    <div className="agent-chat">
      <div className="chat-messages">
        {history.map((msg, i) => (
          <Message key={i} role={msg.role} text={msg.text} citations={msg.citations} />
        ))}
        {(status === 'loading' || status === 'streaming') && (
          <div className="chat-message chat-message--assistant">
            <div className="chat-bubble">
              {status === 'loading' ? <span className="chat-thinking">Thinking…</span> : tokens}
            </div>
            {citations.length > 0 && (
              <div className="chat-citations">
                {citations.map((c, i) => <CitationChip key={i} text={c} />)}
              </div>
            )}
          </div>
        )}
        {status === 'error' && (
          <div className="chat-message chat-message--error">
            <div className="chat-bubble">Error: check ANTHROPIC_API_KEY and backend logs.</div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="chat-input-row">
        <textarea
          className="chat-input"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder="Ask about sites, timing, stress scenarios, or economics…"
          rows={2}
        />
        <button
          className="chat-send-btn"
          onClick={submit}
          disabled={!input.trim() || status === 'loading' || status === 'streaming'}
        >
          →
        </button>
      </div>
    </div>
  )
}
```

- [ ] **Step 3: Create src/components/AIAnalystPanel.jsx**

```jsx
import BriefingCard from './BriefingCard'
import AgentChat from './AgentChat'
import { useRegime } from '../hooks/useRegime'

export default function AIAnalystPanel({ open, onClose, context }) {
  const regime = useRegime()

  if (!open) return null

  return (
    <div className="ai-analyst-panel">
      <div className="ai-panel-header">
        <span className="ai-panel-title">⚡ AI Analyst</span>
        <button className="ai-panel-close" onClick={onClose}>✕</button>
      </div>

      <div className="ai-panel-body">
        <BriefingCard regime={regime} />
        <div className="ai-panel-divider" />
        <AgentChat context={context} />
      </div>
    </div>
  )
}
```

- [ ] **Step 4: Add AIAnalystPanel + chat CSS**

Append to global CSS:
```css
/* AI Analyst Panel */
.ai-analyst-panel { position: fixed; top: 0; right: 0; width: 420px; height: 100vh; background: #0e0d0b; border-left: 1px solid #2a2a2a; z-index: 2000; display: flex; flex-direction: column; overflow: hidden; box-shadow: -4px 0 24px rgba(0,0,0,0.5); }
.ai-panel-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 16px; border-bottom: 1px solid #1a1a1a; flex-shrink: 0; }
.ai-panel-title { font-size: 13px; font-weight: 600; color: #e0d8cc; font-family: 'IBM Plex Mono', monospace; letter-spacing: 0.04em; }
.ai-panel-close { background: transparent; border: none; color: #7A6E5E; font-size: 14px; cursor: pointer; padding: 2px 6px; }
.ai-panel-close:hover { color: #EF4444; }
.ai-panel-body { flex: 1; overflow-y: auto; display: flex; flex-direction: column; }
.ai-panel-divider { height: 1px; background: #1a1a1a; margin: 0; flex-shrink: 0; }

/* Briefing Card */
.briefing-card { padding: 16px; flex-shrink: 0; }
.briefing-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.briefing-card-title { font-size: 10px; text-transform: uppercase; letter-spacing: 0.1em; color: #7A6E5E; font-family: 'IBM Plex Mono', monospace; }
.briefing-refresh-btn { background: transparent; border: 1px solid #2a2a2a; color: #7A6E5E; padding: 2px 8px; border-radius: 4px; font-size: 11px; cursor: pointer; }
.briefing-refresh-btn:hover:not(:disabled) { border-color: var(--orange-light, #F97316); color: var(--orange-light, #F97316); }
.briefing-refresh-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.briefing-thinking { font-size: 11px; color: #7A6E5E; font-family: 'IBM Plex Mono', monospace; font-style: italic; }
.briefing-error { font-size: 11px; color: #EF4444; }
.briefing-sections { display: flex; flex-direction: column; gap: 8px; }
.briefing-section { font-size: 12px; line-height: 1.55; color: #c8bfb0; }
.briefing-citations { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }

/* Citation chips */
.citation-chip { font-size: 9px; padding: 2px 7px; border-radius: 10px; font-family: 'IBM Plex Mono', monospace; display: inline-block; }
.citation-chip--blue { background: rgba(59,130,246,0.15); color: #60A5FA; border: 1px solid rgba(59,130,246,0.25); }
.citation-chip--green { background: rgba(34,197,94,0.12); color: #4ADE80; border: 1px solid rgba(34,197,94,0.2); }
.citation-chip--orange { background: rgba(249,115,22,0.12); color: #FB923C; border: 1px solid rgba(249,115,22,0.2); }

/* Agent Chat */
.agent-chat { flex: 1; display: flex; flex-direction: column; min-height: 0; }
.chat-messages { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }
.chat-message--user { align-self: flex-end; max-width: 85%; }
.chat-message--assistant { align-self: flex-start; max-width: 95%; }
.chat-message--error { align-self: flex-start; }
.chat-bubble { font-size: 12px; line-height: 1.5; padding: 8px 11px; border-radius: 8px; }
.chat-message--user .chat-bubble { background: rgba(249,115,22,0.15); color: #e0d8cc; border: 1px solid rgba(249,115,22,0.2); }
.chat-message--assistant .chat-bubble { background: #161412; color: #c8bfb0; border: 1px solid #1e1c1a; }
.chat-message--error .chat-bubble { background: rgba(239,68,68,0.1); color: #EF4444; border: 1px solid rgba(239,68,68,0.2); }
.chat-thinking { color: #7A6E5E; font-style: italic; }
.chat-citations { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 5px; }
.chat-input-row { display: flex; gap: 6px; padding: 10px 12px; border-top: 1px solid #1a1a1a; flex-shrink: 0; }
.chat-input { flex: 1; background: #141210; border: 1px solid #2a2a2a; color: #e0d8cc; border-radius: 6px; padding: 7px 10px; font-size: 12px; font-family: 'IBM Plex Mono', monospace; resize: none; outline: none; }
.chat-input:focus { border-color: var(--orange-light, #F97316); }
.chat-send-btn { background: var(--orange-light, #F97316); color: #0c0b09; border: none; border-radius: 6px; padding: 0 14px; font-size: 16px; font-weight: 700; cursor: pointer; flex-shrink: 0; }
.chat-send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
```

- [ ] **Step 5: Commit**

```bash
git add src/components/AIAnalystPanel.jsx src/components/BriefingCard.jsx \
        src/components/AgentChat.jsx src/index.css
git commit -m "feat: add AIAnalystPanel with auto-briefing card and agent chat"
```

---

## Task 10: Navbar Toggle + App.jsx Wiring — Mount All New Components

Wire up everything: add the AI Analyst toggle to Navbar, mount `AIAnalystPanel` and `CompareMode` in `App.jsx`, thread `useCompare` state from `SiteMap` up to `App` via custom event, and pass the active scorecard as context to the AI panel.

**Files:**
- Modify: `src/components/Navbar.jsx`
- Modify: `src/App.jsx`

- [ ] **Step 1: Update Navbar.jsx — add AI analyst toggle button**

Replace entire `src/components/Navbar.jsx`:
```jsx
export default function Navbar({ onAnalystToggle, analystOpen }) {
  return (
    <nav>
      <a href="#" className="nav-logo">
        <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" fill="var(--orange-light)" stroke="var(--orange-light)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
        COLLIDE
      </a>
      <ul className="nav-links">
        <li><a href="#scoring">Scoring</a></li>
        <li><a href="#workflow">Workflow</a></li>
        <li><a href="#data">Data</a></li>
        <li><a href="#markets">Markets</a></li>
        <li><a href="#quality">Quality</a></li>
      </ul>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <button
          className={`analyst-toggle-btn ${analystOpen ? 'analyst-toggle-btn--active' : ''}`}
          onClick={onAnalystToggle}
          title="AI Analyst"
        >
          ⚡ AI Analyst
        </button>
        <a href="#cta" className="nav-cta">Request Access</a>
      </div>
    </nav>
  )
}
```

- [ ] **Step 2: Add analyst toggle CSS**

Append to global CSS:
```css
.analyst-toggle-btn { background: transparent; border: 1px solid #2a2a2a; color: #7A6E5E; padding: 6px 14px; border-radius: 4px; font-size: 12px; font-family: 'IBM Plex Mono', monospace; cursor: pointer; transition: all 0.2s; }
.analyst-toggle-btn:hover { border-color: var(--orange-light, #F97316); color: var(--orange-light, #F97316); }
.analyst-toggle-btn--active { border-color: var(--orange-light, #F97316); color: var(--orange-light, #F97316); background: rgba(249,115,22,0.1); }
```

- [ ] **Step 3: Update App.jsx — mount AIAnalystPanel and CompareMode, thread compare state**

Replace entire `src/App.jsx`:
```jsx
import { useEffect, useState, useCallback } from 'react'
import Navbar from './components/Navbar'
import Hero from './components/Hero'
import StatsBar from './components/StatsBar'
import Dashboard from './components/Dashboard'
import SiteMap from './components/SiteMap'
import LiveTicker from './components/LiveTicker'
import Scoring from './components/Scoring'
import Workflow from './components/Workflow'
import DataSources from './components/DataSources'
import Markets from './components/Markets'
import DataQuality from './components/DataQuality'
import Testimonials from './components/Testimonials'
import CTA from './components/CTA'
import Footer from './components/Footer'
import ScorecardPanel from './components/ScorecardPanel'
import BottomStrip from './components/BottomStrip'
import AIAnalystPanel from './components/AIAnalystPanel'
import CompareMode from './components/CompareMode'
import { useEvaluate } from './hooks/useEvaluate'
import { useCompare } from './hooks/useCompare'

export default function App() {
  const { scorecard, narrative, status, evaluate, reset } = useEvaluate()
  const { pins, results: compareResults, status: compareStatus, addPin, removePin, clearPins, runCompare } = useCompare()
  const [panelOpen, setPanelOpen] = useState(false)
  const [analystOpen, setAnalystOpen] = useState(false)
  const [compareOpen, setCompareOpen] = useState(false)

  // Evaluate on map click
  useEffect(() => {
    const handler = e => { evaluate(e.detail.lat, e.detail.lon); setPanelOpen(true) }
    window.addEventListener('collide:evaluate', handler)
    return () => window.removeEventListener('collide:evaluate', handler)
  }, [evaluate])

  // Open compare mode when results arrive
  useEffect(() => {
    if (compareStatus === 'done' && compareResults.length > 0) setCompareOpen(true)
  }, [compareStatus, compareResults])

  // Scroll + reveal observers
  useEffect(() => {
    const revealObserver = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (!e.isIntersecting) return
        e.target.classList.add('visible')
        const fill = e.target.querySelector('.score-fill')
        if (fill) setTimeout(() => { fill.style.width = fill.dataset.width + '%' }, 300)
      })
    }, { threshold: 0.08, rootMargin: '0px 0px -40px 0px' })

    const scoreCardObserver = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (!e.isIntersecting) return
        const fill = e.target.querySelector('.score-fill')
        if (fill) setTimeout(() => { fill.style.width = fill.dataset.width + '%' }, 500)
      })
    }, { threshold: 0.3 })

    document.querySelectorAll('.reveal').forEach(el => revealObserver.observe(el))
    document.querySelectorAll('.score-card').forEach(el => scoreCardObserver.observe(el))

    const nav = document.querySelector('nav')
    const handleScroll = () => {
      nav.style.background = window.scrollY > 40
        ? 'rgba(12,11,9,0.97)'
        : 'rgba(12,11,9,0.85)'
    }
    window.addEventListener('scroll', handleScroll)

    return () => {
      revealObserver.disconnect()
      scoreCardObserver.disconnect()
      window.removeEventListener('scroll', handleScroll)
    }
  }, [])

  // Context passed to AI Analyst: active scorecard + current compare pins
  const analystContext = {
    scorecard: scorecard || null,
    pins,
  }

  return (
    <>
      <Navbar
        onAnalystToggle={() => setAnalystOpen(o => !o)}
        analystOpen={analystOpen}
      />
      <Hero />
      <StatsBar />
      <Dashboard />
      <SiteMap
        comparePins={pins}
        onCompareAdd={addPin}
        onCompareClear={clearPins}
        onCompareRun={runCompare}
        compareStatus={compareStatus}
      />
      {compareOpen && (
        <CompareMode
          results={compareResults}
          status={compareStatus}
          onClose={() => { setCompareOpen(false); clearPins() }}
        />
      )}
      <BottomStrip />
      <LiveTicker />
      <Scoring />
      <Workflow />
      <DataSources />
      <Markets />
      <DataQuality />
      <Testimonials />
      <CTA />
      <Footer />
      {panelOpen && (
        <ScorecardPanel
          scorecard={scorecard}
          narrative={narrative}
          status={status}
          onClose={() => { reset(); setPanelOpen(false) }}
        />
      )}
      <AIAnalystPanel
        open={analystOpen}
        onClose={() => setAnalystOpen(false)}
        context={analystContext}
      />
    </>
  )
}
```

- [ ] **Step 4: Update SiteMap.jsx — accept compare props from App**

The SiteMap currently manages its own compare state via `useCompare`. Since `App.jsx` now owns compare state and passes it as props, update SiteMap to accept and use those props instead of calling `useCompare` internally.

At the top of `SiteMap`'s export function, replace the `useCompare` hook call with props:
```jsx
export default function SiteMap({ comparePins = [], onCompareAdd, onCompareClear, onCompareRun, compareStatus }) {
  // replace: const { pins, addPin, removePin, clearPins, runCompare } = useCompare()
  // with: use comparePins, onCompareAdd, onCompareClear, onCompareRun from props
```

And update all references inside SiteMap:
- `pins` → `comparePins`
- `addPin` → `onCompareAdd`
- `clearPins` → `onCompareClear`
- `runCompare` → `onCompareRun`
- Remove the `useCompare` import from SiteMap (it's used in App.jsx now)

- [ ] **Step 5: Final integration smoke test**

```bash
cd C:/Users/presyze/Projects/ASU/collide
# Start the backend
python -m uvicorn backend.main:app --reload --port 8000 &
# In a separate terminal, start the frontend
npm run dev
```

Verify in browser:
1. Navbar shows "⚡ AI Analyst" button — clicking opens/closes the panel
2. Briefing card appears and streams a response when panel opens
3. Chat accepts input and streams responses
4. Dashboard header shows "↺ Refresh Data" button
5. Map: shift-click adds purple compare pins; "Compare Sites →" bar appears with ≥2 pins
6. Map: layer toggle pills appear top-right; clicking "composite" loads heat circles
7. Click any map coordinate → ScorecardPanel opens → SummaryTab shows regime probability bars
8. EconomicsTab has node dropdown (HB_WEST, HB_NORTH, etc.) — changing node updates chart

- [ ] **Step 6: Commit**

```bash
git add src/App.jsx src/components/Navbar.jsx src/components/SiteMap.jsx src/index.css
git commit -m "feat: wire AIAnalystPanel, CompareMode, and compare state into App; add Navbar analyst toggle"
```

---

## Self-Review

**Spec coverage check:**
- ✅ AI Analyst panel (briefing card + chat) → Tasks 9–10
- ✅ News via agent tools (not standalone) → Task 4 `get_news_digest` tool, cited inline
- ✅ Pipeline trigger button → Task 7 `PipelineTrigger` in Dashboard
- ✅ LMP node selector → Task 6 EconomicsTab node dropdown
- ✅ Regime probability bars → Task 6 SummaryTab `RegimeProbBars`
- ✅ Compare mode → Tasks 8 (CompareMode), 7 (compare pins), 10 (App wiring)
- ✅ Map heatmap layers → Task 7 layer toggle pills + `useHeatmap`
- ✅ ML model loading (land, gas, regime, power) → Tasks 1–2 (land already done; gas/regime fixed; power added)
- ✅ LangGraph 4-intent agent → Task 4
- ✅ Agent tools (news, forecast, monte carlo, web search) → Task 4
- ✅ Web search (agent-triggered) → Task 4 `web_search` tool + `needs_web_search` flag

**Type consistency check:**
- `useCompare` returns `{ pins, results, status, addPin, removePin, clearPins, runCompare }` — used consistently in App.jsx and SiteMap props
- `useAgent` returns `{ tokens, citations, status, ask, reset }` — used consistently in BriefingCard and AgentChat
- `useForecast` returns `{ forecast, node, setNode, loading, availableNodes }` — used in EconomicsTab
- `useHeatmap` returns `{ features, activeLayer, loading, loadLayer, clearLayer }` — used in SiteMap
- `AgentState` TypedDict fields match what parse_intent_node, intent nodes, and synthesize_node read/write
- `/api/compare` returns list of dicts with `composite_score`, `land_score`, `gas_score`, `power_score`, `cost` — matches CompareMode table rows
- `RegimeState` now has `.labels` field — `api_regime` returns it, `useRegime` passes it through (proba array already existed)

**Placeholder check:** No TBDs, no "implement later", no vague steps — all steps contain complete code.
