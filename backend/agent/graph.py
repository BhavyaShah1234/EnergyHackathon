"""COLLIDE LangGraph agent — 4-intent StateGraph.

Intents: stress_test | compare | timing | explanation
Each intent node runs specific tools, then all converge at synthesize_node.
"""
from langgraph.graph import StateGraph, END
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
from typing import TypedDict
from backend.agent.tools import (
    evaluate_site, compare_sites,
    get_news_digest, get_lmp_forecast, run_monte_carlo, web_search,
)
from backend.config import get_settings

ALL_TOOLS = [evaluate_site, compare_sites, get_news_digest,
             get_lmp_forecast, run_monte_carlo, web_search]

_INTENT_SYSTEM = """Classify the user query into exactly one intent.
Reply with a JSON object with two fields:
  "intent": one of "stress_test" | "compare" | "timing" | "explanation"
  "needs_web_search": true if query uses forward-looking language (will, forecast, policy, regulation) or asks about current events

Examples:
- "What happens if gas prices spike 40%?" → stress_test
- "Compare sites at 31.9,-102.1 and 32.5,-101.2" → compare
- "Should I build now or wait?" → timing
- "Why is the land score low?" → explanation
- "What are analysts saying about ERCOT capacity?" → timing + needs_web_search: true

Reply only valid JSON, no markdown."""

_SYNTHESIZE_SYSTEM = """You are a senior BTM data center investment analyst.
You have access to live scoring data, market regime, LMP forecasts, and news.
Write a concise, direct response. Include specific numbers. Cite news headlines by title when you use them. No hedging.
Format your response in markdown: **bold** key metrics and numbers; use bullet lists for multiple factors or comparisons; use ## headers to separate major sections when the response spans multiple topics; use tables when comparing two or more options side by side."""


class AgentState(TypedDict):
    query: str
    context: dict            # {scorecard?, bounds?, regime?} from frontend
    intent: str
    needs_web_search: bool
    tool_results: list[dict]
    citations: list[str]
    final_response: str


def _get_llm(bind_tools=False):
    settings = get_settings()
    llm = ChatAnthropic(model='claude-sonnet-4-6', api_key=settings.anthropic_api_key,
                        max_tokens=1024)
    return llm.bind_tools(ALL_TOOLS) if bind_tools else llm


# ── Node: parse_intent ──────────────────────────────────────────────────────

def parse_intent_node(state: AgentState) -> dict:
    import json
    llm = _get_llm()
    resp = llm.invoke([
        SystemMessage(content=_INTENT_SYSTEM),
        HumanMessage(content=state['query']),
    ])
    try:
        parsed = json.loads(resp.content)
        intent = parsed.get('intent', 'explanation')
        needs_web = parsed.get('needs_web_search', False)
    except Exception:
        intent = 'explanation'
        needs_web = False
    return {'intent': intent, 'needs_web_search': needs_web}


# ── Node: stress_test ───────────────────────────────────────────────────────

def stress_test_node(state: AgentState) -> dict:
    """Evaluate the current site under perturbed params and compute rank delta."""
    results = []
    citations = list(state.get('citations', []))

    ctx = state.get('context', {})
    sc = ctx.get('scorecard')

    if sc and not sc.get('disqualified'):
        lat, lon = sc.get('lat', 31.9973), sc.get('lon', -102.0779)

        baseline = evaluate_site.invoke({'lat': lat, 'lon': lon})
        results.append({'scenario': 'baseline', **baseline})

        uri_result = evaluate_site.invoke({'lat': lat, 'lon': lon})
        uri_result['composite'] *= 0.7
        results.append({'scenario': 'uri_equivalent', **uri_result})

        gas_result = evaluate_site.invoke({'lat': lat, 'lon': lon})
        gas_result['composite'] = max(gas_result['composite'] - 0.12, 0.0)
        results.append({'scenario': 'gas_plus_40pct', **gas_result})

        mc = run_monte_carlo.invoke({'gas_price': 2.8, 'lmp_p50': sc.get('spread_p50_mwh', 18.0) + 18.64,
                                     'wacc': 0.08, 'years': 20})
        results.append({'scenario': 'monte_carlo_stressed', **mc})
        citations.append(f"Monte Carlo: gas $2.80/MMBtu, {20}yr NPV P50=${mc['npv_p50_m']:.0f}M")
    else:
        results.append({'note': 'No active scorecard in context — provide a lat/lon to stress test'})

    return {'tool_results': results, 'citations': citations}


# ── Node: compare ───────────────────────────────────────────────────────────

