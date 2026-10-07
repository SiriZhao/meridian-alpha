"""Every test starts outside the canonical runtime, including child processes."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_runtime_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "isolated-runtime"
    monkeypatch.setenv("MERIDIAN_HOME", str(home))
    monkeypatch.setenv("MERIDIAN_CACHE", str(home / "cache"))
