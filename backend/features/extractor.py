"""extract_features(lat, lon) -> FeatureVector.

Uses spatial KDTree indices (from build_land_spatial_index.py) when available,
live EIA gas price + GridStatus LMP from ingest.cache when available,
falling back to state-level median approximations otherwise.
"""
import math
from backend.features.vector import FeatureVector
from backend.features import spatial as _spatial
from backend.ingest.cache import get_live_waha_price, get_live_lmp


# ── State / market classification ──────────────────────────────────────────

def _classify_state(lat: float, lon: float) -> tuple[str, str]:
    """Return (state, market) from coordinate bounding boxes."""
    if lon > -104.0 and lat < 36.5 and lon < -93.5:
        return 'TX', 'ERCOT'
    if -109.0 < lon <= -104.0 and lat < 37.0:
        return 'NM', 'ERCOT' if lon > -105.0 else 'WECC'
    if lon <= -109.0:
        return 'AZ', 'WECC'
    return 'TX', 'ERCOT'


# ── ERCOT hub assignment ───────────────────────────────────────────────────

_ERCOT_HUBS = {
    'HB_WEST':    (31.5, -102.5),
    'HB_NORTH':   (35.0, -101.5),
    'HB_SOUTH':   (29.5, -98.5),
    'HB_HOUSTON': (29.8, -95.4),
    'HB_BUSAVG':  (31.0, -100.0),
}
_CAISO_NODE = ('PALOVRDE_ASR-APND', 38.5)


def _nearest_ercot_node(lat: float, lon: float) -> tuple[str, float]:
    """Return (node_id, live_lmp_mwh) for the nearest ERCOT settlement hub."""
    best_node, best_d = 'HB_WEST', 9999.0
    for node, (nlat, nlon) in _ERCOT_HUBS.items():
        d = math.hypot(lat - nlat, lon - nlon)
        if d < best_d:
            best_node, best_d = node, d
    # Use live LMP from GridStatus cache; fall back to static defaults
    _STATIC_LMP = {'HB_WEST': 42.0, 'HB_NORTH': 40.0, 'HB_SOUTH': 43.0,
                   'HB_HOUSTON': 42.0, 'HB_BUSAVG': 41.5}
    live_lmp = get_live_lmp(best_node, fallback=_STATIC_LMP.get(best_node, 42.0))
    return best_node, live_lmp


# ── State-level medians (fallback when spatial index unavailable) ──────────

_STATE_MEDIANS = {
    'TX': dict(water_km=7.0, fiber_km=3.0, pipeline_km=1.0, substation_km=8.0,
               highway_km=4.0, interstate_pipeline_km=12.0, waha_distance_km=90.0,
               seismic_hazard=0.05, wildfire_risk=0.15, phmsa_incident_density=0.002,
               acres_available=1500.0, fema_zone='X', ownership_type='private',
               is_federal_wilderness=False, epa_attainment=True),
    'NM': dict(water_km=10.0, fiber_km=6.0, pipeline_km=2.0, substation_km=12.0,
               highway_km=6.0, interstate_pipeline_km=20.0, waha_distance_km=60.0,
               seismic_hazard=0.08, wildfire_risk=0.30, phmsa_incident_density=0.001,
               acres_available=1800.0, fema_zone='X', ownership_type='blm_federal',
               is_federal_wilderness=False, epa_attainment=True),
    'AZ': dict(water_km=5.0, fiber_km=2.0, pipeline_km=4.0, substation_km=10.0,
               highway_km=3.0, interstate_pipeline_km=30.0, waha_distance_km=280.0,
               seismic_hazard=0.12, wildfire_risk=0.45, phmsa_incident_density=0.0005,
               acres_available=800.0, fema_zone='X', ownership_type='state',
               is_federal_wilderness=False, epa_attainment=False),
}


# ── Main function ──────────────────────────────────────────────────────────

def extract_features(lat: float, lon: float) -> FeatureVector:
    """Return FeatureVector for arbitrary coordinate.

    Priority for each feature:
      1. Spatial KDTree index (real NHD / USGS / FEMA / pipeline data)
      2. Live market cache (EIA gas price, GridStatus LMP)
      3. State-level median fallback
    """
    state, market = _classify_state(lat, lon)
    medians = _STATE_MEDIANS[state]

    if market == 'ERCOT':
        ercot_node, lmp_mwh = _nearest_ercot_node(lat, lon)
    else:
        ercot_node = _CAISO_NODE[0]
        lmp_mwh    = _CAISO_NODE[1]

    # Spatial index lookups — None when index not loaded
    sp = _spatial.spatial_features(lat, lon)

    # Live Waha Hub gas price from EIA cache
    waha_price = get_live_waha_price()

    return FeatureVector(
        lat=lat, lon=lon, state=state, market=market,

        # Parcel characteristics (spatial index > median fallback)
        acres_available      = medians['acres_available'],
        fema_zone            = medians['fema_zone'],
        is_federal_wilderness= medians['is_federal_wilderness'],
        ownership_type       = sp['ownership_type'] or medians['ownership_type'],
        epa_attainment       = medians['epa_attainment'],

        # Infrastructure proximity (spatial index > median fallback)
        water_km      = sp['water_km']    if sp['water_km']    is not None else medians['water_km'],
        fiber_km      = medians['fiber_km'],     # no spatial layer yet
        pipeline_km   = sp['pipeline_km'] if sp['pipeline_km'] is not None else medians['pipeline_km'],
        substation_km = medians['substation_km'],  # no spatial layer yet
        highway_km    = medians['highway_km'],      # no spatial layer yet

        # Risk scores (spatial index > median fallback)
        seismic_hazard= sp['seismic_hazard'] if sp['seismic_hazard'] is not None else medians['seismic_hazard'],
        wildfire_risk = sp['wildfire_risk']  if sp['wildfire_risk']  is not None else medians['wildfire_risk'],

        # Gas supply features (static approximation)
        interstate_pipeline_km = medians['interstate_pipeline_km'],
        waha_distance_km       = medians['waha_distance_km'],
        phmsa_incident_density = medians['phmsa_incident_density'],

        # Live market data
        lmp_mwh    = lmp_mwh,
        ercot_node = ercot_node,
        waha_price = waha_price,
    )
