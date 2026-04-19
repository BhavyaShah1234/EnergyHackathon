"""Gas Supply Reliability scorer. Loads KDE from data/models/gas_kde.pkl when available."""
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
