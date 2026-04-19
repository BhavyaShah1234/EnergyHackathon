"""Shared in-memory cache for live market prices.

Written by APScheduler background jobs in main.py.
Read by features/extractor.py and scoring/power.py.
Kept in its own module to avoid circular imports
(ingest ← features ← scoring ← pipeline ← main would otherwise loop).
"""
from datetime import datetime, timezone

# ── Live gas prices (EIA) ──────────────────────────────────────────────────
_gas_price_waha:  float = 1.84   # $/MMBtu — Waha Hub
_gas_price_henry: float = 3.41   # $/MMBtu — Henry Hub
_gas_fetched_at:  str   = ""


def get_live_waha_price() -> float:
    return _gas_price_waha


def get_live_henry_price() -> float:
    return _gas_price_henry


def set_live_gas_prices(waha: float, henry: float) -> None:
    global _gas_price_waha, _gas_price_henry, _gas_fetched_at
    _gas_price_waha  = max(waha,  0.01)
    _gas_price_henry = max(henry, 0.01)
    _gas_fetched_at  = datetime.now(timezone.utc).isoformat()


# ── Live ERCOT LMP by hub (GridStatus) ────────────────────────────────────
_lmp_by_hub: dict[str, float] = {
    'HB_WEST':   42.0,
    'HB_NORTH':  40.0,
    'HB_SOUTH':  43.0,
    'HB_BUSAVG': 41.5,
    'HB_HUBAVG': 41.5,
    'HB_HOUSTON': 42.0,
    'HB_PAN':    38.0,
}
_lmp_fetched_at: str = ""


def get_live_lmp(hub: str, fallback: float = 42.0) -> float:
    return _lmp_by_hub.get(hub, fallback)


def get_all_live_lmp() -> dict[str, float]:
    return dict(_lmp_by_hub)


def set_live_lmp(lmp_by_hub: dict[str, float]) -> None:
    global _lmp_by_hub, _lmp_fetched_at
    _lmp_by_hub = {**_lmp_by_hub, **lmp_by_hub}
    _lmp_fetched_at = datetime.now(timezone.utc).isoformat()


def cache_status() -> dict:
    return {
        "waha_price":    _gas_price_waha,
        "henry_price":   _gas_price_henry,
        "gas_fetched_at": _gas_fetched_at,
        "lmp_by_hub":    _lmp_by_hub,
        "lmp_fetched_at": _lmp_fetched_at,
    }
