"""One-shot runner — calls every registered source once, writes a DQ report.

    python -m orchestrator.run_once              # all sources
    python -m orchestrator.run_once --only eia930_azps,caiso_lmp
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid

from rich.console import Console
from rich.table import Table

from pipeline.config import load_config
from pipeline.http_client import HttpClient
from pipeline.quality.report import write_run_report
from pipeline.registry import REGISTRY

log = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="comma-separated source names to run (default: all)")
    parser.add_argument("--fail-fast", action="store_true", help="exit non-zero on any source failure")
    args = parser.parse_args(argv)

    cfg = load_config()
    logging.basicConfig(
        level=cfg.__dict__.get("log_level", "INFO"),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    selected = set(args.only.split(",")) if args.only else set(REGISTRY.keys())
    entries = [e for name, e in REGISTRY.items() if name in selected]

    run_id = uuid.uuid4().hex[:8]
    console = Console()
    console.rule(f"[bold]run {run_id} — {len(entries)} sources")

    results = []
    with HttpClient(cfg) as http:
        for entry in entries:
            try:
                ingestor_cls = entry.load()
                ingestor = ingestor_cls(http=http, cfg=cfg)
                result = ingestor.run()
            except Exception as exc:
                log.exception("fatal error in %s", entry.source)
                from pipeline.quality.checks import CheckResult
                result = CheckResult(
                    dataset=entry.dataset, rows_in=0, rows_out=0, rows_quarantined=0,
                    schema_errors=[f"{type(exc).__name__}: {exc}"], ok=False,
                )
            results.append(result)
            _print_row(console, entry.source, result)

    report_path = write_run_report(run_id, results, cfg.data_root / "_meta" / "runs")
    console.print(f"\nDQ report → [cyan]{report_path}")
    overall_ok = all(r.ok for r in results)
    return 0 if overall_ok or not args.fail_fast else 1


def _print_row(console: Console, source: str, result) -> None:
    status = "[green]OK" if result.ok else "[red]FAIL"
    fresh = f"{result.freshness_minutes:.0f}m" if result.freshness_minutes is not None else "—"
    console.print(
        f"{status}  {source:<22} rows={result.rows_out:<6} quar={result.rows_quarantined:<4} "
        f"fresh={fresh}  dup={result.dup_rate:.1%}  errs={result.schema_errors or '—'}"
    )


if __name__ == "__main__":
    sys.exit(main())
