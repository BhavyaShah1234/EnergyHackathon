"""Sub-C: BTM Power Economics scorer."""
from backend.data.sites import Site
from backend.scoring.sub_b import GAS_HUB_PRICES

# Grid LMP reference ($/MWh) — price you'd pay buying from the grid
GRID_LMP_REF = 42.0

# Modern gas turbine heat rate (MMBtu/MWh)
HEAT_RATE = 8.5  # CCGT standard (was 7.5 — incorrect per spec)

# Fixed O&M proxy ($/MWh) — must match power.py
OM_COST = 3.0


def _estimated_btm_cost(gas_price: float) -> float:
    """All-in BTM power generation cost in $/MWh (fuel + O&M)."""
    return gas_price * HEAT_RATE + OM_COST


def score(
    site: Site,
    live_gas_price: float | None = None,
    live_lmp: float | None = None,
) -> float:
    """Return 0–1 BTM power economics score.

    Weights:
      60%  gas-to-power spread  (BTM cost vs grid LMP — larger = better)
      40%  absolute BTM cost    (lower $/MWh = better)
    """
    gas_price = live_gas_price or GAS_HUB_PRICES.get(site.gas_hub, 3.41)
    lmp       = live_lmp or site.lmp or GRID_LMP_REF

    btm_cost = _estimated_btm_cost(gas_price)
    spread   = lmp - btm_cost  # positive = BTM cheaper than buying from grid

    # $20/MWh spread = perfect score; negative = 0
    spread_score = min(max(spread / 20.0, 0.0), 1.0)

    # $20/MWh = perfect cost; $40/MWh = 0
    cost_score = max(0.0, 1.0 - (btm_cost - 20.0) / 20.0)

    raw = spread_score * 0.60 + cost_score * 0.40
    return round(min(max(raw, 0.0), 1.0), 4)
