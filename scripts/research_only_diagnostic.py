"""Run the GPT-native research chain against a saved canonical report.

This diagnostic never reads a broker account, writes the paper ledger, creates
an order, or mutates canonical reports.  It reuses only the normalized research
evidence already persisted in a canonical daily report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from meridian.gpt_native_research import CodexResearchModelRuntime, NativeResearchChainOutput


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--model", default="codex-default")
    parser.add_argument(
        "--reasoning-effort",
        choices=("minimal", "low", "medium", "high", "xhigh"),
        default="medium",
    )
    parser.add_argument("--budget-seconds", type=int, default=90)
    parser.add_argument(
        "--schema-smoke",
        action="store_true",
        help="exercise the same structured schema with one evidence item, without the chain workflow",
    )
    return parser


def _load_input(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    intelligence = report.get("research_intelligence")
    research_input = report.get("research_input")
    if not isinstance(intelligence, dict) or not isinstance(research_input, dict):
        raise ValueError("CANONICAL_RESEARCH_INPUT_MISSING")
    evidence = intelligence.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ValueError("CANONICAL_RESEARCH_EVIDENCE_MISSING")
    prior = intelligence.get("prior_memory")
    return {
        "market_context": research_input.get("market_context"),
        "portfolio_context": None,
        "research_question": "Assess the supplied symbols using only normalized evidence.",
        "analysis_cutoff": research_input.get("analysis_cutoff"),
        "evidence": evidence,
        "prior_thesis": prior if isinstance(prior, dict) else None,
        "data_limitations": [
            "Prior research is context only and cannot override current evidence.",
            "No execution authority.",
        ],
    }


def main() -> int:
    args = _parser().parse_args()
    if args.budget_seconds < 1 or args.budget_seconds > 600:
        raise ValueError("BUDGET_SECONDS_OUT_OF_RANGE")
    input_data = _load_input(args.report.resolve())
    runtime = CodexResearchModelRuntime(working_directory=Path(__file__).resolve().parents[1])
    if args.schema_smoke:
        result = runtime.invoke(
            "SCHEMA_SMOKE",
            {"evidence": [input_data["evidence"][0]], "instruction": "Return the smallest valid research chain."},
            NativeResearchChainOutput.model_json_schema(),
            args.budget_seconds,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
        )
    else:
        result = runtime.invoke_chain(
            input_data,
            args.budget_seconds,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
        )
    payload = result.model_dump(mode="json")
    payload["diagnostic_scope"] = {
        "source_report": str(args.report.resolve()),
        "evidence_count": len(input_data["evidence"]),
        "broker_submission": "DISABLED",
        "canonical_runtime_mutated": False,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result.status.value == "SUCCESS" and result.schema_valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
