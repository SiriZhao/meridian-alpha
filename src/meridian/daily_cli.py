"""Additive safe CLI for sanitized snapshot validation and daily closure."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from meridian.config import load_policies
from meridian.daily_closure import (
    DailyClosureService,
    load_market_fixture,
    load_snapshot,
    persist_report,
)
from meridian.runtime import RuntimePaths, policy_directory


def main() -> int:
    parser = argparse.ArgumentParser(prog="meridian")
    commands = parser.add_subparsers(dest="command", required=True)
    snapshot = commands.add_parser("snapshot")
    snapshot_sub = snapshot.add_subparsers(dest="snapshot_command", required=True)
    validate = snapshot_sub.add_parser("validate")
    validate.add_argument("file")
    validate.add_argument("--json", action="store_true")
    daily = commands.add_parser("daily")
    daily.add_argument("--snapshot", required=True)
    daily.add_argument("--market-fixture")
    daily.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        account = load_snapshot(Path(args.file if args.command == "snapshot" else args.snapshot))
        if args.command == "snapshot":
            payload = {"valid": True, "snapshot_id": account.snapshot_id, "as_of": account.as_of.isoformat(), "freshness": account.freshness_state.value, "sync": account.sync_state.value, "sanitized": True}
            print(json.dumps(payload, sort_keys=True) if args.json else f"Snapshot valid: {payload['freshness']} / {payload['sync']}")
            return 0 if account.freshness_state.value in {"VERIFIED", "RECENT"} else 2
        quotes = load_market_fixture(Path(args.market_fixture)) if args.market_fixture else {}
        result = DailyClosureService(load_policies(policy_directory())).run(account, quotes, cutoff=datetime.now(account.as_of.tzinfo))
        persisted = persist_report(result, RuntimePaths.from_environment())
        payload = {**persisted.report, "report_json": str(persisted.report_json), "report_markdown": str(persisted.report_markdown)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True))
        else:
            print(f"{payload['status']} — manual only; report: {persisted.report_markdown}")
        return 0 if payload["status"] in {"NO_ACTION", "DRAFT"} else 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "FAILED", "error": type(error).__name__, "message": "Snapshot or market input was rejected; no order draft was created."}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
