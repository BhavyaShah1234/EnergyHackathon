"""Tavily + Claude web context enrichment for land and pipeline scoring.

Two scored adjustments per site evaluation:
  land_adjustment  float [-0.10, +0.10]  — added to ML land score
  pipeline_score   float [0.0,   1.0]    — operator reliability from web news

Both degrade gracefully to 0.0 / 0.5 when APIs are unavailable.
Results are cached at 0.5° grid resolution (~55 km) for the process lifetime.
"""
import asyncio
import json
import logging
import math
from dataclasses import dataclass, field
from typing import Optional

_LOGGER = logging.getLogger(__name__)

# ── Geographic region hints for Tavily query construction ──────────────────
# (lat, lon, "county / metro name for search query")
_REGIONS = [
    (31.997, -102.078, "Midland Odessa Permian Basin West Texas"),
    (32.448, -99.733,  "Abilene Taylor County Texas"),
    (33.579, -101.855, "Lubbock Lubbock County Texas"),
    (35.222, -101.831, "Amarillo Potter County Texas Panhandle"),
    (31.542, -97.146,  "Waco McLennan County Central Texas"),
    (32.725, -97.321,  "Fort Worth Tarrant County Texas"),
    (30.267, -97.743,  "Austin Travis County Texas"),
    (29.760, -95.370,  "Houston Harris County Texas"),
    (29.424, -98.494,  "San Antonio Bexar County Texas"),
    (28.703, -100.502, "Eagle Pass Maverick County South Texas"),
    (32.252, -104.376, "Carlsbad Eddy County New Mexico Permian"),
    (32.721, -103.103, "Hobbs Lea County New Mexico"),
    (33.394, -104.523, "Roswell Chaves County New Mexico"),
    (32.221, -110.958, "Tucson Pima County Arizona"),
    (33.430, -112.359, "Goodyear Maricopa County Arizona"),
    (33.448, -111.924, "Mesa Maricopa County Arizona"),
    (34.054, -118.243, "Los Angeles California"),
]


def _nearest_region(lat: float, lon: float) -> str:
    best_name, best_d = _REGIONS[0][2], 9999.0
    for rlat, rlon, name in _REGIONS:
        d = math.hypot(lat - rlat, lon - rlon)
        if d < best_d:
            best_name, best_d = name, d
    return best_name


def _cache_key(lat: float, lon: float) -> str:
    """0.5° grid cell key (~55 km resolution)."""
    return f"{round(lat * 2) / 2:.1f},{round(lon * 2) / 2:.1f}"


# ── Result type ───────────────────────────────────────────────────────────

@dataclass
class WebContext:
    land_adjustment:    float = 0.0   # bounded to [-0.10, +0.10]
    pipeline_score:     float = 0.5   # 0–1 operator reliability
    land_reasoning:     str   = ""
    pipeline_reasoning: str   = ""
    sources:            list  = field(default_factory=list)
    fetched:            bool  = False  # True = real API data, False = fallback


# ── Process-lifetime cache ─────────────────────────────────────────────────
_WEB_CACHE: dict[str, WebContext] = {}


# ── Main async function ────────────────────────────────────────────────────

