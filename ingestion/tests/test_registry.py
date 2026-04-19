"""Guard: every registry entry must import cleanly and point to a real class."""
from __future__ import annotations

from pipeline.registry import REGISTRY
from pipeline.base import BaseIngestor


def test_all_entries_importable():
    for name, entry in REGISTRY.items():
        cls = entry.load()
        assert issubclass(cls, BaseIngestor), f"{name} does not subclass BaseIngestor"
        assert cls.SOURCE == entry.source
        assert cls.DATASET == entry.dataset
        assert cls.SCHEMA is not None
        assert cls.PARTITION_COL
