"""Reproducible synthetic engineering registry, explicitly not financial OOS."""
import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from meridian.quant.experiments import isolated_output  # noqa: E402
from meridian.quant.flagship_experiments import (  # noqa: E402
    FlagshipExperimentPlan,
    FlagshipVariant,
    run_flagship_experiments,
)
from meridian.quant.flagship_policy import FlagshipPolicy  # noqa: E402
from meridian.quant.flagship_replay import flagship_engine_hash  # noqa: E402
from meridian.quant.integration import immutable_record  # noqa: E402
from meridian.quant.policy import CostPolicy  # noqa: E402
from tests.quant_helpers import folds, risk_policy, synthetic_dataset  # noqa: E402


def variants() -> tuple[FlagshipVariant, ...]:
    rows = [FlagshipVariant(name=s, strategy=s) for s in ('CASH', 'SPY_BUY_HOLD', 'SPY_POLICY', 'EQUAL_WEIGHT', 'A0', 'A1', 'A2', 'A3', 'A4', 'V22')]
    for method in ('SHRUNK_RISK_BUDGET', 'COST_CONSTRAINED', 'REGIME_CONDITIONED'):
        rows.append(FlagshipVariant(name='V23_' + method, strategy='V23', flagship=FlagshipPolicy(construction=method)))
    for bps in (0, 25, 50):
        costs = CostPolicy(slippage_bps=Decimal(bps), commission_per_order=Decimal(0 if bps == 0 else 1))
        rows.extend([FlagshipVariant(name='V22_COST_' + str(bps), strategy='V22', costs=costs),
            FlagshipVariant(name='V23_COST_' + str(bps), strategy='V23', flagship=FlagshipPolicy(), costs=costs)])
    for value in ('.08', '.12'):
        rows.append(FlagshipVariant(name='V23_RISK_WEIGHT_' + value, strategy='V23', flagship=FlagshipPolicy(risk_weight=Decimal(value))))
    rows.append(FlagshipVariant(name='V23_NO_TURNOVER_OR_COST_PENALTY', strategy='V23',
        flagship=FlagshipPolicy(turnover_weight=Decimal(0), cost_weight=Decimal(0))))
    return tuple(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--freeze-only', action='store_true')
    args = parser.parse_args()
    output = isolated_output(args.output)
    dataset = synthetic_dataset()
    path = output / 'plan.json'
    if path.exists():
        plan = FlagshipExperimentPlan.model_validate_json(path.read_text(encoding='utf-8'))
        if plan.variants != variants():
            raise ValueError('V23_FROZEN_PARAMETERS_CHANGED')
    else:
        plan = FlagshipExperimentPlan(declared_at=datetime.now(UTC), dataset_hash=dataset.digest,
            engine_hash=flagship_engine_hash(), folds=folds(dataset), variants=variants(), risk=risk_policy())
        immutable_record(path, plan.stable_json() + '\n')
        immutable_record(output / 'synthetic-dataset.json', dataset.stable_json() + '\n')
    if args.freeze_only:
        print(json.dumps({'status': 'FROZEN_BEFORE_EVALUATION', 'engine_hash': plan.engine_hash}))
        return 0
    summary = run_flagship_experiments(dataset, plan, output, diagnostic=True)
    results = summary['results']
    if not isinstance(results, list):
        raise ValueError('V23_RESULT_SCHEMA_INVALID')
    failures = [r for r in results if r['status'] != 'REPLAY_COMPLETE']
    print(json.dumps({'evaluations': summary['evaluation_count'], 'failures': failures, 'evidence_level': summary['evidence_level']}))
    return int(bool(failures))


if __name__ == '__main__':
    raise SystemExit(main())
