"""Commit receipts for a verified report bundle; never mutate financial state."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from uuid import uuid4

from meridian.canonical_run import assert_report_projection_consistency, canonical_snapshot
from meridian.daily_closure import publish_staged_report


def finalize_report_bundle(payload: dict[str, object], json_path: Path,
        markdown_path: Path, health_path: Path) -> Path:
    canonical = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    health = json.loads(health_path.read_text(encoding="utf-8"))
    assert_report_projection_consistency(canonical, markdown, health, payload)
    files = (json_path, markdown_path, health_path)
    if any(path.parent != json_path.parent for path in files):
        raise ValueError("REPORT_BUNDLE_DIRECTORY_MISMATCH")
    snapshot = canonical_snapshot(canonical)
    receipt = {
        "schema_version": "meridian-report-bundle.v1", "status": "COMPLETE",
        "run_id": snapshot.run_id, "canonical_run_id": snapshot.canonical_run_id,
        "files": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
    }
    destination = json_path.parent / "report_bundle.json"
    temporary = json_path.parent / f"report_bundle.{uuid4().hex}.tmp"
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        publish_staged_report(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def verify_report_bundle(path: Path) -> dict[str, object]:
    """Fresh consumers must verify the final receipt and all sibling files."""
    receipt = json.loads(path.read_text(encoding="utf-8"))
    if receipt.get("schema_version") != "meridian-report-bundle.v1" or receipt.get("status") != "COMPLETE":
        raise ValueError("REPORT_BUNDLE_INCOMPLETE")
    files = receipt.get("files")
    if not isinstance(files, dict) or len(files) != 3:
        raise ValueError("REPORT_BUNDLE_FILES_INVALID")
    if set(files) == {"daily.json", "daily.md", "run_health.json"}:
        json_name = "daily.json"
    elif set(files) == {"paper-daily.json", "paper-daily.md", "run_health.json"}:
        json_name = "paper-daily.json"
    else:
        raise ValueError("REPORT_BUNDLE_FILES_INVALID")
    for filename, digest in files.items():
        if Path(filename).name != filename:
            raise ValueError("REPORT_BUNDLE_PATH_INVALID")
        if hashlib.sha256((path.parent / filename).read_bytes()).hexdigest() != digest:
            raise ValueError("REPORT_BUNDLE_HASH_MISMATCH")
    snapshot = canonical_snapshot(json.loads((path.parent / json_name).read_text(encoding="utf-8")))
    if receipt.get("run_id") != snapshot.run_id or receipt.get("canonical_run_id") != snapshot.canonical_run_id:
        raise ValueError("REPORT_BUNDLE_IDENTITY_MISMATCH")
    return receipt
