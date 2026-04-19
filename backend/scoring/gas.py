"""Gas Supply Reliability scorer. Loads KDE from data/models/gas_kde.pkl when available."""
import logging
from pathlib import Path
import numpy as np


class GPUKernelDensity:
    """GPU-accelerated Gaussian KDE (PyTorch) with sklearn KernelDensity-compatible interface.

    Stored in this module so pickle can resolve the class on load.
    Falls back to CPU tensors when CUDA is unavailable.
    """

    def __init__(self, bandwidth=0.5):
        self.bandwidth = bandwidth
        self._train_pts = None
        self._log_weights = None

    def fit(self, X, sample_weight=None):
        import torch
        w = np.ones(len(X), dtype=np.float32) if sample_weight is None else np.array(sample_weight, dtype=np.float32)
        w /= w.sum()
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._train_pts = torch.tensor(X, dtype=torch.float32).to(device)
        self._log_weights = torch.tensor(np.log(w), dtype=torch.float32).to(device)
        return self

    def score_samples(self, X):
        import torch
        device = self._train_pts.device
        X_t = torch.tensor(np.array(X, dtype=np.float32)).to(device)
        diff = X_t.unsqueeze(1) - self._train_pts.unsqueeze(0)
        sq_dist = (diff ** 2).sum(dim=-1)
        D = X_t.shape[1]
        log_norm = -D * (np.log(self.bandwidth) + 0.5 * np.log(2 * np.pi))
        log_kernel = -0.5 * sq_dist / (self.bandwidth ** 2)
        log_density = torch.logsumexp(log_kernel + self._log_weights.unsqueeze(0), dim=1) + log_norm
        return log_density.cpu().numpy()

_KDE_PATH = Path('data/models/gas_kde.pkl')
_LOGGER = logging.getLogger(__name__)

_KDE_MODEL = None
_KDE_LOAD_ATTEMPTED = False
_KDE_LOAD_WARNED = False
_KDE_SCORE_WARNED = False

_INCIDENT_WEIGHT = 0.40
_PIPELINE_WEIGHT = 0.35
_WAHA_WEIGHT     = 0.25


def _load_kde_model():
    """Load cached KDE model once. Return None when unavailable or incompatible."""
    global _KDE_MODEL, _KDE_LOAD_ATTEMPTED, _KDE_LOAD_WARNED
    if _KDE_LOAD_ATTEMPTED:
        return _KDE_MODEL

    _KDE_LOAD_ATTEMPTED = True
    if not _KDE_PATH.exists():
        return None

    try:
        import pickle
        with open(_KDE_PATH, 'rb') as f:
            _KDE_MODEL = pickle.load(f)
    except Exception as exc:
        _KDE_MODEL = None
        if not _KDE_LOAD_WARNED:
            _LOGGER.warning("Failed to load gas KDE model from %s; using rule-based gas scoring fallback (%s)", _KDE_PATH, exc)
            _KDE_LOAD_WARNED = True

    return _KDE_MODEL


def score_gas(
    lat: float,
    lon: float,
    incident_density: float,
    interstate_pipeline_km: float,
    waha_distance_km: float,
    pipeline_web_score: float | None = None,
) -> float:
    """Return gas reliability score 0–1.

    Args:
        lat, lon: coordinate (used for KDE lookup when model is loaded)
        incident_density: PHMSA fallback density when KDE not available
        interstate_pipeline_km: distance to nearest interstate pipeline
        waha_distance_km: distance to Waha Hub
        pipeline_web_score: [0,1] operator reliability from Tavily+Claude web
            context (None = not available, skip). When provided, blended in
            at 20% weight and the other three weights are scaled to 80%.
    """
    kde = _load_kde_model()
    global _KDE_SCORE_WARNED
    if kde is not None:
        try:
            log_density = float(kde.score_samples([[lat, lon]])[0])
            # log_density is negative; higher (less negative) = denser incidents = lower reliability
            # Normalize: typical range [-15, -3] → incident_score [0, 1]
            incident_score = max(0.0, min(1.0, 1.0 - (log_density + 15) / 12.0))
        except Exception as exc:
            incident_score = max(0.0, 1.0 - min(incident_density * 200, 1.0))
            if not _KDE_SCORE_WARNED:
                _LOGGER.warning("Failed to score with gas KDE model; falling back to incident_density heuristic (%s)", exc)
                _KDE_SCORE_WARNED = True
    else:
        incident_score = max(0.0, 1.0 - min(incident_density * 200, 1.0))

    pipeline_score = max(0.0, 1.0 - interstate_pipeline_km / 100.0)
    waha_score     = max(0.0, 1.0 - waha_distance_km / 400.0)

    if pipeline_web_score is not None:
        # Web context adds a 4th component at 20%; scale base weights to 80%
        raw = (
            incident_score  * _INCIDENT_WEIGHT * 0.80 +
            pipeline_score  * _PIPELINE_WEIGHT * 0.80 +
            waha_score      * _WAHA_WEIGHT     * 0.80 +
            pipeline_web_score                 * 0.20
        )
    else:
        raw = (
            incident_score * _INCIDENT_WEIGHT +
            pipeline_score * _PIPELINE_WEIGHT +
            waha_score     * _WAHA_WEIGHT
        )
    return round(min(max(raw, 0.0), 1.0), 4)
