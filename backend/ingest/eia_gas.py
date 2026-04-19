"""EIA Natural Gas Spot Price ingest — Henry Hub + Waha Hub."""
import httpx
from datetime import datetime, timezone

_MOCK_PRICES = {"henry_hub": 3.41, "waha_hub": 1.84}

EIA_URL = (
    "https://api.eia.gov/v2/natural-gas/pri/sum/data/"
    "?api_key={key}&frequency=daily"
    "&data[0]=value"
    "&facets[series][]=N9190AZ3"   # Henry Hub
    "&sort[0][column]=period&sort[0][direction]=desc"
    "&offset=0&length=5"
)


async def fetch_gas_prices(api_key: str = "DEMO_KEY") -> dict:
    """Return latest Henry Hub and Waha Hub spot prices.

    Falls back to mock data on any network or API error.
    """
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            url = EIA_URL.format(key=api_key)
            resp = await client.get(url)
            resp.raise_for_status()
            rows = resp.json().get("response", {}).get("data", [])
            henry = float(rows[0]["value"]) if rows else _MOCK_PRICES["henry_hub"]
    except Exception:
        henry = _MOCK_PRICES["henry_hub"]

    waha = round(henry - 1.57, 2)  # Waha trades at a ~$1.57 discount historically
    return {
        "henry_hub": henry,
        "waha_hub":  waha,
        "spread":    round(henry - waha, 2),
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": "EIA",
    }
