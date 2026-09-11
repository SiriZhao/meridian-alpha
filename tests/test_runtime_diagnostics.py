from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from meridian.runtime import RuntimePaths
from meridian.runtime_diagnostics import report


def test_windows_default_and_environment_override(tmp_path: Path) -> None:
    overridden = RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path)})
    assert overridden.home == tmp_path
    cache = tmp_path / "explicit-cache"
    split = RuntimePaths.from_environment(
        {"MERIDIAN_HOME": str(tmp_path), "MERIDIAN_CACHE": str(cache)}
    )
    assert split.home == tmp_path
    assert split.cache == cache
    windows = RuntimePaths.from_environment({"LOCALAPPDATA": "C:/Local"}, platform="win32")
    assert windows.home == Path("C:/Local") / "MeridianAlpha"


def test_runtime_paths_create_only_runtime_directories(tmp_path: Path) -> None:
    paths = RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path / "runtime")})
    paths.ensure_directories()
    assert paths.db.parent.is_dir()
    assert paths.reports.is_dir()
    assert not (tmp_path / "policies").exists()


def test_doctor_json_is_secret_safe_and_network_free(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MERIDIAN_HOME", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_API_KEY", "this-value-must-not-appear")
    payload = report()
    encoded = json.dumps(payload)
    assert payload["schema_version"] == "meridian-doctor.v2"
    assert payload["network_accessed"] is False
    assert "this-value-must-not-appear" not in encoded


def test_doctor_module_startup_smoke(tmp_path: Path) -> None:
    env = {**os.environ, "MERIDIAN_HOME": str(tmp_path)}
    result = subprocess.run([sys.executable, "-m", "meridian.runtime_diagnostics", "doctor", "--json"], capture_output=True, text=True, env=env, timeout=10, check=False)
    payload = json.loads(result.stdout)
    assert payload["network_accessed"] is False
    assert payload["elapsed_ms"] < 10_000


def test_read_only_runtime_report_does_not_claim_a_write_probe(tmp_path: Path) -> None:
    payload = cast(dict[str, Any], report(RuntimePaths(tmp_path), probe_writes=False))
    assert payload["cache"]["status"] == "NOT_PROBED_READ_ONLY_HOST"
    assert any(check["name"] == "runtime_write" and check["status"] == "SKIPPED" for check in payload["checks"])