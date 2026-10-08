"""New, isolated frozen challenger registry; never modifies V2.1 archives."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meridian.quant.experiments import (  # noqa: E402
    ChallengerExperimentPlan,
    ChallengerExperimentVariant,
    isolated_output,
    run_experiments,
)
from meridian.quant.policy import ChallengerPolicy, CostPolicy, QuantPolicy  # noqa: E402
from tests.quant_helpers import folds, risk_policy, synthetic_dataset  # noqa: E402


def variants() -> tuple[ChallengerExperimentVariant, ...]:
    rows = []
    controls, costs = QuantPolicy(), CostPolicy()
    for label in ("CASH", "SPY_BUY_HOLD", "SPY_POLICY", "EQUAL_WEIGHT", "A0", "A1", "A2", "A3", "A4"):
        policy = QuantPolicy.model_validate({**controls.model_dump(), "strategy": label if label.startswith("A") else "A2"})
        rows.append(ChallengerExperimentVariant(name=label, strategy=label, policy=policy, costs=costs,
            purpose="COMMON_HARD_LIMITS_COSTS_AND_TIMING; SPY_BUY_HOLD_IS_UNCONSTRAINED_REFERENCE"))
    base = ChallengerPolicy()
    experiments = [("V22", base, costs, "FIXED_CHALLENGER")]
    for group in ("absolute", "relative", "trend"):
        policy = ChallengerPolicy.model_validate({**base.model_dump(), "neutral_groups": [group], "diagnostic_exposure": ".25"})
        experiments.append(("V22_NEUTRAL_" + group.upper(), policy, costs, "NEUTRAL_REPLACEMENT_MATCHED_NOMINAL_BUDGET; AUDIT_REALIZED_EXPOSURE"))
    matched = ChallengerPolicy.model_validate({**base.model_dump(), "diagnostic_exposure": ".25"})
    experiments.append(("V22_MATCHED_BUDGET", matched, costs, "MATCHED_NOMINAL_BUDGET_ABLATION_CONTROL"))
    for blend in (".15", ".25"):
        policy = ChallengerPolicy.model_validate({**base.model_dump(), "maximum_rank_blend": blend})
        experiments.append(("V22_RANK_BLEND_" + blend, policy, costs, "PREDECLARED_LOCAL_PERTURBATION"))
    for bps in (10, 25, 50):
        experiments.append(("V22_COST_" + str(bps), base, CostPolicy(slippage_bps=Decimal(bps)), "COST_STRESS"))
    for name, challenger, friction, purpose in experiments:
        rows.append(ChallengerExperimentVariant(name=name, strategy="V22", policy=challenger.controls,
            challenger=challenger, costs=friction, purpose=purpose))
    return tuple(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    output = isolated_output(args.output)
    output.mkdir(parents=True, exist_ok=True)
    dataset = synthetic_dataset()
    from meridian.quant.integration import immutable_record
    immutable_record(output / "synthetic-dataset.json", dataset.stable_json() + "\n")
    plan_path = output / "plan.json"
    if plan_path.exists():
        plan = ChallengerExperimentPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
        if plan.variants != variants():
            raise ValueError("CHALLENGER_FROZEN_PARAMETERS_CHANGED_USE_NEW_DIRECTORY")
    else:
        plan = ChallengerExperimentPlan(declared_at=datetime.now(UTC), folds=folds(dataset), variants=variants(), risk=risk_policy())
        immutable_record(plan_path, plan.stable_json() + "\n")
    result = run_experiments(dataset, plan, output, diagnostic=True)
    rows = result["results"]
    failures = [r for r in rows if r["status"] != "REPLAY_COMPLETE"] if isinstance(rows, list) else []
    print(json.dumps({"status": result["status"], "evaluations": result["evaluation_count"],
        "variants": result["trial_count"], "failures": failures, "summary_path": result["summary_path"]}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
