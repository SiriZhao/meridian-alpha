"""Research-only commands with explicit files; never instantiate daily runtime."""

import argparse
import json
from pathlib import Path

from meridian.quant.backtest import QuantDataset
from meridian.quant.experiments import ExperimentPlan, run_experiments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meridian quant")
    parser.add_argument("command", choices=("inspect", "backtest"))
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--diagnostic", action="store_true", help="allow synthetic engineering replays; never financial evidence")
    args = parser.parse_args(argv)
    try:
        dataset = QuantDataset.model_validate_json(args.dataset.read_text(encoding="utf-8"))
        if args.command == "inspect":
            payload = {"status": dataset.evidence_status, "dataset_hash": dataset.digest,
                       "universe_basis": dataset.universe_basis, "symbols": [s.canonical_symbol for s in dataset.series],
                       "corporate_action_coverage": str(dataset.corporate_actions_covered_until), "broker_submission": "DISABLED"}
        else:
            if args.plan is None or args.output is None:
                parser.error("backtest requires --plan and --output")
            plan = ExperimentPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
            payload = run_experiments(dataset, plan, args.output, diagnostic=args.diagnostic)
        print(json.dumps(payload, indent=2, allow_nan=False))
        return 1 if payload["status"] == "INSUFFICIENT_EVIDENCE" else 0
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "INSUFFICIENT_EVIDENCE", "error_type": type(error).__name__,
                          "reason": str(error) if isinstance(error, ValueError) else "EXPLICIT_FILE_ACCESS_FAILED",
                          "broker_submission": "DISABLED"}))
        return 1
