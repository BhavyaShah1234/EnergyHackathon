"""Tests for the DQ layer — these guard the 'no corruption downstream' promise."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from pipeline.quality.checks import validate
from pipeline.quality.schemas import EIA930_SCHEMA


def _base_row(**overrides):
    row = {
        "period_utc": datetime.now(timezone.utc),
        "respondent": "AZPS",
        "type": "D",
        "value_mw": 2500.0,
        "_source": "eia930_azps",
        "_request_id": "abc",
        "_fetched_at_utc": datetime.now(timezone.utc),
        "_payload_sha256": "0" * 64,
    }
    row.update(overrides)
    return row


def test_happy_path(tmp_path: Path):
    df = pd.DataFrame([_base_row(), _base_row(respondent="CISO")])
    clean, report = validate(
        df, EIA930_SCHEMA,
        dataset="eia930", freshness_sla_hours=3,
        freshness_col="period_utc",
        natural_key=["period_utc", "respondent", "type"],
        quarantine_dir=tmp_path,
    )
    assert report.ok
    assert report.rows_out == 2
    assert report.rows_quarantined == 0


def test_quarantines_out_of_range_value(tmp_path: Path):
    # 10M MW is physically impossible — schema range check rejects it.
    df = pd.DataFrame([_base_row(), _base_row(value_mw=1e7, respondent="CISO")])
    clean, report = validate(
        df, EIA930_SCHEMA,
        dataset="eia930", freshness_sla_hours=3,
        freshness_col="period_utc",
        natural_key=["period_utc", "respondent", "type"],
        quarantine_dir=tmp_path,
    )
    assert report.rows_quarantined == 1
    assert report.rows_out == 1
    # Quarantine file exists with the bad row
    files = list((tmp_path / "eia930").rglob("*.parquet"))
    assert files, "expected a quarantine parquet"


def test_freshness_sla_violation(tmp_path: Path):
    stale = _base_row(period_utc=datetime.now(timezone.utc) - timedelta(hours=12))
    df = pd.DataFrame([stale])
    _, report = validate(
        df, EIA930_SCHEMA,
        dataset="eia930", freshness_sla_hours=3,
        freshness_col="period_utc",
        natural_key=["period_utc", "respondent", "type"],
        quarantine_dir=tmp_path,
    )
    assert report.freshness_ok is False
    assert report.ok is False


def test_dedup_on_natural_key(tmp_path: Path):
    ts = datetime.now(timezone.utc)
    df = pd.DataFrame([
        _base_row(period_utc=ts, value_mw=2500.0),
        _base_row(period_utc=ts, value_mw=2600.0),   # same natural key, fresher value wins
    ])
    clean, report = validate(
        df, EIA930_SCHEMA,
        dataset="eia930", freshness_sla_hours=3,
        freshness_col="period_utc",
        natural_key=["period_utc", "respondent", "type"],
        quarantine_dir=tmp_path,
    )
    assert len(clean) == 1
    assert clean.iloc[0]["value_mw"] == 2600.0
    assert report.dup_rate == 0.5
