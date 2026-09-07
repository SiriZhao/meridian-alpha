from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from meridian.application import MeridianApplicationService
from meridian.audit import SCHEMA_VERSION
from meridian.runtime import RuntimePaths


def database(payload: dict[str, object]) -> dict[str, Any]:
    return cast(dict[str, Any], payload["database"])


def test_fresh_home_requires_explicit_init_then_doctor_is_current(tmp_path: Path) -> None:
    service = MeridianApplicationService(RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path)}))
    assert database(service.doctor())["migration_status"] == "PENDING"
    initialized = service.init()
    assert initialized["status"] == "INIT_COMPLETE"
    assert initialized["schema_version"] == SCHEMA_VERSION
    assert service.init()["status"] == "INIT_ALREADY_COMPLETE"
    assert database(service.doctor())["migration_status"] == "CURRENT"


def test_application_service_paths_data_and_forward_are_runtime_scoped(tmp_path: Path) -> None:
    service = MeridianApplicationService(RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path)}))
    assert service.paths_status()["home"] == str(tmp_path)
    assert service.data_status()["certification"] == "OPERATIONAL_DATA_IS_NOT_CERTIFIED_RESEARCH"
    assert service.forward_status()["status"] == "INSUFFICIENT_FORWARD_EVIDENCE"


def test_invalid_existing_database_fails_closed(tmp_path: Path) -> None:
    paths = RuntimePaths.from_environment({"MERIDIAN_HOME": str(tmp_path)})
    paths.db.parent.mkdir(parents=True)
    paths.db.write_text("not a sqlite database", encoding="utf-8")
    assert MeridianApplicationService(paths).init()["status"] == "INIT_FAILED"
