"""COLLIDE Platform — FastAPI scoring engine."""
import asyncio
import json
import sys
import types
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sse_starlette.sse import EventSourceResponse

# Vercel can materialize Python entrypoints either as a package module
# (backend/main.py) or as a flat file (/var/task/main.py). Registering a
# lightweight "backend" package alias keeps absolute imports working in both.
if "backend" not in sys.modules:
    backend_pkg = types.ModuleType("backend")
    backend_pkg.__path__ = [str(Path(__file__).resolve().parent)]
    sys.modules["backend"] = backend_pkg

from backend.config import get_settings
from backend.data.sites import CANDIDATE_SITES
from backend.ingest.eia_gas import fetch_gas_prices
from backend.ingest.caiso_lmp import fetch_all_nodes
from backend.ingest.eia_demand import fetch_all_bas
from backend.ingest.gridstatus import fetch_ercot_snapshot
from backend.ingest.cache import set_live_gas_prices, set_live_lmp, cache_status
from backend.scoring.engine import score_all, score_site
from backend.scoring.sub_b import GAS_HUB_PRICES
from backend.scoring.power import HEAT_RATE as PWR_HEAT_RATE, OM_COST as PWR_OM_COST
from backend.pipeline.runner import run_pipeline
from backend.pipeline.evaluate import (
    evaluate_coordinate, evaluate_coordinate_enriched,
    stream_narration, get_cached_regime, set_cached_regime,
)
from backend.scoring.regime import classify_regime


settings = get_settings()
scheduler = AsyncIOScheduler()
_news_cache: dict = {"items": [], "fetched_at": ""}


# ── Background jobs ────────────────────────────────────────────────────────

async def _refresh_regime():
    """Refresh market regime + cache live LMP and gas prices every 5 min."""
    # GridStatus: live ERCOT LMP + fuel mix
    snapshot = await fetch_ercot_snapshot(settings.gridstatus_api_key)
    fm  = snapshot['fuel_mix']
    lmp = snapshot['lmp']
    lmp_mean = sum(lmp.values()) / max(len(lmp), 1)

    regime = classify_regime(
        lmp_mean=lmp_mean, lmp_std=lmp_mean * 0.25,
        wind_pct=fm.get('wind', 0.28),
        demand_mw=55000, reserve_margin=0.18,
    )
    set_cached_regime(regime)

    # Cache live LMP for use in extract_features()
    set_live_lmp(lmp)

    # EIA: live gas prices (Henry Hub → Waha derivation)
    try:
        gas = await fetch_gas_prices(settings.eia_api_key)
        set_live_gas_prices(
            waha=gas.get('waha_hub', 1.84),
            henry=gas.get('henry_hub', 3.41),
        )
    except Exception:
        pass  # keep previous cached value


async def _refresh_news():
    global _news_cache
    api_key = settings.tavily_api_key
    if not api_key:
        return
    try:
        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)
        results = client.search("BTM natural gas data center energy Texas", max_results=3)
        _news_cache = {
            "items": [{"title": r["title"], "url": r["url"], "snippet": r["content"][:200]}
                      for r in results.get("results", [])],
            "fetched_at": __import__('datetime').datetime.utcnow().isoformat(),
        }
    except Exception:
        pass


