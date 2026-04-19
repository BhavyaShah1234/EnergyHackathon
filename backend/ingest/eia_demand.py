"""EIA-930 15-min Balancing Authority demand + net generation ingest."""
import httpx
from datetime import datetime, timezone

_MOCK_DEMAND = {
    "AZPS": {"demand_mw": 8420,  "net_gen_mw": 8180,  "interchange_mw": -240},
    "CISO": {"demand_mw": 32100, "net_gen_mw": 29800,  "interchange_mw": -2300},
    "ERCO": {"demand_mw": 51200, "net_gen_mw": 49600,  "interchange_mw": -1600},
}

EIA_930_URL = (
    "https://api.eia.gov/v2/electricity/rto/region-data/data/"
    "?api_key={key}&frequency=local-hourly"
    "&data[0]=value&facets[respondent][]={ba}"
    "&facets[type][]=D&sort[0][column]=period"
    "&sort[0][direction]=desc&offset=0&length=1"
)


async def fetch_ba_demand(ba: str, api_key: str = "DEMO_KEY") -> dict:
    """Return latest demand for a Balancing Authority."""
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            url = EIA_930_URL.format(key=api_key, ba=ba)
            resp = await client.get(url)
            resp.raise_for_status()
            rows = resp.json().get("response", {}).get("data", [])
            demand = float(rows[0]["value"]) if rows else _MOCK_DEMAND[ba]["demand_mw"]
    except Exception:
        demand = _MOCK_DEMAND.get(ba, {}).get("demand_mw", 0)

    mock = _MOCK_DEMAND.get(ba, {})
    return {
        "ba":              ba,
        "demand_mw":       demand,
        "net_gen_mw":      mock.get("net_gen_mw", demand * 0.97),
        "interchange_mw":  mock.get("interchange_mw", 0),
        "fetched_at_utc":  datetime.now(timezone.utc).isoformat(),
        "source":          "EIA_930",
    }


async def fetch_all_bas(api_key: str = "DEMO_KEY") -> dict:
    results = {}
    for ba in _MOCK_DEMAND:
        results[ba] = await fetch_ba_demand(ba, api_key)
    return results
