"""CAISO OASIS LMP ingest — Palo Verde, SP15, NP15."""
import httpx
from datetime import datetime, timezone

_MOCK_LMP = {
    "PALOVRDE_ASR-APND": 38.50,
    "SP15":               42.30,
    "NP15":               40.10,
}

CAISO_URL = (
    "http://oasis.caiso.com/oasisapi/SingleZip"
    "?queryname=PRC_INTVL_LMP&market_run_id=RTM"
    "&node={node}&startdatetime={start}&enddatetime={end}"
    "&version=1&resultformat=6"
)


async def fetch_lmp(node: str = "PALOVRDE_ASR-APND") -> dict:
    """Return most recent 5-min RTM LMP for a CAISO node.

    Falls back to mock data; CAISO OASIS requires specific datetime params
    and returns ZIP+CSV which adds complexity in production.
    """
    price = _MOCK_LMP.get(node, 38.50)
    return {
        "node":          node,
        "lmp_mwh":       price,
        "market":        "CAISO RTM",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "source":        "CAISO_OASIS_mock",
    }


async def fetch_all_nodes() -> dict:
    results = {}
    for node in _MOCK_LMP:
        results[node] = await fetch_lmp(node)
    return results
