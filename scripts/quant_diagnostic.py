"""Predeclare and run synthetic engineering experiments, never market research.

Usage: python scripts/quant_diagnostic.py --output .tmp/quant-v2/diagnostic
Real PIT inputs instead use `meridian quant backtest --dataset ... --plan ...`.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meridian.quant.backtest import QuantDataset  # noqa: E402
from meridian.quant.experiments import (  # noqa: E402
    ExperimentPlan,
    ExperimentVariant,
    isolated_output,
    run_experiments,
)
from meridian.quant.policy import CostPolicy, QuantPolicy  # noqa: E402
from tests.quant_helpers import folds, risk_policy, synthetic_dataset  # noqa: E402


def variants() -> tuple[ExperimentVariant, ...]:
    base = QuantPolicy()
    costs = CostPolicy()
    items = []
    for name in ("CASH", "SPY_BUY_HOLD", "EQUAL_WEIGHT", "A0", "A1", "A2", "A3", "A4"):
        updates: dict[str, object] = {"strategy": name if name.startswith("A") else "A2"}
        if name in {"A0", "EQUAL_WEIGHT"}:
            updates.update({"allocation": "score", "rebalance": "daily", "use_cost_gate": False})
        elif name in {"A1", "A2"}:
            updates.update({"allocation": "score"})
        policy = QuantPolicy.model_validate({**base.model_dump(), **updates})
        items.append(ExperimentVariant(name=name, strategy=name, policy=policy, costs=costs, purpose="PREDECLARED_CONTROL_OR_MAIN_VARIANT"))
    ablations: dict[str, dict[str, object]] = {
        "A4_NO_MOMENTUM": {"use_momentum": False},
        "A4_NO_TREND": {"use_trend": False},
        "A4_NO_VOL_ADJUSTMENT": {"use_volatility_adjustment": False, "allocation": "score"},
        "A4_NO_REGIME": {"strategy": "A3"},
        "A4_NO_COST_GATE": {"use_cost_gate": False, "rebalance": "daily"},
        "A4_CORRELATION_090": {"correlation_limit": Decimal(".9")},
        "A4_WEEKLY": {"rebalance": "weekly"},
        "A4_DAILY": {"rebalance": "daily"},
        "A4_MOM_WEIGHT_065": {"momentum_weight": Decimal(".65"), "trend_weight": Decimal(".35")},
        "A4_MOM_WEIGHT_075": {"momentum_weight": Decimal(".75"), "trend_weight": Decimal(".25")},
        "A4_REGIME_PERCENTILE_075": {"high_volatility_percentile": Decimal(".75")},
        "A4_REGIME_PERCENTILE_085": {"high_volatility_percentile": Decimal(".85")},
    }
    for name, updates in ablations.items():
        policy = QuantPolicy.model_validate({**base.model_dump(), **updates})
        items.append(ExperimentVariant(name=name, strategy=policy.strategy, policy=policy, costs=costs,
                                       purpose="PREDECLARED_ABLATION_OR_PARAMETER_SENSITIVITY"))
    for bps in (10, 25, 50):
        items.append(ExperimentVariant(name="A4_COST_" + str(bps), strategy="A4", policy=base,
                                       costs=CostPolicy(slippage_bps=Decimal(bps)), purpose="PREDECLARED_COST_SENSITIVITY"))
    return tuple(items)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = isolated_output(args.output)
    output.mkdir(parents=True, exist_ok=True)
    dataset = synthetic_dataset()
    dataset_path, plan_path = output / "synthetic-dataset.json", output / "plan.json"
    if not dataset_path.exists():
        dataset_path.write_text(dataset.stable_json() + "\n", encoding="utf-8")
    elif QuantDataset.model_validate_json(dataset_path.read_text(encoding="utf-8")).digest != dataset.digest:
        raise ValueError("DIAGNOSTIC_INPUT_CHANGED_USE_NEW_OUTPUT_DIRECTORY")
    if plan_path.exists():
        plan = ExperimentPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    else:
        plan = ExperimentPlan(declared_at=datetime.now(UTC), folds=folds(dataset), variants=variants(), risk=risk_policy())
        plan_path.write_text(plan.stable_json() + "\n", encoding="utf-8")
    result = run_experiments(dataset, plan, output, diagnostic=True)
    rows = result["results"]
    failures = [r for r in rows if r["status"] != "REPLAY_COMPLETE"] if isinstance(rows, list) else []
    print(json.dumps({"status": result["status"], "financial_alpha_demonstrated": False,
                      "evaluation_count": result["evaluation_count"], "trial_count": result["trial_count"],
                      "failures": failures, "summary_path": result["summary_path"]}, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
