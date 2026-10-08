"""Local-only Meridian runtime diagnostics.

This module intentionally performs no network request, provider probe, model
initialization, or database migration.  It is safe to call as a startup
preflight and returns only sanitized state.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import re
import sqlite3
import subprocess
import sys
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from time import monotonic
from zoneinfo import ZoneInfo

from meridian.audit import SCHEMA_VERSION
from meridian.cache_health import CacheHealth, CacheHealthStatus, check_cache_health
from meridian.codex_provider import AUTH_MODE, discover_codex_executable
from meridian.config import load_policies
from meridian.readonly_storage import ReadOnlyStorageRefusal, connect_read_only
from meridian.runtime import RuntimePaths, policy_directory, project_root
from meridian.runtime_io import FilesystemFailure


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def _writable(path: Path) -> None:
    from meridian.runtime_io import write_probe
    write_probe(path)


def _database(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"status": "DEGRADED", "detail": "database_not_initialized", "schema_version": None, "migration_status": "PENDING"}
    try:
        with closing(connect_read_only(path)) as connection:
            quick = connection.execute("PRAGMA quick_check").fetchone()
            table = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'").fetchone()
            version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] if table else None
        if version is not None and version > SCHEMA_VERSION:
            return {"status": "FAIL", "detail": "MERIDIAN_DATABASE_NEWER_SCHEMA: upgrade Meridian; preserve DB", "schema_version": version, "migration_status": "FAILED"}
        healthy = quick == ("ok",) and version == SCHEMA_VERSION
        return {"status": "PASS" if healthy else "DEGRADED", "detail": "healthy" if healthy else "migration_required", "schema_version": version, "migration_status": "CURRENT" if version == SCHEMA_VERSION else "PENDING"}
    except ReadOnlyStorageRefusal as error:
        return {"status": "FAIL", "detail": str(error), "schema_version": None, "migration_status": "NOT_VERIFIED"}
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
        return Check(name, "WARN" if optional else "FAIL", json.dumps(error.detail) if isinstance(error, FilesystemFailure) else type(error).__name__ + "; inspect the corresponding path/config in this report and rerun doctor")


def _codex_version(executable: str | None) -> tuple[str, str]:
    if executable is None:
        return "FAIL", "CODEX_NOT_INSTALLED"
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "FAIL", "CODEX_VERSION_UNAVAILABLE"
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", result.stdout + result.stderr)
    if result.returncode != 0 or match is None:
        return "FAIL", "CODEX_VERSION_UNAVAILABLE"
    version = tuple(int(part) for part in match.groups())
    return ("PASS" if version >= (0, 153, 0) else "FAIL"), ".".join(match.groups())


def _skill_check() -> tuple[Check, dict[str, object]]:
    development_source = project_root() / "skills" / "meridian-alpha"
    packaged_source = Path(__file__).resolve().parent / "skills" / "meridian-alpha"
    source = development_source if development_source.is_dir() else packaged_source
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    installed = codex_home / "skills" / "meridian-alpha"

    def tree_hash(root: Path, relative_files: list[Path]) -> str:
        digest = hashlib.sha256()
        for relative in relative_files:
            digest.update(relative.as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update((root / relative).read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    try:
        files = sorted(
            path.relative_to(source)
            for path in source.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.suffix.lower() not in {".pyc", ".pyo"}
        )
        source_hash = tree_hash(source, files)
        installed_hash = tree_hash(installed, files)
    except OSError:
        return Check("skill_installation", "INFO", "MERIDIAN_SKILL_NOT_INSTALLED"), {
            "source": str(source), "installed": str(installed), "hash_match": False
        }
    matched = source_hash == installed_hash
    return Check(
        # A globally installed Skill may intentionally lag a fresh checkout.
        # Keep the mismatch visible without making runtime health fail closed;
        # the installed Skill is not an execution or persistence dependency.
        "skill_installation", "PASS" if matched else "INFO",
        "source_and_installed_hash_match" if matched else "MERIDIAN_SKILL_HASH_MISMATCH",
    ), {"source": str(source), "installed": str(installed), "source_hash": source_hash,
        "installed_hash": installed_hash, "hash_match": matched, "file_count": len(files)}


def _mcp_check() -> tuple[Check, dict[str, object]]:
    try:
        from meridian.mcp_server import registered_tool_names

        names = registered_tool_names()
    except Exception:  # noqa: BLE001 - doctor must remain diagnostics-only
        return Check("mcp_tools", "FAIL", "MCP_TOOL_REGISTRATION_UNAVAILABLE"), {
            "registered": [], "configured": False
        }
    required = {
        "runtime_status", "market_snapshot", "account_snapshot", "company_facts",
        "research_packet", "quant_metrics", "portfolio_context", "risk_analysis",
        "forward_evidence", "daily_closure", "audit_lookup",
    }
    configured = False
    executable = discover_codex_executable()
    if executable:
        try:
            result = subprocess.run(
                [executable, "mcp", "list"], capture_output=True, text=True,
                encoding="utf-8", errors="replace", timeout=5, check=False,
            )
            configured = result.returncode == 0 and "meridian-alpha" in result.stdout
        except (OSError, subprocess.TimeoutExpired):
            configured = False
    missing = sorted(required - set(names))
    return Check(
        "mcp_tools", "PASS" if not missing and configured else "INFO",
        "registered_and_discovered" if not missing and configured else (
            "missing=" + ",".join(missing) if missing else "MCP_NOT_DISCOVERED_BY_CODEX"
        ),
    ), {"registered": sorted(names), "configured": configured, "missing": missing}


def report(
    paths: RuntimePaths | None = None, *, probe_writes: bool = True
) -> dict[str, object]:
    """Return a machine-readable, bounded and secret-free health report.

    ``doctor`` uses the default active probes. Read-only MCP hosts must not
    treat their intentionally sandboxed filesystem as a runtime failure.
    """
    started = monotonic()
    paths = paths or RuntimePaths.from_environment()
    checks = [
        Check("python", "PASS" if sys.version_info[:2] == (3, 12) else "FAIL", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}; production baseline is 3.12"),
        Check("project_venv", "PASS" if sys.prefix != sys.base_prefix else "FAIL", "project virtual environment required"),
        _attempt("package_import", lambda: __import__("meridian")),
    ]
    cache_health = None
    try:
        if probe_writes:
            paths.ensure_directories()
        present = all(path.is_dir() for path in paths.directories().values())
        checks.append(Check("runtime_directories", "PASS" if present else "INFO",
                            str(paths.home) if present else "DIRECTORIES_NOT_PRESENT_NO_READ_ONLY_CREATION"))
        if probe_writes:
            checks.extend(_attempt(f"runtime_write:{name}", lambda path=path: _writable(path)) for name, path in paths.directories().items() if name != "cache")
            cache_health = check_cache_health(paths.cache)
            cache_check_status = "PASS" if cache_health.status is CacheHealthStatus.READY else "WARN"
            checks.append(Check("cache_health", cache_check_status, f"{cache_health.status.value}:{cache_health.error_code or 'NONE'}"))
        else:
            checks.append(Check("runtime_write", "SKIPPED", "READ_ONLY_MCP_HOST"))
            cache_health = {
                "status": "NOT_PROBED_READ_ONLY_HOST",
                "path": str(paths.cache),
                "error_code": None,
                "next_action": "Run meridian doctor --json outside the read-only host to verify writable runtime paths.",
            }
    except Exception:  # noqa: BLE001
        checks.append(Check("runtime_directories", "FAIL", f"{paths.home}: create failed; set MERIDIAN_HOME to an absolute writable user directory"))
    checks.append(_attempt("sqlite", lambda: sqlite3.connect(":memory:").close()))
    database = _database(paths.db)
    checks.extend((Check("database", str(database["status"]), str(database["detail"])), Check("migration", str(database["migration_status"]), str(database["schema_version"]))))
    checks.append(_attempt("config", lambda: load_policies(policy_directory())))
    checks.append(_attempt("timezone", lambda: ZoneInfo("America/New_York")))
    checks.append(_attempt("market_calendar", lambda: __import__("meridian.trading_calendar")))
    codex_executable = discover_codex_executable()
    checks.append(
        Check(
            "codex_cli",
            "PASS" if codex_executable else "INFO",
            "available; authentication is managed by Codex CLI"
            if codex_executable
            else "CODEX_NOT_INSTALLED",
        )
    )
    codex_version_status, codex_version = _codex_version(codex_executable) if probe_writes else ("INFO", "NOT_PROBED_READ_ONLY_HOST")
    checks.append(Check("codex_compatibility", codex_version_status if codex_executable else "INFO", f"{codex_version}; minimum 0.153.0"))
    checks.append(Check("codex_auth_mode", "PASS", AUTH_MODE))
    skill_check, skill = _skill_check()
    checks.append(skill_check)
    mcp_check, mcp = _mcp_check() if probe_writes else (Check("mcp_tools", "INFO", "NOT_PROBED_READ_ONLY_HOST"), {"configured": None, "registered": [], "discovery_status": "NOT_PROBED"})
    checks.append(mcp_check)
    for package in ("pydantic", "PyYAML", "mcp"):
        checks.append(_attempt(f"dependency:{package}", lambda package=package: importlib.metadata.version(package)))
    for module in ("meridian.adapters.tradingagents", "meridian.finrlx_runtime", "meridian.mcp_server"):
        installed = importlib.util.find_spec(module) is not None
        checks.append(Check(f"optional:{module.rsplit('.', 1)[-1]}", "UNKNOWN", "adapter present; provider not probed" if installed else "not installed"))
    secret_names = ("ALPACA_API_KEY", "POLYGON_API_KEY", "MERIDIAN_MCP_BEARER_TOKEN")
    checks.append(Check("secrets", "PASS", "configured=" + str(any(bool(os.environ.get(name)) for name in secret_names)).lower()))
    statuses = {check.status for check in checks}
    return {"schema_version": "meridian-doctor.v2", "status": "FAIL" if "FAIL" in statuses else "DEGRADED" if "WARN" in statuses or "DEGRADED" in statuses else "PASS", "checks": [asdict(check) for check in checks], "paths": {**paths.as_dict(), "database": str(paths.db), "policies": str(policy_directory())}, "python_executable": sys.executable, "virtual_environment": sys.prefix != sys.base_prefix, "database": database, "cache": cache_health.as_dict() if isinstance(cache_health, CacheHealth) else cache_health if cache_health is not None else {"status": "BLOCKED", "error_code": "CACHE_HEALTH_UNAVAILABLE"}, "skill": skill, "mcp": mcp, "project_version": _version(), "elapsed_ms": round((monotonic() - started) * 1000, 1), "network_accessed": False}


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