app = FastAPI(title="COLLIDE Scoring API", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    scheduler.add_job(_refresh_regime, 'interval', seconds=settings.regime_refresh_secs)
    scheduler.add_job(_refresh_news,   'interval', seconds=settings.news_refresh_secs)
    scheduler.start()


@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()


# ── Response models ────────────────────────────────────────────────────────

class ScoreResponse(BaseModel):
    id: str
    name: str
    location: str
    state: str
    market: str
    lat: float
    lng: float
    acres: int
    land_cost_per_acre: int
    fiber_km: float
    water_km: float
    pipeline_km: float
    gas_hub: str
    gas_price: float
    lmp_node: str
    lmp: float | None
    est_power_cost_mwh: float
    total_land_cost_m: float
    scores: dict[str, float]
    rank: int


class MarketResponse(BaseModel):
    gas: dict[str, Any]
    lmp: dict[str, Any]
    demand: dict[str, Any]


class EvaluateRequest(BaseModel):
    lat: float
    lon: float
    weights: tuple[float, float, float] = (0.30, 0.35, 0.35)


class OptimizeRequest(BaseModel):
    bounds: dict
    weights: tuple[float, float, float] = (0.30, 0.35, 0.35)
    grid_steps: int = 8
    max_sites: int = 3
    gas_price_max: float | None = None
    power_cost_max: float | None = None
    acres_min: int = 0
    market_filter: list[str] = []
    min_composite: float = 0.0


# ── Helpers ────────────────────────────────────────────────────────────────

def _build_site_response(site, sc, rank: int = 0) -> ScoreResponse:
    """Build a ScoreResponse using System B (ML+TOPSIS) scorecard data."""
    # Use hub-appropriate gas price for display; BTM economics always use Waha (per model)
    gas_price_display = sc.live_gas_price if site.gas_hub == "Waha" else GAS_HUB_PRICES.get(site.gas_hub, 3.41)
    btm_cost_display = round(gas_price_display * PWR_HEAT_RATE + PWR_OM_COST, 2)
    return ScoreResponse(
        id=site.id,
        name=site.name,
        location=site.location,
        state=site.state,
        market=site.market,
        lat=site.lat,
        lng=site.lng,
        acres=site.acres,
        land_cost_per_acre=site.land_cost_per_acre,
        fiber_km=site.fiber_km,
        water_km=site.water_km,
        pipeline_km=site.pipeline_km,
        gas_hub=site.gas_hub,
        gas_price=round(gas_price_display, 2),
        lmp_node=site.lmp_node,
        lmp=site.lmp,
        est_power_cost_mwh=btm_cost_display,
        total_land_cost_m=round(site.acres * site.land_cost_per_acre / 1_000_000, 2),
        scores={
            "land": round(sc.land_score, 4),
            "gas": round(sc.gas_score, 4),
            "power": round(sc.power_score, 4),
            "composite": round(sc.composite_score, 4),
        },
        rank=rank,
    )


async def _fetch_market_inputs(api_key: str) -> tuple[dict, dict]:
    gas_data, lmp_data = await asyncio.gather(
        fetch_gas_prices(api_key),
        fetch_all_nodes(),
    )
    return gas_data, lmp_data


# ── Existing endpoints (unchanged) ─────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "collide-scoring-api"}


@app.get("/api/sites", response_model=list[ScoreResponse])
async def get_sites():
    """Return candidate sites with enriched System B scoring, identical to /api/evaluate click-through.

    Uses the same evaluate_coordinate_enriched() path as the side panel so popup and panel
    scores always match. Web context is cached at 0.5° resolution so only the first request
    per grid cell makes external API calls.
    """
    scorecards = await asyncio.gather(*[
        evaluate_coordinate_enriched(
            s.lat, s.lng,
            tavily_key=settings.tavily_api_key,
            anthropic_key=settings.anthropic_api_key,
        )
        for s in CANDIDATE_SITES
    ])
    responses = [
        _build_site_response(site, sc)
        for site, sc in zip(CANDIDATE_SITES, scorecards)
    ]
    responses.sort(key=lambda r: r.scores["composite"], reverse=True)
    for i, r in enumerate(responses):
        r.rank = i + 1
    return responses


@app.get("/api/sites/{site_id}", response_model=ScoreResponse)
async def get_site(site_id: str):
    """Return System B scored detail for a single candidate site."""
    site = next((s for s in CANDIDATE_SITES if s.id == site_id), None)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")
    sc = await evaluate_coordinate_enriched(
        site.lat, site.lng,
        tavily_key=settings.tavily_api_key,
        anthropic_key=settings.anthropic_api_key,
    )
    return _build_site_response(site, sc, rank=1)


@app.get("/api/market", response_model=MarketResponse)
async def get_market():
    """Return live gas prices, LMPs, and BA demand."""
    gas, lmp, demand = await asyncio.gather(
        fetch_gas_prices(settings.eia_api_key),
        fetch_all_nodes(),
        fetch_all_bas(settings.eia_api_key),
    )
    return MarketResponse(gas=gas, lmp=lmp, demand=demand)


@app.post("/api/pipeline/run")
async def trigger_pipeline() -> dict:
    """Trigger a full ingest → validate → silver lake → score pipeline run."""
    return await run_pipeline(settings.eia_api_key)


# ── New endpoints ──────────────────────────────────────────────────────────

@app.post("/api/evaluate")
async def api_evaluate(req: EvaluateRequest):
    async def generate():
        # Use enriched async path: Tavily + Claude web context runs concurrently
        # with ML scoring. Falls back gracefully when API keys missing.
        sc = await evaluate_coordinate_enriched(
            req.lat, req.lon, req.weights,
            tavily_key=settings.tavily_api_key,
            anthropic_key=settings.anthropic_api_key,
        )

        payload = {
            "lat": sc.lat, "lon": sc.lon,
            "hard_disqualified": sc.hard_disqualified,
            "disqualify_reason": sc.disqualify_reason,
            "land_score": sc.land_score, "gas_score": sc.gas_score,
            "power_score": sc.power_score, "composite_score": sc.composite_score,
            "land_shap": sc.land_shap,
            "spread_p50_mwh": sc.spread_p50_mwh,
            "spread_durability": sc.spread_durability,
            "regime": sc.regime, "regime_proba": sc.regime_proba,
            "live_gas_price": sc.live_gas_price,
            "live_lmp_mwh": sc.live_lmp_mwh,
            "cost": {
                "land_acquisition_m": sc.cost.land_acquisition_m if sc.cost else 0,
                "pipeline_connection_m": sc.cost.pipeline_connection_m if sc.cost else 0,
                "water_connection_m": sc.cost.water_connection_m if sc.cost else 0,
                "btm_capex_m": sc.cost.btm_capex_m if sc.cost else 0,
                "npv_p10_m": sc.cost.npv_p10_m if sc.cost else 0,
                "npv_p50_m": sc.cost.npv_p50_m if sc.cost else 0,
                "npv_p90_m": sc.cost.npv_p90_m if sc.cost else 0,
            } if sc.cost else None,
        }
        yield {"event": "scorecard", "data": json.dumps(payload)}

        # Emit web context event when real Tavily data was fetched
        if sc.web_fetched:
            web_payload = {
                "land_adjustment":    sc.web_land_adjustment,
                "pipeline_score":     sc.web_pipeline_score,
                "land_reasoning":     sc.web_land_reasoning,
                "pipeline_reasoning": sc.web_pipeline_reasoning,
                "sources":            sc.web_sources[:5],
            }
            yield {"event": "web_context", "data": json.dumps(web_payload)}

        if not sc.hard_disqualified:
            async for chunk in stream_narration(sc, settings.anthropic_api_key):
                yield {"event": "narrative", "data": json.dumps(chunk)}

        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(generate())


@app.post("/api/optimize")
async def api_optimize(req: OptimizeRequest):
    async def generate():
        sw = req.bounds["sw"]
        ne = req.bounds["ne"]
        steps = req.grid_steps

        lat_grid = [sw["lat"] + (ne["lat"] - sw["lat"]) * i / (steps - 1) for i in range(steps)]
        lon_grid = [sw["lon"] + (ne["lon"] - sw["lon"]) * j / (steps - 1) for j in range(steps)]

        candidates = []
        total = steps * steps
        count = 0

        for lat in lat_grid:
            for lon in lon_grid:
                sc = evaluate_coordinate(lat, lon, req.weights)
                count += 1
                yield {
                    "event": "progress",
                    "data": json.dumps({
                        "lat": lat, "lon": lon,
                        "composite_score": sc.composite_score,
                        "pct": round(count / total * 100),
                    }),
                }
                if sc.hard_disqualified:
                    await asyncio.sleep(0)
                    continue
                if sc.composite_score < req.min_composite:
                    await asyncio.sleep(0)
                    continue
                # Apply gas/power cost filters (previously dead code — now active)
                btm_cost = sc.live_gas_price * PWR_HEAT_RATE + PWR_OM_COST
                if req.gas_price_max is not None and sc.live_gas_price > req.gas_price_max:
                    await asyncio.sleep(0)
                    continue
                if req.power_cost_max is not None and btm_cost > req.power_cost_max:
                    await asyncio.sleep(0)
                    continue
                candidates.append(sc)
                await asyncio.sleep(0)

        candidates.sort(key=lambda s: s.composite_score, reverse=True)
        top_raw = candidates[:req.max_sites]

        # Enrich top candidates with web context so scores match /api/evaluate click-through
        if top_raw:
            enriched = await asyncio.gather(*[
                evaluate_coordinate_enriched(
                    sc.lat, sc.lon, req.weights,
                    tavily_key=settings.tavily_api_key,
                    anthropic_key=settings.anthropic_api_key,
                )
                for sc in top_raw
            ])
            top_final = sorted(enriched, key=lambda s: s.composite_score, reverse=True)
        else:
            top_final = top_raw

        for sc in top_final:
            payload = {
                "lat": sc.lat, "lon": sc.lon,
                "composite_score": sc.composite_score,
                "land_score": sc.land_score,
                "gas_score": sc.gas_score,
                "power_score": sc.power_score,
            }
            yield {"event": "optimal", "data": json.dumps(payload)}

        yield {"event": "done", "data": "{}"}

    return EventSourceResponse(generate())


@app.get("/api/regime")
async def api_regime():
    r = get_cached_regime()
    return {"label": r.label, "proba": r.proba, "labels": r.labels}


# ── /api/forecast ──────────────────────────────────────────────────────────

class ForecastResponse(BaseModel):
    node: str
    horizon: int
    p10: list[float]
    p50: list[float]
    p90: list[float]
    btm_cost_mwh: float
    method: str


@app.get("/api/forecast", response_model=ForecastResponse)
async def api_forecast(node: str = "HB_WEST", horizon: int = 72):
    """Return Moirai P10/P50/P90 LMP forecast for a node (served from cache)."""
    from backend.scoring.power import get_forecast, HEAT_RATE, OM_COST
    fc = get_forecast(node)
    waha_price = 1.84
    btm_cost = waha_price * HEAT_RATE + OM_COST
    if fc is not None:
        h = min(horizon, len(fc['p50']))
        return ForecastResponse(
            node=node, horizon=h,
            p10=fc['p10'][:h].tolist() if hasattr(fc['p10'], 'tolist') else list(fc['p10'][:h]),
            p50=fc['p50'][:h].tolist() if hasattr(fc['p50'], 'tolist') else list(fc['p50'][:h]),
            p90=fc['p90'][:h].tolist() if hasattr(fc['p90'], 'tolist') else list(fc['p90'][:h]),
            btm_cost_mwh=round(btm_cost, 2),
            method=fc.get('method', 'cache'),
        )
    base = 42.0
    flat_p50 = [base] * horizon
    return ForecastResponse(
        node=node, horizon=horizon,
        p10=[base - 8] * horizon, p50=flat_p50, p90=[base + 8] * horizon,
        btm_cost_mwh=round(btm_cost, 2), method='fallback',
    )


# ── /api/heatmap ────────────────────────────────────────────────────────────

VALID_LAYERS = {'composite', 'gas', 'lmp'}


@app.get("/api/heatmap")
async def api_heatmap(layer: str = "composite", bounds: str = "", zoom: int = 8):
    """Return GeoJSON FeatureCollection of System B scored points for a map heat layer."""
    if layer not in VALID_LAYERS:
        return {"type": "FeatureCollection", "features": []}

    scorecards = await asyncio.gather(
        *[asyncio.to_thread(evaluate_coordinate, s.lat, s.lng) for s in CANDIDATE_SITES]
    )
    score_key = {
        'composite': lambda sc: sc.composite_score,
        'gas':       lambda sc: sc.gas_score,
        'lmp':       lambda sc: sc.power_score,
    }[layer]

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [site.lng, site.lat]},
            "properties": {
                "score": round(score_key(sc), 4),
                "layer": layer,
                "name": site.name,
            },
        }
        for site, sc in zip(CANDIDATE_SITES, scorecards)
    ]
    return {"type": "FeatureCollection", "features": features}


