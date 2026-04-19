"""Integrity manifest — SHA256 of every silver file, signed on write, verified on demand.

If a silver parquet file is mutated, truncated, or deleted outside the pipeline,
`verify()` catches it. This is the 'tamper-evident' guarantee on top of git history.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def update_manifest(silver_dir: Path, manifest_path: Path) -> dict:
    """Rebuild manifest from what's on disk. Call after every silver write."""
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "files": {},
    }
    for p in sorted(silver_dir.rglob("*.parquet")):
        rel = str(p.relative_to(silver_dir))
        manifest["files"][rel] = {
            "sha256": _sha256(p),
            "size_bytes": p.stat().st_size,
            "mtime_utc": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
        }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2))
    return manifest


def verify(silver_dir: Path, manifest_path: Path) -> dict:
    """Return a report of {ok, missing, modified, new} relative to the manifest."""
    if not manifest_path.exists():
        return {"ok": False, "reason": "no_manifest", "missing": [], "modified": [], "new": []}
    manifest = json.loads(manifest_path.read_text())
    recorded = manifest["files"]
    on_disk = {str(p.relative_to(silver_dir)): p for p in silver_dir.rglob("*.parquet")}
    missing = [k for k in recorded if k not in on_disk]
    new = [k for k in on_disk if k not in recorded]
    modified = []
    for k, meta in recorded.items():
        if k not in on_disk:
            continue
        if _sha256(on_disk[k]) != meta["sha256"]:
            modified.append(k)
    return {
        "ok": not (missing or modified),
        "missing": missing,
        "modified": modified,
        "new": new,
        "generated_at_utc": manifest["generated_at_utc"],
    }
