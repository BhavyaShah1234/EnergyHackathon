"""Verify the silver lake matches the manifest. Run in CI or before model training.

Exit code 0 if every silver file matches; 1 otherwise (CI-friendly).
"""
from __future__ import annotations

import json
import sys

from rich.console import Console

from pipeline.config import load_config
from pipeline.integrity import verify


def main() -> int:
    cfg = load_config()
    report = verify(cfg.data_root / "silver", cfg.data_root / "_meta" / "manifest.json")
    console = Console()
    console.print_json(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
