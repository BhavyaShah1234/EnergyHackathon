"""Sub-A: Land & Lease Viability scorer."""
from backend.data.sites import Site


def score(site: Site) -> float:
    """Return 0-1 land viability score.

    Weights:
      35%  parcel size (1000+ acres = perfect)
      25%  land cost per acre (lower = better; $500 floor, $3000 cap)
      20%  fiber proximity (0-10 km range)
      12%  water proximity (0-15 km range)
       8%  federal land penalty (private = 1.0, public = 0.3)
    """
    # Parcel size
    acres_score = min(site.acres / 1000.0, 1.0)

    # Land cost (lower is better)
    cost_score = max(0.0, 1.0 - (site.land_cost_per_acre - 500) / 2500.0)

    # Fiber proximity (closer = better)
    fiber_score = max(0.0, 1.0 - site.fiber_km / 10.0)

    # Water proximity
    water_score = max(0.0, 1.0 - site.water_km / 15.0)

    # Federal/private land (heuristic: AZ state land harder to permit)
    ownership_score = 0.7 if site.state == "AZ" else 1.0

    raw = (
        acres_score    * 0.35 +
        cost_score     * 0.25 +
        fiber_score    * 0.20 +
        water_score    * 0.12 +
        ownership_score * 0.08
    )
    return round(min(max(raw, 0.0), 1.0), 4)