async def fetch_web_context(
    lat: float,
    lon: float,
    pipe_info: Optional[dict],     # from spatial.nearest_pipeline_info()
    tavily_key: str,
    anthropic_key: str,
) -> WebContext:
    """Fetch Tavily search results → Claude reasoning → WebContext.

    Returns cached result when the same 0.5° grid cell was already evaluated.
    Returns unfetched WebContext (adjustment=0, pipeline=0.5) on any API failure.
    """
    key = _cache_key(lat, lon)
    if key in _WEB_CACHE:
        return _WEB_CACHE[key]

    ctx = WebContext()

    if not tavily_key or not anthropic_key:
        _WEB_CACHE[key] = ctx
        return ctx

    region   = _nearest_region(lat, lon)
    operator = pipe_info.get('pipe_type', 'natural gas') if pipe_info else 'natural gas'
    pipe_dist = pipe_info.get('dist_km', 0) if pipe_info else 0

    # ── Step 1: Tavily search ─────────────────────────────────────────────
    land_text = ""
    pipe_text = ""
    sources: list[dict] = []

    try:
        from tavily import TavilyClient
        tc = TavilyClient(api_key=tavily_key)

        land_q = (
            f"{region} data center industrial zoning permitting land development 2024 2025"
        )
        pipe_q = (
            f"natural gas pipeline reliability safety {region} PHMSA incident 2024 2025"
        )

        # Run both searches concurrently
        land_res, pipe_res = await asyncio.gather(
            asyncio.to_thread(lambda: tc.search(land_q,  max_results=3)),
            asyncio.to_thread(lambda: tc.search(pipe_q,  max_results=3)),
        )

        def _fmt(res: dict) -> str:
            return "\n\n".join(
                f"[{r['title']}]\n{r['content'][:400]}\nSource: {r['url']}"
                for r in res.get("results", [])
            )

        land_text = _fmt(land_res)
        pipe_text = _fmt(pipe_res)
        sources = [
            {"title": r["title"], "url": r["url"]}
            for r in (land_res.get("results", []) + pipe_res.get("results", []))
        ]

    except Exception as exc:
        _LOGGER.warning("Tavily search failed for (%.3f, %.3f): %s", lat, lon, exc)
        _WEB_CACHE[key] = ctx
        return ctx

    # ── Step 2: Claude Haiku reasoning ───────────────────────────────────
    _SYSTEM = """You are a BTM data center site analyst. Analyze web search results for a candidate site and return ONLY a JSON object with exactly these fields:

{
  "land_adjustment": <float, -0.10 to +0.10>,
  "land_reasoning": "<1–2 sentences summarizing zoning/legal/permitting signals>",
  "pipeline_score": <float, 0.0 to 1.0>,
  "pipeline_reasoning": "<1–2 sentences summarizing gas supply reliability signals>"
}

land_adjustment scoring:
  +0.06 to +0.10 → strong positives: industrial rezoning approvals, data center corridor designation, fast-track permits, announced hyperscaler investments in region
  +0.01 to +0.05 → mild positives: pro-business climate news, minor zoning updates
  -0.01 to +0.01 → neutral or no relevant information
  -0.05 to -0.01 → mild negatives: slow permitting, minor community concerns
  -0.10 to -0.06 → strong negatives: permitting freeze, litigation, wilderness/environmental designations, moratoriums

pipeline_score:
  0.85–1.00 → recent capacity expansions, strong operator safety record, redundant supply
  0.60–0.84 → no notable incidents, normal operations
  0.40–0.59 → insufficient information (use 0.50 as default)
  0.20–0.39 → recent PHMSA incidents, regulatory violations, aging infrastructure warnings
  0.00–0.19 → severe recent failures, ongoing safety orders

Return ONLY valid JSON. No markdown fences. No extra text."""

    try:
        import anthropic as _anthropic
        client = _anthropic.AsyncAnthropic(api_key=anthropic_key)

        user_content = (
            f"Region: {region}\n"
            f"Pipeline type nearby: {operator} ({pipe_dist:.1f} km away)\n"
            f"Coordinates: {lat:.4f}°N, {lon:.4f}°E\n\n"
            f"=== LAND / ZONING SEARCH RESULTS ===\n"
            f"{land_text or '(no results returned)'}\n\n"
            f"=== PIPELINE / GAS SUPPLY SEARCH RESULTS ===\n"
            f"{pipe_text or '(no results returned)'}"
        )

        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )

        raw = resp.content[0].text.strip()
        # Strip markdown fences if model adds them despite instructions
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        parsed = json.loads(raw)

        ctx.land_adjustment    = float(max(-0.10, min(0.10, parsed.get("land_adjustment", 0.0))))
        ctx.pipeline_score     = float(max(0.0,   min(1.0,  parsed.get("pipeline_score",  0.5))))
        ctx.land_reasoning     = str(parsed.get("land_reasoning",     ""))[:600]
        ctx.pipeline_reasoning = str(parsed.get("pipeline_reasoning", ""))[:600]
        ctx.sources            = sources
        ctx.fetched            = True

    except Exception as exc:
        _LOGGER.warning("Claude web reasoning failed for (%.3f, %.3f): %s", lat, lon, exc)
        ctx.sources = sources   # keep sources even if reasoning failed

    _WEB_CACHE[key] = ctx
    return ctx


def clear_cache() -> None:
    """Clear the process-lifetime web context cache (for testing)."""
    _WEB_CACHE.clear()
