"""Continuous runner — schedules each source at its configured cadence.

  python -m orchestrator.run_live

Graceful shutdown: SIGINT drains in-flight jobs and writes a final DQ report.
"""
from __future__ import annotations

import logging
import signal
import sys
import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger

from pipeline.config import load_config
from pipeline.http_client import HttpClient
from pipeline.quality.checks import CheckResult
from pipeline.quality.report import write_run_report
from pipeline.registry import REGISTRY

log = logging.getLogger(__name__)


def _job(source_name: str, http: HttpClient) -> CheckResult:
    entry = REGISTRY[source_name]
    try:
        ingestor = entry.load()(http=http)
        result = ingestor.run()
    except Exception as exc:
        log.exception("job %s failed", source_name)
        result = CheckResult(
            dataset=entry.dataset, rows_in=0, rows_out=0, rows_quarantined=0,
            schema_errors=[f"{type(exc).__name__}: {exc}"], ok=False,
        )
    status = "OK " if result.ok else "FAIL"
    log.info(
        "%s %s rows=%d quar=%d fresh=%s errs=%s",
        status, source_name, result.rows_out, result.rows_quarantined,
        result.freshness_minutes, result.schema_errors,
    )
    return result


def main() -> int:
    cfg = load_config()
    logging.basicConfig(
        level="INFO", format="%(asctime)s %(levelname)s %(message)s",
    )

    http = HttpClient(cfg)
    scheduler = BlockingScheduler(timezone="UTC")
    results_buffer: list[CheckResult] = []
    shutting_down = False

    def _close_http() -> None:
        try:
            http.close()
        except Exception:
            log.exception("failed to close http client")

    def _shutdown(*_):
        nonlocal shutting_down
        if shutting_down:
            return
        shutting_down = True
        log.info("shutting down…")
        if scheduler.running:
            scheduler.shutdown(wait=False)
        if results_buffer:
            write_run_report(uuid.uuid4().hex[:8], results_buffer, cfg.data_root / "_meta" / "runs")
        _close_http()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    try:
        for source_name, entry in REGISTRY.items():
            cadence = cfg.sources[source_name].cadence_seconds
            scheduler.add_job(
                lambda s=source_name: results_buffer.append(_job(s, http)),
                trigger=IntervalTrigger(seconds=cadence),
                id=source_name,
                name=source_name,
                next_run_time=datetime.now(timezone.utc),  # kick off immediately
                max_instances=1,
                coalesce=True,
            )
            log.info("scheduled %s every %ds", source_name, cadence)
        scheduler.start()
        return 0
    finally:
        if not shutting_down:
            _close_http()


if __name__ == "__main__":
    main()
