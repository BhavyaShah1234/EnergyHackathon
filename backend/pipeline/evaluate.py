"""evaluate_coordinate: the core sequential scoring pipeline.

evaluate_coordinate(lat, lon, weights?) -> SiteScorecard  (~200ms, sync)
stream_narration(scorecard, api_key)  -> AsyncGenerator[str]  (Claude SSE)
"""
from backend.features.extractor import extract_features
from backend.scoring.land import score_land, check_hard_disqualifiers
from backend.scoring.gas import score_gas
from backend.scoring.regime import classify_regime, RegimeState
from backend.scoring.power import score_power
from backend.scoring.topsis import topsis
from backend.scoring.cost import estimate_costs
from backend.scoring.scorecard import SiteScorecard

_CACHED_REGIME: RegimeState | None = None  # set by APScheduler background job


def get_cached_regime() -> RegimeState:
    if _CACHED_REGIME is not None:
        return _CACHED_REGIME
    return classify_regime(lmp_mean=42.0, lmp_std=12.0, wind_pct=0.28,
                            demand_mw=55000, reserve_margin=0.18)


def set_cached_regime(regime: RegimeState) -> None:
    global _CACHED_REGIME
    _CACHED_REGIME = regime


def evaluate_coordinate(
    lat: float,
    lon: float,
    weights: tuple = (0.30, 0.35, 0.35),
) -> SiteScorecard:
    fv = extract_features(lat, lon)

    reason = check_hard_disqualifiers(fv)
    if reason:
        return SiteScorecard(lat=lat, lon=lon,
                             hard_disqualified=True, disqualify_reason=reason)

    land_score, land_shap = score_land(fv)

    gas_score = score_gas(
        lat=fv.lat,
        lon=fv.lon,
        incident_density=fv.phmsa_incident_density,
        interstate_pipeline_km=fv.interstate_pipeline_km,
        waha_distance_km=fv.waha_distance_km,
    )

    regime = get_cached_regime()

    power_result = score_power(fv, regime)
    power_score  = power_result['power_score']

    composite = topsis(land_score, gas_score, power_score, weights)

    cost = estimate_costs(fv, land_score, power_score)

    return SiteScorecard(
        lat=lat, lon=lon,
        hard_disqualified=False, disqualify_reason=None,
        land_score=land_score, gas_score=gas_score,
        power_score=power_score, composite_score=composite,
        land_shap=land_shap,
        spread_p50_mwh=power_result['spread_p50_mwh'],
        spread_durability=power_result['spread_durability'],
        regime=regime.label, regime_proba=regime.proba,
        cost=cost,
    )


_NARRATION_SYSTEM = """You are a senior energy infrastructure analyst advising a data center development team.
Given a BTM site scorecard, write a concise executive summary with exactly three sections:
1. **Site overview**: what makes it strong or weak across land, gas, and power dimensions.
2. **Key risk**: which dimension is the binding constraint and why.
3. **Timing recommendation**: based on the current market regime and any news.
Be specific about numbers. Use markdown: **bold** key metrics and scores, bullet sub-points within a section where helpful. Keep each section to 2-3 sentences."""


async def stream_narration(scorecard: SiteScorecard, api_key: str):
    """Yield Claude text chunks for the scorecard narrative. Requires ANTHROPIC_API_KEY."""
    import anthropic
    if not api_key:
        yield "Narrative unavailable — set ANTHROPIC_API_KEY in .env"
        return

    client = anthropic.AsyncAnthropic(api_key=api_key)
    cost = scorecard.cost

    user_msg = f"""
Site: ({scorecard.lat:.4f}, {scorecard.lon:.4f})
Land score: {scorecard.land_score:.3f}
Gas score:  {scorecard.gas_score:.3f}
Power score:{scorecard.power_score:.3f}
Composite:  {scorecard.composite_score:.3f}
Regime:     {scorecard.regime}
BTM spread P50: ${scorecard.spread_p50_mwh:.1f}/MWh
Spread durability: {scorecard.spread_durability:.0%} of trailing 90 days positive
NPV P10/P50/P90: ${cost.npv_p10_m:.0f}M / ${cost.npv_p50_m:.0f}M / ${cost.npv_p90_m:.0f}M
Key land factors: {scorecard.land_shap}
Disqualified: {scorecard.hard_disqualified}
""".strip()

    async with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=512,
        system=_NARRATION_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        async for text in stream.text_stream:
            yield text
