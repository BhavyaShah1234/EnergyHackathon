"""Per-run DQ report — one JSON per orchestrator tick, under data/_meta/runs/."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .checks import CheckResult


def write_run_report(
    run_id: str,
    results: list[CheckResult],
    meta_dir: Path,
) -> Path:
    meta_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = meta_dir / f"{ts}_{run_id}.json"
    payload = {
        "run_id": run_id,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall_ok": all(r.ok for r in results),
        "datasets": [r.to_dict() for r in results],
    }
    path.write_text(json.dumps(payload, indent=2, default=str))
    return path
