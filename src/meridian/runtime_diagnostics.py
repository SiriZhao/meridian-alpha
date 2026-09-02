"""Local-only Meridian runtime diagnostics.

This module intentionally performs no network request, provider probe, model
initialization, or database migration.  It is safe to call as a startup
preflight and returns only sanitized state.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

from meridian.config import load_policies
from meridian.runtime import RuntimePaths, policy_directory


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def _writable(path: Path) -> None:
    probe = path / ".meridian-write-probe"
    probe.write_text("", encoding="utf-8")
    probe.unlink()


def _database(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"status": "DEGRADED", "detail": "database_not_initialized", "schema_version": None, "migration_status": "PENDING"}
    try:
        with sqlite3.connect(f"file:{path}?mode=rw", uri=True) as connection:
            quick = connection.execute("PRAGMA quick_check").fetchone()
            table = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
            version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] if table else None
        healthy = quick == ("ok",) and version == 1
        return {"status": "PASS" if healthy else "DEGRADED", "detail": "healthy" if healthy else "migration_required", "schema_version": version, "migration_status": "CURRENT" if version == 1 else "PENDING"}
    except sqlite3.DatabaseError:
        return {"status": "FAIL", "detail": "DATABASE_CORRUPT_OR_INCOMPATIBLE", "schema_version": None, "migration_status": "FAILED"}
    except OSError:
        return {"status": "FAIL", "detail": "DATABASE_UNAVAILABLE", "schema_version": None, "migration_status": "FAILED"}


def _attempt(name: str, callback: object, *, optional: bool = False) -> Check:
    try:
        if callable(callback):
            callback()
        return Check(name, "PASS", "available")
    except Exception as error:  # noqa: BLE001 - doctor must never traceback
        return Check(name, "WARN" if optional else "FAIL", type(error).__name__)


def report(paths: RuntimePaths | None = None) -> dict[str, object]:
    """Return a machine-readable, bounded and secret-free health report."""
    started = monotonic()
    paths = paths or RuntimePaths.from_environment()
    checks = [
        Check("python", "PASS" if sys.version_info[:2] == (3, 12) else "FAIL", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}; production baseline is 3.12"),
        _attempt("package_import", lambda: __import__("meridian")),
    ]
    try:
        paths.ensure_directories()
        checks.append(Check("runtime_directories", "PASS", str(paths.home)))
        checks.extend(_attempt(f"runtime_write:{name}", lambda path=path: _writable(path)) for name, path in paths.directories().items())
    except Exception as error:  # noqa: BLE001
        checks.append(Check("runtime_directories", "FAIL", type(error).__name__))
    checks.append(_attempt("sqlite", lambda: sqlite3.connect(":memory:").close()))
    database = _database(paths.db)
    checks.extend((Check("database", str(database["status"]), str(database["detail"])), Check("migration", str(database["migration_status"]), str(database["schema_version"]))))
    checks.append(_attempt("config", lambda: load_policies(policy_directory())))
    checks.append(_attempt("timezone", lambda: ZoneInfo("America/New_York")))
    checks.append(_attempt("market_calendar", lambda: __import__("meridian.trading_calendar")))
    for package in ("pydantic", "PyYAML", "mcp"):
        checks.append(_attempt(f"dependency:{package}", lambda package=package: importlib.metadata.version(package)))
    for module in ("meridian.adapters.tradingagents", "meridian.finrlx_runtime", "meridian.mcp_server"):
        installed = importlib.util.find_spec(module) is not None
        checks.append(Check(f"optional:{module.rsplit('.', 1)[-1]}", "PASS" if installed else "WARN", "installed" if installed else "not installed"))
    secret_names = ("DEEPSEEK_API_KEY", "ALPACA_API_KEY", "POLYGON_API_KEY", "MERIDIAN_MCP_BEARER_TOKEN")
    checks.append(Check("secrets", "PASS", "configured=" + str(any(bool(os.environ.get(name)) for name in secret_names)).lower()))
    statuses = {check.status for check in checks}
    return {"schema_version": "meridian-doctor.v1", "status": "FAIL" if "FAIL" in statuses else "DEGRADED" if "WARN" in statuses or "DEGRADED" in statuses else "PASS", "checks": [asdict(check) for check in checks], "paths": paths.as_dict(), "database": database, "project_version": _version(), "elapsed_ms": round((monotonic() - started) * 1000, 1), "network_accessed": False}


def _version() -> str:
    try:
        return importlib.metadata.version("meridian-alpha")
    except importlib.metadata.PackageNotFoundError:
        return "UNAVAILABLE"


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian-runtime")
    parser.add_argument("command", choices=("doctor", "paths", "version"), nargs="?", default="doctor")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    paths = RuntimePaths.from_environment()
    if args.command == "paths":
        payload: object = paths.as_dict()
    elif args.command == "version":
        payload = {"project_version": _version(), "python": sys.version.split()[0], "production_python": "3.12"}
    else:
        payload = report(paths)
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True) if args.json or isinstance(payload, dict) else str(payload))
    return 1 if args.command == "doctor" and isinstance(payload, dict) and payload["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
