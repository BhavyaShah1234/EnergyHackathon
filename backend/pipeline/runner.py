"""Pipeline runner — ingest → validate → silver lake → score."""
import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from backend.ingest.eia_gas import fetch_gas_prices
from backend.ingest.eia_demand import fetch_all_bas
from backend.ingest.caiso_lmp import fetch_all_nodes
from backend.scoring.engine import score_all

logger = logging.getLogger(__name__)

SILVER_DIR = Path("data/silver")
RAW_DIR    = Path("data/raw")


def _sha256(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _persist_raw(source: str, payload: dict) -> Path:
    now  = datetime.now(timezone.utc)
    dest = RAW_DIR / source / now.strftime("%Y-%m-%d")
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{now.strftime('%H%M%S')}.json"
    path.write_text(json.dumps(payload, indent=2))
    return path


def _write_silver(name: str, records: list[dict]) -> Path:
    df   = pd.DataFrame(records)
    dest = SILVER_DIR / name
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"{datetime.now(timezone.utc).strftime('%Y%m%d')}.parquet"
    df.to_parquet(path, index=False)
    return path


async def run_pipeline(api_key: str = "DEMO_KEY") -> dict:
    """Full ingest → validate → silver lake → score. Returns a run summary."""
    run_id  = f"run_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    started = datetime.now(timezone.utc)

    # ── 1. Ingest (parallel) ──────────────────────────────────────────────
    gas, demand, lmp = await asyncio.gather(
        fetch_gas_prices(api_key),
        fetch_all_bas(api_key),
        fetch_all_nodes(),
    )

    # Stamp provenance on every raw payload
    for payload in (gas, demand, lmp):
        payload["_sha256"]     = _sha256(payload)
        payload["_request_id"] = run_id

    # ── 2. Persist raw (best-effort — never block scoring on I/O failure) ─
    try:
        _persist_raw("eia_gas",    gas)
        _persist_raw("eia_demand", demand)
        _persist_raw("caiso_lmp",  lmp)
    except Exception as exc:
        logger.warning("Raw persistence failed (non-fatal): %s", exc)

    # ── 3. Silver lake ────────────────────────────────────────────────────
    try:
        now_utc = datetime.now(timezone.utc).isoformat()
        _write_silver("eia_gas", [{
            "period":    now_utc,
            "henry_hub": gas["henry_hub"],
            "waha_hub":  gas["waha_hub"],
            "spread":    gas["spread"],
            "_source":      "EIA",
            "_request_id":  run_id,
            "_fetched_at_utc": now_utc,
            "_payload_sha256": gas["_sha256"],
        }])
    except Exception as exc:
        logger.warning("Silver write failed (non-fatal): %s", exc)

    # ── 4. Score ──────────────────────────────────────────────────────────
    palo_lmp = lmp.get("PALOVRDE_ASR-APND", {}).get("lmp_mwh")
    scores   = score_all(live_gas_price=gas.get("waha_hub"), live_lmp=palo_lmp)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    return {
        "run_id":     run_id,
        "elapsed_s":  round(elapsed, 3),
        "gas":        {k: v for k, v in gas.items() if not k.startswith("_")},
        "site_count": len(scores),
        "top_site":   scores[0].site.name if scores else None,
        "top_score":  scores[0].composite if scores else None,
        "rankings": [
            {"rank": s.rank, "site": s.site.name, "composite": s.composite}
            for s in scores
        ],
    }
