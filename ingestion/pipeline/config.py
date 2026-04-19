"""Load config/sources.yaml + .env into a single typed object."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "sources.yaml"


@dataclass
class SourceSpec:
    name: str
    description: str
    endpoint: str
    cadence_seconds: int
    freshness_sla_hours: float
    natural_key: list[str]
    region: str
    facets: dict[str, list[str]] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    nodes: list[str] = field(default_factory=list)


@dataclass
class HttpPolicy:
    timeout_seconds: int
    max_retries: int
    backoff_base_seconds: float
    backoff_max_seconds: float
    per_host_rps: dict[str, float]


@dataclass
class PipelineConfig:
    sources: dict[str, SourceSpec]
    http: HttpPolicy
    retention: dict[str, int]
    data_root: Path
    eia_api_key: str | None
    noaa_user_agent: str


@lru_cache(maxsize=1)
def load_config() -> PipelineConfig:
    load_dotenv(ROOT / ".env")
    with CONFIG_PATH.open() as f:
        raw = yaml.safe_load(f)

    sources = {
        name: SourceSpec(name=name, **spec)
        for name, spec in raw["sources"].items()
    }
    http = HttpPolicy(**raw["http"])
    data_root = Path(os.environ.get("DATA_ROOT", ROOT / "data")).resolve()

    return PipelineConfig(
        sources=sources,
        http=http,
        retention=raw["retention"],
        data_root=data_root,
        eia_api_key=os.environ.get("EIA_API_KEY") or None,
        noaa_user_agent=os.environ.get(
            "NOAA_USER_AGENT", "collide-energy-pipeline anon@example.com"
        ),
    )
