from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pipeline.http_client import FetchResult
from pipeline.sources.pipelines_infra import PipelineInfraIngestor, _polyline_length_km


class _DummyHttp:
    pass


def _fetch(payload: dict) -> FetchResult:
    return FetchResult(
        request_id="req-1",
        fetched_at_utc=datetime.now(timezone.utc),
        url="https://example.test/pipelines",
        status_code=200,
        payload_sha256="0" * 64,
        body=json.dumps(payload).encode("utf-8"),
        raw_path=Path("/tmp/pipelines.json"),
    )


def test_parse_flattens_paths_and_extracts_geometry():
    ingestor = PipelineInfraIngestor(http=_DummyHttp())
    df = ingestor.parse(_fetch({
        "features": [
            {
                "attributes": {
                    "FID": 7,
                    "TYPEPIPE": "Interstate",
                    "Operator": "Example Gas",
                    "Status": "Operating",
                },
                "geometry": {
                    "paths": [
                        [[-110.0, 33.0], [-109.5, 33.5]],
                        [[-109.0, 34.0]],
                    ]
                },
            }
        ]
    }))

    assert len(df) == 1
    row = df.iloc[0]
    assert row["pipeline_id"] == 7
    assert row["pipe_type"] == "Interstate"
    assert row["num_vertices"] == 3
    assert row["start_lon"] == -110.0
    assert row["end_lat"] == 34.0
    assert row["geometry_wkt"].startswith("LINESTRING (")
    assert row["length_km"] > 0


def test_polyline_length_is_zero_for_repeated_point():
    length = _polyline_length_km([[-112.0, 33.0], [-112.0, 33.0]])
    assert length == 0.0
