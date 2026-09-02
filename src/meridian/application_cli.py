"""Canonical ``meridian`` command, delegating exclusively to ApplicationService."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from meridian.application import MeridianApplicationService


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian")
    parser.add_argument("command", choices=("version", "paths", "doctor", "init", "data-status", "snapshot", "daily", "dip-scout", "forward-status"))
    parser.add_argument("subcommand", nargs="?")
    parser.add_argument("file", nargs="?")
    parser.add_argument("--snapshot")
    parser.add_argument("--market-fixture")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    service = MeridianApplicationService()
    try:
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
        elif args.command == "daily" and args.snapshot:
            payload = service.daily(Path(args.snapshot), Path(args.market_fixture) if args.market_fixture else None)
        elif args.command == "dip-scout" and args.file:
            payload = service.dip_scout(Path(args.file))
        else:
            raise ValueError("invalid command arguments")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAILED", "error": type(error).__name__, "message": "Input or runtime state was rejected; no order was created."}, sort_keys=True))
        return 3
    print(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))
    status = str(payload.get("status", "PASS"))
    return 0 if status in {"PASS", "INIT_COMPLETE", "INIT_ALREADY_COMPLETE", "NO_ACTION", "DRAFT"} else 2 if status in {"DEGRADED", "BLOCKED_STALE_ACCOUNT", "BLOCKED_STALE_MARKET", "INSUFFICIENT_FORWARD_EVIDENCE"} else 3