# ── /api/compare ────────────────────────────────────────────────────────────

@app.get("/api/compare")
async def api_compare(coords: str):
    """Evaluate N coordinates and return ranked scorecards.

    coords: semicolon-separated 'lat,lon' pairs, e.g. '31.9,-102.1;32.5,-101.2'
    """
    pairs = []
    for part in coords.split(';'):
        part = part.strip()
        if not part:
            continue
        try:
            lat_s, lon_s = part.split(',')
            pairs.append((float(lat_s.strip()), float(lon_s.strip())))
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Invalid coord pair: '{part}'")

    if not pairs:
        raise HTTPException(status_code=422, detail="No valid coordinate pairs provided")
    if len(pairs) > 5:
        raise HTTPException(status_code=422, detail="Maximum 5 coordinates per compare request")

    scorecards = await asyncio.gather(*[
        evaluate_coordinate_enriched(
            lat, lon,
            tavily_key=settings.tavily_api_key,
            anthropic_key=settings.anthropic_api_key,
        )
        for lat, lon in pairs
    ])
    results = []
    for sc in scorecards:
        results.append({
            "lat": sc.lat, "lon": sc.lon,
            "composite_score": sc.composite_score,
            "land_score": sc.land_score,
            "gas_score": sc.gas_score,
            "power_score": sc.power_score,
            "regime": sc.regime,
            "spread_p50_mwh": sc.spread_p50_mwh,
            "spread_durability": sc.spread_durability,
            "disqualified": sc.hard_disqualified,
            "disqualify_reason": sc.disqualify_reason,
            "cost": {
                "npv_p10_m": sc.cost.npv_p10_m if sc.cost else 0,
                "npv_p50_m": sc.cost.npv_p50_m if sc.cost else 0,
                "npv_p90_m": sc.cost.npv_p90_m if sc.cost else 0,
                "btm_capex_m": sc.cost.btm_capex_m if sc.cost else 0,
                "land_acquisition_m": sc.cost.land_acquisition_m if sc.cost else 0,
                "pipeline_connection_m": sc.cost.pipeline_connection_m if sc.cost else 0,
                "water_connection_m": sc.cost.water_connection_m if sc.cost else 0,
            } if sc.cost else None,
        })

    results.sort(key=lambda x: x['composite_score'], reverse=True)
    return results


