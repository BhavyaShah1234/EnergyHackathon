"""HTTP client with retry/backoff, per-host rate limiting, and raw-response persistence.

Every request:
  - retries on 429/5xx/transient network errors with jittered exponential backoff
  - respects per-host RPS from config (token bucket)
  - persists the raw response bytes to data/raw/<source>/<YYYY-MM-DD>/<request_id>.json
    before parsing, so we always have an audit trail even if parsing breaks
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential_jitter,
)

from .config import PipelineConfig, load_config


class _RateLimiter:
    """Minimal token-bucket keyed by host. Thread-safe enough for APScheduler."""

    def __init__(self, per_host_rps: dict[str, float]):
        self._rps = per_host_rps
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def acquire(self, host: str) -> None:
        rps = self._rps.get(host, 10.0)
        min_interval = 1.0 / rps
        with self._lock:
            now = time.monotonic()
            last = self._last.get(host, 0.0)
            wait = last + min_interval - now
            if wait > 0:
                time.sleep(wait)
            self._last[host] = time.monotonic()


@dataclass
class FetchResult:
    request_id: str          # uuid4 for this request, stamped on every row for provenance
    fetched_at_utc: datetime
    url: str
    status_code: int
    payload_sha256: str      # hash of response body; dedup + integrity
    body: bytes              # raw bytes; parsed downstream
    raw_path: Path           # where we persisted the raw response


class HttpClient:
    """One client per pipeline run. Not thread-safe for in-flight requests, but
    rate limiter is, so parallel sources are fine."""

    def __init__(self, cfg: PipelineConfig | None = None):
        self.cfg = cfg or load_config()
        self._client = httpx.Client(
            timeout=self.cfg.http.timeout_seconds,
            headers={"User-Agent": self.cfg.noaa_user_agent},
            follow_redirects=True,
        )
        self._limiter = _RateLimiter(self.cfg.http.per_host_rps)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def fetch(
        self,
        source: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        persist_raw: bool = True,
    ) -> FetchResult:
        host = httpx.URL(url).host
        self._limiter.acquire(host)

        resp = self._fetch_with_retries(url, params=params, headers=headers)
        body = resp.content
        sha = hashlib.sha256(body).hexdigest()
        fetched_at = datetime.now(timezone.utc)
        request_id = str(uuid.uuid4())

        raw_path = self._raw_path(source, fetched_at, request_id)
        if persist_raw:
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            # Wrap payload with metadata so the raw file is self-describing.
            envelope = {
                "request_id": request_id,
                "fetched_at_utc": fetched_at.isoformat(),
                "url": str(resp.request.url),
                "status_code": resp.status_code,
                "payload_sha256": sha,
                "headers": dict(resp.headers),
                "body_b64_or_text": _decode_or_b64(body),
            }
            raw_path.write_text(json.dumps(envelope, separators=(",", ":")))

        return FetchResult(
            request_id=request_id,
            fetched_at_utc=fetched_at,
            url=str(resp.request.url),
            status_code=resp.status_code,
            payload_sha256=sha,
            body=body,
            raw_path=raw_path,
        )

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=1.0, max=60.0),
        retry=retry_if_exception(lambda e: _is_retryable(e)),
        reraise=True,
    )
    def _fetch_with_retries(
        self,
        url: str,
        *,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
    ) -> httpx.Response:
        resp = self._client.get(url, params=params, headers=headers)
        # Raise on 429/5xx (retried by tenacity) and on 4xx (not retried — see _is_retryable).
        resp.raise_for_status()
        return resp

    def _raw_path(self, source: str, ts: datetime, request_id: str) -> Path:
        day = ts.strftime("%Y-%m-%d")
        return self.cfg.data_root / "raw" / source / day / f"{request_id}.json"


def _is_retryable(exc: BaseException) -> bool:
    """Retry only on transient issues: network errors, timeouts, 429, 5xx.
    4xx (e.g. 404, 401) are permanent — fail fast so a bad config doesn't burn the rate budget."""
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or 500 <= code < 600
    return False


def _decode_or_b64(body: bytes) -> str:
    """Store text responses as-is for grep-ability; fall back to base64 for binary (CAISO zips)."""
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        import base64
        return "base64:" + base64.b64encode(body).decode("ascii")