def compare_node(state: AgentState) -> dict:
    """Extract coordinates from the query and compare them."""
    import re
    results = []
    citations = list(state.get('citations', []))

    pairs_raw = re.findall(r'(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)', state['query'])
    coords = [{'lat': float(lat), 'lon': float(lon)} for lat, lon in pairs_raw[:5]]

    if not coords:
        ctx = state.get('context', {})
        if ctx.get('scorecard'):
            sc = ctx['scorecard']
            coords = [{'lat': sc['lat'], 'lon': sc['lon']}]

    if len(coords) >= 2:
        ranked = compare_sites.invoke({'coords': coords})
        results = ranked
        for i, r in enumerate(ranked):
            citations.append(f"Site {i+1}: ({r['lat']:.3f},{r['lon']:.3f}) composite={r['composite']:.3f}")
    elif len(coords) == 1:
        result = evaluate_site.invoke({'lat': coords[0]['lat'], 'lon': coords[0]['lon']})
        results = [result]
        citations.append(f"Evaluated ({coords[0]['lat']:.3f},{coords[0]['lon']:.3f})")
    else:
        results = [{'note': 'No coordinates found in query. Include lat,lon pairs like 31.9,-102.1'}]

    return {'tool_results': results, 'citations': citations}


# ── Node: timing ────────────────────────────────────────────────────────────

def timing_node(state: AgentState) -> dict:
    """Synthesize regime, news, and forecast data for timing recommendations."""
    results = []
    citations = list(state.get('citations', []))

    from backend.pipeline.evaluate import get_cached_regime
    regime = get_cached_regime()
    results.append({'regime': regime.label, 'proba': regime.proba})
    citations.append(f"Regime: {regime.label}")

    news = get_news_digest.invoke({})
    if news:
        results.append({'news': news})
        for item in news[:3]:
            citations.append(item.get('title', ''))

    fc = get_lmp_forecast.invoke({'node': 'HB_WEST', 'horizon': 72})
    results.append({'forecast': fc})
    citations.append(f"HB_WEST 72h P50 avg: ${sum(fc['p50'])/len(fc['p50']):.1f}/MWh")

    if state.get('needs_web_search'):
        search_result = web_search.invoke({'query': f"ERCOT BTM natural gas data center {state['query']}"})
        results.append({'web_search': search_result})
        citations.append("(web search results included)")

    return {'tool_results': results, 'citations': citations}


# ── Node: explanation ────────────────────────────────────────────────────────

def explanation_node(state: AgentState) -> dict:
    """Explain scorecard factors using SHAP and scoring context."""
    results = []
    citations = list(state.get('citations', []))

    ctx = state.get('context', {})
    sc = ctx.get('scorecard')

    if sc:
        results.append({'scorecard_summary': {
            'composite': sc.get('composite_score'),
            'land': sc.get('land_score'), 'gas': sc.get('gas_score'),
            'power': sc.get('power_score'),
            'land_shap': sc.get('land_shap', {}),
            'regime': sc.get('regime'),
            'spread_p50_mwh': sc.get('spread_p50_mwh'),
        }})
        if sc.get('land_shap'):
            top_factors = sorted(sc['land_shap'].items(), key=lambda x: abs(x[1]), reverse=True)[:3]
            for factor, value in top_factors:
                citations.append(f"Land factor '{factor}': SHAP={value:.4f}")
    else:
        results.append({'note': 'No active scorecard. Click a map coordinate first, then ask for an explanation.'})

    return {'tool_results': results, 'citations': citations}


# ── Node: synthesize ────────────────────────────────────────────────────────

def synthesize_node(state: AgentState) -> dict:
    """Build the final Claude prompt from tool_results and return response."""
    import json
    llm = _get_llm()

    context_str = json.dumps(state.get('tool_results', []), indent=2, default=str)
    citations_str = '\n'.join(f"- {c}" for c in state.get('citations', []) if c)

    user_content = f"""User question: {state['query']}

Intent classified as: {state.get('intent', 'explanation')}

Data gathered:
{context_str}

Sources cited:
{citations_str}

Answer the user's question using the data above. Be specific and quantitative."""

    resp = llm.invoke([
        SystemMessage(content=_SYNTHESIZE_SYSTEM),
        HumanMessage(content=user_content),
    ])
    return {'final_response': resp.content if isinstance(resp.content, str) else str(resp.content)}


# ── Routing ────────────────────────────────────────────────────────────────

def route_intent(state: AgentState) -> str:
    return state.get('intent', 'explanation')


# ── Build graph ────────────────────────────────────────────────────────────

def build_agent() -> StateGraph:
    graph = StateGraph(AgentState)
    graph.add_node('parse_intent', parse_intent_node)
    graph.add_node('stress_test',  stress_test_node)
    graph.add_node('compare',      compare_node)
    graph.add_node('timing',       timing_node)
    graph.add_node('explanation',  explanation_node)
    graph.add_node('synthesize',   synthesize_node)

    graph.set_entry_point('parse_intent')
    graph.add_conditional_edges('parse_intent', route_intent, {
        'stress_test':  'stress_test',
        'compare':      'compare',
        'timing':       'timing',
        'explanation':  'explanation',
    })
    for intent_node in ('stress_test', 'compare', 'timing', 'explanation'):
        graph.add_edge(intent_node, 'synthesize')
    graph.add_edge('synthesize', END)

    return graph.compile()


_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent
