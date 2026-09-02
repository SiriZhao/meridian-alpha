from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from meridian.audit import AuditStore
from meridian.runtime import RuntimePaths
from meridian.runtime_diagnostics import report


def _database(payload: dict[str, object]) -> dict[str, Any]:
    return cast(dict[str, Any], payload["database"])


def test_temp_database_migration_is_visible_to_doctor(tmp_path: Path, monkeypatch) -> None:
    paths = RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path)})
    AuditStore(paths.db).migrate()
    monkeypatch.setenv("MERIDIAN_HOME", str(tmp_path))
    database = _database(report())
    assert database["migration_status"] == "CURRENT"
    assert database["schema_version"] == 1


def test_missing_database_is_explicitly_pending_not_a_shadow_database(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MERIDIAN_HOME", str(tmp_path))
    database = _database(report())
    assert database["migration_status"] == "PENDING"
    assert not (tmp_path / "var" / "meridian.db").exists()
