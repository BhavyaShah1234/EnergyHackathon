"""Core sequential scoring pipeline.

evaluate_coordinate(lat, lon, weights?)         -> SiteScorecard  (sync, ~50ms)
evaluate_coordinate_enriched(lat, lon, weights,
  tavily_key, anthropic_key)                    -> SiteScorecard  (async, ~2-4s)

The sync variant is used by /api/optimize (tight grid loop).
The async variant is used by /api/evaluate (single-site SSE stream) and adds:
  - Tavily web search for zoning / pipeline news
  - Claude Haiku reasoning → land_adjustment + pipeline_score
  - stream_narration with web context included
"""
from backend.features.extractor import extract_features
from backend.features import spatial as _spatial
from backend.scoring.land import score_land, check_hard_disqualifiers
from backend.scoring.gas import score_gas
from backend.scoring.regime import classify_regime, RegimeState
from backend.scoring.power import score_power
from backend.scoring.topsis import topsis
from backend.scoring.cost import estimate_costs
from backend.scoring.scorecard import SiteScorecard
from backend.ingest.cache import get_live_waha_price, get_live_lmp

_CACHED_REGIME: RegimeState | None = None


def get_cached_regime() -> RegimeState:
    if _CACHED_REGIME is not None:
        return _CACHED_REGIME
    return classify_regime(lmp_mean=42.0, lmp_std=12.0, wind_pct=0.28,
                           demand_mw=55000, reserve_margin=0.18)


def set_cached_regime(regime: RegimeState) -> None:
    global _CACHED_REGIME
    _CACHED_REGIME = regime


# ── Sync scorer (used by /api/optimize grid sweep) ─────────────────────────

def evaluate_coordinate(
    lat: float,
    lon: float,
    weights: tuple = (0.30, 0.35, 0.35),
) -> SiteScorecard:
    """Score a coordinate using cached live prices. No web context (sync-safe)."""
    fv = extract_features(lat, lon)

    reason = check_hard_disqualifiers(fv)
    if reason:
        return SiteScorecard(lat=lat, lon=lon,
                             hard_disqualified=True, disqualify_reason=reason)

    land_score, land_shap = score_land(fv)

    gas_score = score_gas(
        lat=fv.lat, lon=fv.lon,
        incident_density=fv.phmsa_incident_density,
        interstate_pipeline_km=fv.interstate_pipeline_km,
        waha_distance_km=fv.waha_distance_km,
        pipeline_web_score=None,  # no web context in sync path
    )

    regime      = get_cached_regime()
    power_result = score_power(fv, regime)
    power_score  = power_result['power_score']

    composite = topsis(land_score, gas_score, power_score, weights)
    cost      = estimate_costs(fv, land_score, power_score)

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
        live_gas_price=fv.waha_price,
        live_lmp_mwh=fv.lmp_mwh,
    )


# ── Async enriched scorer (used by /api/evaluate single-site call) ─────────

