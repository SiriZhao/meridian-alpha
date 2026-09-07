"""Canonical ``meridian`` command, delegating exclusively to ApplicationService."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from meridian.application import MeridianApplicationService
from meridian.host_readiness import ReadinessStatus, RecommendationReadiness
from meridian.runtime import RuntimePathError


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian")
    parser.add_argument("command", choices=("version", "paths", "doctor", "init", "data-status", "snapshot", "daily", "dip-scout", "forward-status"))
    parser.add_argument("subcommand", nargs="?")
    parser.add_argument("file", nargs="?")
    parser.add_argument("--snapshot")
    parser.add_argument("--market-fixture")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    service = None
    try:
        service = MeridianApplicationService()
        if args.command == "version":
            payload = service.version()
        elif args.command == "paths":
            payload = service.paths_status()
        elif args.command == "doctor":
            payload = service.doctor()
        elif args.command == "init":
            payload = service.init()
        elif args.command == "data-status":
            payload = service.data_status()
        elif args.command == "forward-status":
            payload = service.forward_status()
        elif args.command == "snapshot" and args.subcommand == "validate" and args.file:
            payload = service.snapshot_validate(Path(args.file))
        elif args.command == "daily":
            payload = service.daily(Path(args.snapshot) if args.snapshot else None, Path(args.market_fixture) if args.market_fixture else None)
        elif args.command == "dip-scout" and args.file:
            payload = service.dip_scout(Path(args.file))
        else:
            raise ValueError("invalid command arguments")
    except (OSError, ValueError, RuntimePathError, sqlite3.Error) as error:
        if isinstance(error, RuntimePathError):
            code, category, message = "MERIDIAN_RUNTIME_UNAVAILABLE", "USER_FIXABLE", str(error)
        elif isinstance(error, OSError):
            code, category, message = "MERIDIAN_FILESYSTEM_ERROR", "USER_FIXABLE", "Check the indicated path, permissions and file locks; choose a writable MERIDIAN_HOME."
        elif isinstance(error, sqlite3.Error):
            code, category, message = "MERIDIAN_DATABASE_ERROR", "USER_FIXABLE", "Run doctor; check database permissions, locks and schema. Preserve the database."
        else:
            code, category, message = "MERIDIAN_INPUT_INVALID", "DATA_QUALITY", "Supply a valid sanitized HostAccountSnapshotEnvelope and market fixture; run snapshot validate first."
        payload = {"status": "FAILED", "runtime_status": "FAILED", "error_code": code, "category": category, "message": message, "path": str(getattr(error, "filename", None) or ""), "logs_path": str(service.paths.logs) if service else None, "automatic_recovery": "No destructive recovery attempted"}
        payload.update({"run_id": "failed-" + uuid4().hex,
                        "readiness": RecommendationReadiness(runtime_health=ReadinessStatus.FAILED).model_dump(mode="json"),
                        "errors": [code], "next_actions": [message], "output_files": {}})
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 3
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))
    else:
        print("MERIDIAN ALPHA")
        print("Status: " + str(payload.get("status", "PASS")))
        print(json.dumps(payload, ensure_ascii=False, default=str, indent=2, sort_keys=True))
    if payload.get("exit_code") == 3:
        return 3
    status = str(payload.get("status", "PASS"))
    return 0 if status in {"PASS", "INIT_COMPLETE", "INIT_ALREADY_COMPLETE", "NO_ACTION", "NO_CAPITAL", "DRAFT"} else 2 if status in {"DEGRADED", "BLOCKED_STALE_ACCOUNT", "BLOCKED_STALE_MARKET", "INSUFFICIENT_FORWARD_EVIDENCE"} else 3


if __name__ == "__main__":
    raise SystemExit(main())
