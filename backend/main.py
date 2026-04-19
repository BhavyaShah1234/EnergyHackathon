"""COLLIDE Platform — FastAPI scoring engine."""
import asyncio
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.config import get_settings
from backend.data.sites import CANDIDATE_SITES
from backend.ingest.eia_gas import fetch_gas_prices
from backend.ingest.caiso_lmp import fetch_all_nodes
from backend.ingest.eia_demand import fetch_all_bas
from backend.scoring.engine import score_all, score_site
from backend.scoring.sub_b import GAS_HUB_PRICES
from backend.pipeline.runner import run_pipeline


settings = get_settings()

app = FastAPI(title="COLLIDE Scoring API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# ── Helpers ────────────────────────────────────────────────────────────────

def _build_response(s, waha: float | None) -> ScoreResponse:
    gp = waha if s.site.gas_hub == "Waha" else GAS_HUB_PRICES.get(s.site.gas_hub, 3.41)
    return ScoreResponse(
        id=s.site.id,
        name=s.site.name,
        location=s.site.location,
        state=s.site.state,
        market=s.site.market,
        lat=s.site.lat,
        lng=s.site.lng,
        acres=s.site.acres,
        land_cost_per_acre=s.site.land_cost_per_acre,
        fiber_km=s.site.fiber_km,
        water_km=s.site.water_km,
        pipeline_km=s.site.pipeline_km,
        gas_hub=s.site.gas_hub,
        gas_price=gp,
        lmp_node=s.site.lmp_node,
        lmp=s.site.lmp,
        est_power_cost_mwh=s.est_power_cost_mwh,
        total_land_cost_m=round(s.site.acres * s.site.land_cost_per_acre / 1_000_000, 2),
        scores={"subA": s.sub_a, "subB": s.sub_b, "subC": s.sub_c, "composite": s.composite},
        rank=s.rank,
    )


async def _fetch_market_inputs(api_key: str) -> tuple[dict, dict]:
    gas_data, lmp_data = await asyncio.gather(
        fetch_gas_prices(api_key),
        fetch_all_nodes(),
    )
    return gas_data, lmp_data


# ── Endpoints ──────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "collide-scoring-api"}


@app.get("/api/sites", response_model=list[ScoreResponse])
async def get_sites():
    """Return all candidate sites ranked by composite score using live market inputs."""
    gas_data, lmp_data = await _fetch_market_inputs(settings.eia_api_key)
    waha     = gas_data.get("waha_hub")
    palo_lmp = lmp_data.get("PALOVRDE_ASR-APND", {}).get("lmp_mwh")

    scored = score_all(live_gas_price=waha, live_lmp=palo_lmp)
    return [_build_response(s, waha) for s in scored]


@app.get("/api/sites/{site_id}", response_model=ScoreResponse)
async def get_site(site_id: str):
    """Return scored detail for a single candidate site."""
    site = next((s for s in CANDIDATE_SITES if s.id == site_id), None)
    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")

    gas_data, lmp_data = await _fetch_market_inputs(settings.eia_api_key)
    waha     = gas_data.get("waha_hub")
    palo_lmp = lmp_data.get("PALOVRDE_ASR-APND", {}).get("lmp_mwh")
    s        = score_site(site, waha, palo_lmp)
    return _build_response(s, waha)


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
