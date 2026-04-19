"""Land & Lease Viability scorer for arbitrary coordinates.

Baseline: rule-based weighted formula with SHAP-style per-feature attribution.
Upgrade: loads scikit-learn Random Forest from data/models/land_rf.pkl when available.
"""
import logging
import warnings
from pathlib import Path
from backend.features.vector import FeatureVector, DISQUALIFY_FEMA, MIN_ACRES

try:
    from sklearn.exceptions import InconsistentVersionWarning
except Exception:  # pragma: no cover - sklearn may be absent in some test environments
    InconsistentVersionWarning = Warning

_WEIGHTS = {
    'water':      0.15,
    'fiber':      0.12,
    'pipeline':   0.10,
    'substation': 0.08,
    'highway':    0.07,
    'ownership':  0.18,
    'fema':       0.10,
    'seismic':    0.08,
    'wildfire':   0.07,
    'epa':        0.05,
}
assert abs(sum(_WEIGHTS.values()) - 1.0) < 0.001

_FEMA_SCORES = {'X': 1.0, 'X500': 0.7, 'D': 0.4, 'A': 0.0, 'AE': 0.0, 'V': 0.0}
_OWNERSHIP_SCORES = {'private': 1.0, 'state': 0.6, 'blm_federal': 0.3}

_MODEL_PATH = Path('data/models/land_rf.pkl')
_LOGGER = logging.getLogger(__name__)
_MODEL_BUNDLE = None
_EXPLAINER = None
_MODEL_LOAD_ATTEMPTED = False
_LAND_LOAD_WARNED = False
_LAND_SCORE_WARNED = False
_LAND_SHAP_WARNED = False


def check_hard_disqualifiers(fv: FeatureVector) -> str | None:
    if fv.fema_zone in DISQUALIFY_FEMA:
        return f"FEMA flood zone {fv.fema_zone} — unbuildable"
    if fv.is_federal_wilderness:
        return "Federal wilderness designation — no development permitted"
    if fv.acres_available < MIN_ACRES:
        return f"Only {fv.acres_available:.0f} contiguous acres — minimum {MIN_ACRES:.0f} required"
    return None


def _rule_based(fv: FeatureVector) -> tuple[float, dict[str, float]]:
    raw = {
        'water':      max(0.0, 1.0 - fv.water_km / 15.0),
        'fiber':      max(0.0, 1.0 - fv.fiber_km / 10.0),
        'pipeline':   max(0.0, 1.0 - fv.pipeline_km / 20.0),
        'substation': max(0.0, 1.0 - fv.substation_km / 25.0),
        'highway':    max(0.0, 1.0 - fv.highway_km / 15.0),
        'ownership':  _OWNERSHIP_SCORES.get(fv.ownership_type, 0.5),
        'fema':       _FEMA_SCORES.get(fv.fema_zone, 0.4),
        'seismic':    1.0 - fv.seismic_hazard,
        'wildfire':   1.0 - fv.wildfire_risk,
        'epa':        1.0 if fv.epa_attainment else 0.5,
    }
    shap = {k: round(raw[k] * _WEIGHTS[k], 5) for k in raw}
    score = round(min(max(sum(shap.values()), 0.0), 1.0), 4)
    return score, shap


def _load_land_assets():
    """Load LightGBM model/scaler + optional SHAP explainer once per process."""
    global _MODEL_BUNDLE, _EXPLAINER, _MODEL_LOAD_ATTEMPTED, _LAND_LOAD_WARNED
    if _MODEL_LOAD_ATTEMPTED:
        return _MODEL_BUNDLE, _EXPLAINER

    _MODEL_LOAD_ATTEMPTED = True
    if not _MODEL_PATH.exists():
        return None, None

    try:
        import pickle
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', InconsistentVersionWarning)
            with open(_MODEL_PATH, 'rb') as f:
                bundle = pickle.load(f)
        if isinstance(bundle, tuple) and len(bundle) == 2:
            _MODEL_BUNDLE = bundle
    except Exception as exc:
        _MODEL_BUNDLE = None
        if not _LAND_LOAD_WARNED:
            _LOGGER.warning("Failed to load land model bundle from %s; using rule-based land scoring fallback (%s)", _MODEL_PATH, exc)
            _LAND_LOAD_WARNED = True

    shap_path = _MODEL_PATH.with_suffix('.shap.pkl')
    if shap_path.exists():
        try:
            import pickle
            with warnings.catch_warnings():
                warnings.simplefilter('ignore', InconsistentVersionWarning)
                with open(shap_path, 'rb') as f:
                    _EXPLAINER = pickle.load(f)
        except Exception:
            _EXPLAINER = None

    return _MODEL_BUNDLE, _EXPLAINER


def score_land(fv: FeatureVector) -> tuple[float, dict[str, float]]:
    """Return (land_score, shap_dict). Loads LightGBM model if available."""
    global _LAND_SCORE_WARNED, _LAND_SHAP_WARNED
    bundle, explainer = _load_land_assets()
    if bundle is not None:
        try:
            import numpy as np
            model, scaler = bundle
            features = np.array([[
                fv.water_km, fv.fiber_km, fv.pipeline_km, fv.substation_km,
                fv.highway_km, _OWNERSHIP_SCORES.get(fv.ownership_type, 0.5),
                _FEMA_SCORES.get(fv.fema_zone, 0.4),
                fv.seismic_hazard, fv.wildfire_risk, float(fv.epa_attainment),
            ]])
            X = scaler.transform(features)
            score = float(model.predict_proba(X)[0, 1])

            _, shap = _rule_based(fv)
            if explainer is not None:
                try:
                    keys = ['water', 'fiber', 'pipeline', 'substation', 'highway',
                            'ownership', 'fema', 'seismic', 'wildfire', 'epa']
                    with warnings.catch_warnings():
                        warnings.filterwarnings(
                            'ignore',
                            message='LightGBM binary classifier with TreeExplainer shap values output has changed to a list of ndarray',
                            category=UserWarning,
                        )
                        shap_values = explainer.shap_values(X)
                    import numpy as _np
                    sv_raw = _np.array(shap_values) if not isinstance(shap_values, list) else shap_values
                    if isinstance(sv_raw, list):
                        # Old shap: list[neg_class, pos_class], each shape (n, features)
                        sv = sv_raw[1][0] if len(sv_raw) > 1 else sv_raw[0][0]
                    elif sv_raw.ndim == 3:
                        # shap 0.51+: (n_samples, n_features, n_classes) — take pos class
                        sv = sv_raw[0, :, 1]
                    else:
                        sv = sv_raw[0]
                    shap = {k: round(float(v), 5) for k, v in zip(keys, sv)}
                except Exception as exc:
                    if not _LAND_SHAP_WARNED:
                        _LOGGER.warning("Failed to compute land SHAP values; using rule-based attributions (%s)", exc)
                        _LAND_SHAP_WARNED = True

            return round(min(max(score, 0.0), 1.0), 4), shap
        except Exception as exc:
            if not _LAND_SCORE_WARNED:
                _LOGGER.warning("Land model inference failed; using rule-based land scoring fallback (%s)", exc)
                _LAND_SCORE_WARNED = True
            pass
    return _rule_based(fv)
