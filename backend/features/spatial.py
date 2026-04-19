"""Spatial feature lookup backed by pre-built KDTree indices.

Loaded lazily on first call from data/models/land_spatial_index.pkl and
data/models/pipeline_index.pkl (built by scripts/training/build_land_spatial_index.py).

Falls back to None gracefully when index files don't exist.
"""
import math
import logging
import pickle
import warnings
from pathlib import Path
from typing import Optional

try:
    from sklearn.exceptions import InconsistentVersionWarning
except Exception:
    InconsistentVersionWarning = Warning

import numpy as np

_LAND_INDEX_PATH = Path("data/models/land_spatial_index.pkl")
_PIPE_INDEX_PATH = Path("data/models/pipeline_index.pkl")

_LOGGER = logging.getLogger(__name__)
_land_idx = None
_pipe_idx = None
_idx_load_attempted = False
_load_warned = False


def _load_indices():
    global _land_idx, _pipe_idx, _idx_load_attempted, _load_warned
    if _idx_load_attempted:
        return
    _idx_load_attempted = True

    for path, attr in [(_LAND_INDEX_PATH, '_land_idx'), (_PIPE_INDEX_PATH, '_pipe_idx')]:
        if path.exists():
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter('ignore', InconsistentVersionWarning)
                    with open(path, 'rb') as f:
                        obj = pickle.load(f)
                if attr == '_land_idx':
                    globals()['_land_idx'] = obj
                else:
                    globals()['_pipe_idx'] = obj
            except Exception as exc:
                if not _load_warned:
                    _LOGGER.warning("Failed to load spatial index from %s: %s", path, exc)
                    globals()['_load_warned'] = True


def _dist_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine distance in km."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(max(0, min(1, a))))


def nearest_water_km(lat: float, lon: float) -> Optional[float]:
    """Return distance in km to nearest NHD water body, or None if index missing."""
    _load_indices()
    if _land_idx is None or 'water_tree' not in _land_idx:
        return None
    tree = _land_idx['water_tree']
    coords = _land_idx['water_coords']
    _, idx = tree.query([lat, lon])
    w_lat, w_lon = coords[idx]
    return _dist_km(lat, lon, w_lat, w_lon)


def nearest_pipeline_km(lat: float, lon: float) -> Optional[float]:
    """Return distance in km to nearest gas pipeline segment, or None if missing."""
    _load_indices()
    if _pipe_idx is None or 'pipe_tree' not in _pipe_idx:
        return None
    tree = _pipe_idx['pipe_tree']
    coords = _pipe_idx['pipe_coords']
    _, idx = tree.query([lat, lon])
    p_lat, p_lon = coords[idx]
    return _dist_km(lat, lon, p_lat, p_lon)


def nearest_pipeline_info(lat: float, lon: float) -> Optional[dict]:
    """Return {dist_km, pipe_type, status} for nearest pipeline segment."""
    _load_indices()
    if _pipe_idx is None:
        return None
    tree = _pipe_idx['pipe_tree']
    coords = _pipe_idx['pipe_coords']
    _, idx = tree.query([lat, lon])
    p_lat, p_lon = coords[idx]
    return {
        'dist_km': _dist_km(lat, lon, p_lat, p_lon),
        'pipe_type': str(_pipe_idx['pipe_types'][idx]),
        'status': str(_pipe_idx['pipe_statuses'][idx]),
    }


def seismic_hazard(lat: float, lon: float, radius_km: float = 100.0) -> Optional[float]:
    """Return 0–1 seismic hazard score (higher = more seismic risk)."""
    _load_indices()
    if _land_idx is None or 'seis_tree' not in _land_idx:
        return None
    tree = _land_idx['seis_tree']
    mags = _land_idx['seis_mags']
    seis_max = _land_idx.get('seis_max', 1.0)

    lat_r = radius_km / 111.0
    candidates = tree.query_ball_point([lat, lon], lat_r)
    if not candidates:
        return 0.0
    candidate_mags = mags[candidates]
    energy_weights = np.power(10.0, 1.5 * candidate_mags)
    raw = float(np.log1p(energy_weights.sum()))
    return float(min(raw / seis_max, 1.0))


def wildfire_risk(lat: float, lon: float) -> Optional[float]:
    """Return 0–1 wildfire risk score (higher = more wildfire risk)."""
    _load_indices()
    if _land_idx is None or 'wf_tree' not in _land_idx:
        return None
    wf_coords = _land_idx.get('wf_coords')
    if wf_coords is None or len(wf_coords) == 0:
        return None
    tree = _land_idx['wf_tree']
    risks = _land_idx['wf_risks']
    _, idx = tree.query([lat, lon])
    return float(risks[idx])


def ownership_type(lat: float, lon: float) -> Optional[str]:
    """Return ownership type ('private', 'state', 'blm_federal') for nearest known parcel."""
    _load_indices()
    if _land_idx is None or _land_idx.get('glo_tree') is None:
        return None
    tree = _land_idx['glo_tree']
    coords = _land_idx['glo_coords']
    status = _land_idx['glo_status']
    _, idx = tree.query([lat, lon])
    p_lat, p_lon = coords[idx]
    dist = _dist_km(lat, lon, p_lat, p_lon)
    if dist > 50.0:
        return None  # too far, can't reliably infer ownership
    raw_status = str(status[idx]).lower()
    if 'active' in raw_status or 'processing' in raw_status:
        return 'state'  # GLO upland leases are Texas state land
    return 'private'


def spatial_features(lat: float, lon: float) -> dict:
    """Return all spatial features for a (lat, lon) as a dict.

    Values are None when the index is unavailable. Callers should fall back
    to state-level medians for any None values.
    """
    return {
        'water_km': nearest_water_km(lat, lon),
        'pipeline_km': nearest_pipeline_km(lat, lon),
        'seismic_hazard': seismic_hazard(lat, lon),
        'wildfire_risk': wildfire_risk(lat, lon),
        'ownership_type': ownership_type(lat, lon),
    }
