"""Sub-B: Gas Supply Reliability scorer."""
from backend.data.sites import Site

# Henry Hub reference ($/MMBtu) — used to compute Waha discount
HENRY_HUB_REF = 3.41

# Approximate gas prices by hub
GAS_HUB_PRICES = {
    "Waha":         1.84,
    "Panhandle EP": 1.90,
    "SoCal Gas":    3.10,
}

# Pipeline failure risk proxy: lower index = more reliable grid
PIPELINE_RELIABILITY = {
    "TX": 0.92,
    "NM": 0.87,
    "AZ": 0.74,
}


def score(site: Site, live_gas_price: float | None = None) -> float:
    """Return 0-1 gas supply reliability score.

    Weights:
      30%  pipeline proximity (0-5 km range)
      30%  Waha discount vs Henry Hub (larger discount = better)
      25%  state-level pipeline reliability
      15%  hub diversity (Waha / Panhandle preferred over SoCal)
    """
    hub_price = live_gas_price or GAS_HUB_PRICES.get(site.gas_hub, HENRY_HUB_REF)

    # Pipeline proximity
    pipeline_score = max(0.0, 1.0 - site.pipeline_km / 5.0)

    # Gas price advantage (discount from Henry Hub)
    discount = max(0.0, HENRY_HUB_REF - hub_price)
    price_score = min(discount / 2.0, 1.0)  # $2 discount = perfect

    # State reliability
    reliability = PIPELINE_RELIABILITY.get(site.state, 0.80)

    # Hub diversity bonus (Waha/Permian Basin hubs preferred)
    hub_score = 0.95 if site.gas_hub in ("Waha", "Panhandle EP") else 0.55

    raw = (
        pipeline_score * 0.30 +
        price_score    * 0.30 +
        reliability    * 0.25 +
        hub_score      * 0.15
    )
    return round(min(max(raw, 0.0), 1.0), 4)
