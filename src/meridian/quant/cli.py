"""Research-only commands with explicit files; never instantiate daily runtime."""

import argparse
import json
from datetime import datetime
from pathlib import Path

from meridian.quant.backtest import QuantDataset
from meridian.quant.experiments import ChallengerExperimentPlan, ExperimentPlan, run_experiments


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meridian quant")
    parser.add_argument("command", choices=("inspect", "backtest", "packet"))
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--cutoff", type=datetime.fromisoformat)
    parser.add_argument("--diagnostic", action="store_true", help="allow synthetic engineering replays; never financial evidence")
    args = parser.parse_args(argv)
    try:
        dataset = QuantDataset.model_validate_json(args.dataset.read_text(encoding="utf-8"))
        if args.command == "inspect":
            payload = {"status": dataset.evidence_status, "dataset_hash": dataset.digest,
                       "universe_basis": dataset.universe_basis, "symbols": [s.canonical_symbol for s in dataset.series],
                       "corporate_action_coverage": str(dataset.corporate_actions_covered_until), "broker_submission": "DISABLED"}
        elif args.command == "packet":
            from meridian.config import load_policies
            from meridian.quant.packet import build_research_packet
            from meridian.quant.policy import ChallengerPolicy
            if args.cutoff is None:
                parser.error("packet requires --cutoff with timezone")
            symbols = tuple(m.symbol for m in dataset.memberships if m.known_at <= args.cutoff
                            and m.start <= args.cutoff.date() and (m.end is None or m.end >= args.cutoff.date()))
            packet = build_research_packet({s.canonical_symbol: s for s in dataset.series}, symbols,
                cutoff=args.cutoff, policies=load_policies(Path(__file__).resolve().parents[3] / "policies"),
                policy=ChallengerPolicy(), metadata=tuple(m for m in dataset.security_metadata if m.known_at <= args.cutoff),
                diagnostic=args.diagnostic)
            payload = {"status": "RESEARCH_ONLY", "packet": packet.model_dump(mode="json")}
        else:
            if args.plan is None or args.output is None:
                parser.error("backtest requires --plan and --output")
            raw = json.loads(args.plan.read_text(encoding="utf-8"))
            plan = ChallengerExperimentPlan.model_validate(raw) if raw.get("version") == "quant-experiment-plan-v2.2" else ExperimentPlan.model_validate(raw)
            payload = run_experiments(dataset, plan, args.output, diagnostic=args.diagnostic)
        print(json.dumps(payload, indent=2, allow_nan=False))
        return 1 if payload["status"] == "INSUFFICIENT_EVIDENCE" else 0
    except (ValueError, OSError) as error:
        print(json.dumps({"status": "INSUFFICIENT_EVIDENCE", "error_type": type(error).__name__,
                          "reason": str(error) if isinstance(error, ValueError) else "EXPLICIT_FILE_ACCESS_FAILED",
                          "broker_submission": "DISABLED"}))
        return 1