async def evaluate_coordinate_enriched(
    lat: float,
    lon: float,
    weights: tuple = (0.30, 0.35, 0.35),
    tavily_key: str = "",
    anthropic_key: str = "",
) -> SiteScorecard:
    """Score a coordinate with Tavily + Claude web context enrichment.

    Steps:
      1. extract_features() — same as sync path
      2. fetch_web_context() — Tavily search + Claude Haiku reasoning (async)
      3. score_land() + apply web land_adjustment (bounded [-0.10, +0.10])
      4. score_gas() with web pipeline_score blended in at 20%
      5. score_power(), topsis(), estimate_costs() — unchanged
    """
    from backend.scoring.web_context import fetch_web_context

    fv = extract_features(lat, lon)

    reason = check_hard_disqualifiers(fv)
    if reason:
        return SiteScorecard(lat=lat, lon=lon,
                             hard_disqualified=True, disqualify_reason=reason)

    # Fetch pipeline proximity info for web context query
    pipe_info = _spatial.nearest_pipeline_info(lat, lon)

    # Run ML scoring and web context fetch concurrently
    import asyncio
    (land_score_raw, land_shap), web_ctx = await asyncio.gather(
        asyncio.to_thread(score_land, fv),
        fetch_web_context(lat, lon, pipe_info, tavily_key, anthropic_key),
    )

    # Apply web land adjustment — bounded so ML score stays primary
    land_score = round(max(0.0, min(1.0, land_score_raw + web_ctx.land_adjustment)), 4)

    gas_score = score_gas(
        lat=fv.lat, lon=fv.lon,
        incident_density=fv.phmsa_incident_density,
        interstate_pipeline_km=fv.interstate_pipeline_km,
        waha_distance_km=fv.waha_distance_km,
        pipeline_web_score=web_ctx.pipeline_score if web_ctx.fetched else None,
    )

    regime       = get_cached_regime()
    power_result = score_power(fv, regime)
    power_score  = power_result['power_score']

    composite = topsis(land_score, gas_score, power_score, weights)
    cost      = estimate_costs(fv, land_score, power_score)

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
        # Web context fields
        web_land_adjustment=web_ctx.land_adjustment,
        web_pipeline_score=web_ctx.pipeline_score if web_ctx.fetched else None,
        web_land_reasoning=web_ctx.land_reasoning,
        web_pipeline_reasoning=web_ctx.pipeline_reasoning,
        web_sources=web_ctx.sources,
        web_fetched=web_ctx.fetched,
        # Live market provenance
        live_gas_price=fv.waha_price,
        live_lmp_mwh=fv.lmp_mwh,
    )


# ── Narration ──────────────────────────────────────────────────────────────

_NARRATION_SYSTEM = """You are a senior energy infrastructure analyst advising a data center development team.
Given a BTM site scorecard, write a concise executive summary with exactly three sections:
1. **Site overview**: what makes it strong or weak across land, gas, and power dimensions.
2. **Key risk**: which dimension is the binding constraint and why.
3. **Timing recommendation**: based on the current market regime, live prices, and any web intelligence.
Be specific about numbers. Use markdown: **bold** key metrics and scores, bullet sub-points within a section where helpful. Keep each section to 2-3 sentences."""


async def stream_narration(scorecard: SiteScorecard, api_key: str):
    """Yield Claude text chunks for the scorecard narrative."""
    import anthropic
    if not api_key:
        yield "Narrative unavailable — set ANTHROPIC_API_KEY in .env"
        return

    client = anthropic.AsyncAnthropic(api_key=api_key)
    cost = scorecard.cost

    # Build web context section only if real data was fetched
    web_section = ""
    if scorecard.web_fetched:
        web_section = f"""
Web intelligence (Tavily):
  Land context: {scorecard.web_land_reasoning or 'n/a'} (adjustment: {scorecard.web_land_adjustment:+.2f})
  Pipeline: {scorecard.web_pipeline_reasoning or 'n/a'} (operator score: {f'{scorecard.web_pipeline_score:.2f}' if scorecard.web_pipeline_score is not None else 'n/a'})
  Sources: {', '.join(s.get('title','') for s in scorecard.web_sources[:3])}"""

    user_msg = f"""
Site: ({scorecard.lat:.4f}, {scorecard.lon:.4f})
Land score: {scorecard.land_score:.3f} (ML raw {scorecard.land_score - scorecard.web_land_adjustment:.3f}, web adj {scorecard.web_land_adjustment:+.3f})
Gas score:  {scorecard.gas_score:.3f}
Power score:{scorecard.power_score:.3f}
Composite:  {scorecard.composite_score:.3f}
Regime:     {scorecard.regime}
Live Waha gas price: ${scorecard.live_gas_price:.2f}/MMBtu
Live LMP at hub: ${scorecard.live_lmp_mwh:.1f}/MWh
BTM spread P50: ${scorecard.spread_p50_mwh:.1f}/MWh
Spread durability: {scorecard.spread_durability:.0%}
NPV P10/P50/P90: ${cost.npv_p10_m:.0f}M / ${cost.npv_p50_m:.0f}M / ${cost.npv_p90_m:.0f}M
Key land SHAP: {scorecard.land_shap}{web_section}
""".strip()

    async with client.messages.stream(
        model="claude-opus-4-7",
        max_tokens=600,
        system=_NARRATION_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    ) as stream:
        async for text in stream.text_stream:
            yield text
