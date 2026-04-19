"""Composite scoring engine — runs Sub-A + Sub-B + Sub-C."""
from dataclasses import dataclass

from backend.data.sites import Site, CANDIDATE_SITES
from backend.scoring import sub_a, sub_b, sub_c
from backend.scoring.sub_b import GAS_HUB_PRICES
from backend.scoring.sub_c import _estimated_btm_cost

# Composite weights  (must sum to 1.0)
W_A, W_B, W_C = 0.30, 0.35, 0.35


@dataclass
class SiteScore:
    site: Site
    sub_a: float
    sub_b: float
    sub_c: float
    composite: float
    est_power_cost_mwh: float
    rank: int = 0


def _composite(a: float, b: float, c: float) -> float:
    return round(a * W_A + b * W_B + c * W_C, 4)


def score_site(
    site: Site,
    live_gas_price: float | None = None,
    live_lmp: float | None = None,
) -> SiteScore:
    a = sub_a.score(site)
    b = sub_b.score(site, live_gas_price)
    c = sub_c.score(site, live_gas_price, live_lmp)

    gas_p = live_gas_price or GAS_HUB_PRICES.get(site.gas_hub, 3.41)

    return SiteScore(
        site=site,
        sub_a=a,
        sub_b=b,
        sub_c=c,
        composite=_composite(a, b, c),
        est_power_cost_mwh=round(_estimated_btm_cost(gas_p), 2),
    )


def score_all(
    live_gas_price: float | None = None,
    live_lmp: float | None = None,
) -> list[SiteScore]:
    results = [score_site(s, live_gas_price, live_lmp) for s in CANDIDATE_SITES]
    results.sort(key=lambda x: x.composite, reverse=True)
    for i, r in enumerate(results):
        r.rank = i + 1
    return results