@app.get("/api/news")
async def api_news():
    return _news_cache


@app.get("/api/cache/status")
async def api_cache_status():
    """Return current state of live-price and regime caches (observability endpoint)."""
    regime = get_cached_regime()
    return {
        "prices": cache_status(),
        "regime": {"label": regime.label, "proba": regime.proba},
    }


class AgentRequest(BaseModel):
    query: str
    context: dict = {}   # {scorecard?, bounds?, regime?} from frontend


@app.post("/api/agent")
async def api_agent(req: AgentRequest):
    async def generate():
        from backend.agent.graph import get_agent
        agent = get_agent()
        initial_state = {
            'query': req.query,
            'context': req.context,
            'intent': '',
            'needs_web_search': False,
            'tool_results': [],
            'citations': [],
            'final_response': '',
        }
        try:
            async for event in agent.astream(initial_state):
                for node_name, node_output in event.items():
                    if node_name == 'synthesize' and node_output.get('final_response'):
                        response_text = node_output['final_response']
                        chunk_size = 4
                        for i in range(0, len(response_text), chunk_size):
                            yield {"event": "token", "data": json.dumps(response_text[i:i+chunk_size])}
                    elif node_name == 'config':
                        for result in node_output.get('tool_results', []):
                            if result.get('config_update'):
                                yield {"event": "config_update", "data": json.dumps(result['config_update'])}
                        for citation in node_output.get('citations', []):
                            if citation:
                                yield {"event": "citation", "data": citation}
                    elif node_name in ('stress_test', 'compare', 'timing', 'explanation'):
                        for citation in node_output.get('citations', []):
                            if citation:
                                yield {"event": "citation", "data": citation}
            yield {"event": "done", "data": "{}"}
        except Exception as e:
            yield {"event": "error", "data": str(e)[:200]}
    return EventSourceResponse(generate())


@app.websocket("/api/lmp/stream")
async def ws_lmp(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            snapshot = await fetch_ercot_snapshot(settings.gridstatus_api_key)
            await websocket.send_json(snapshot['lmp'])
            await asyncio.sleep(300)  # 5-min cadence
    except (WebSocketDisconnect, Exception):
        pass
