"""Apply retention from config/sources.yaml. Run daily via cron or APScheduler.

Keeps the raw audit trail bounded — default 7 days. Quarantine is kept longer
(30 days) so you can investigate systematic validation failures after the fact.
"""
from __future__ import annotations

import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.config import load_config


def purge_dir(root: Path, days: int) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    removed = 0
    if not root.exists():
        return 0
    for day_dir in root.rglob("*"):
        if not day_dir.is_dir():
            continue
        # Leaf date dirs look like YYYY-MM-DD or YYYYMMDDTHHMMSSZ prefixed files.
        try:
            day = datetime.strptime(day_dir.name[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if day < cutoff:
            shutil.rmtree(day_dir)
            removed += 1
    return removed


def main() -> None:
    cfg = load_config()
    r = cfg.retention
    print("raw purged:", purge_dir(cfg.data_root / "raw", r["raw_days"]))
    print("quarantine purged:", purge_dir(cfg.data_root / "quarantine", r["quarantine_days"]))
    print("reports purged:", purge_dir(cfg.data_root / "_meta" / "runs", r["dq_reports_days"]))


if __name__ == "__main__":
    main()
