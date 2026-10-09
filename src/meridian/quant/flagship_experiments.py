"""Frozen V2.3 experiments over the existing strict chronological replay."""
import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from meridian.config import RiskPolicy
from meridian.quant.backtest import QuantDataset, WalkForwardFold, WalkForwardRunner
from meridian.quant.experiments import isolated_output
from meridian.quant.flagship_metrics import flagship_metrics
from meridian.quant.flagship_policy import FlagshipPolicy
from meridian.quant.flagship_replay import FlagshipWalkForwardRunner, flagship_engine_hash
from meridian.quant.integration import immutable_record
from meridian.quant.policy import ChallengerPolicy, CostPolicy, QuantPolicy
from meridian.schemas import StableModel


class FlagshipVariant(StableModel):
    name: str = Field(min_length=1, max_length=80)
    strategy: Literal['CASH', 'SPY_BUY_HOLD', 'SPY_POLICY', 'EQUAL_WEIGHT', 'A0', 'A1', 'A2', 'A3', 'A4', 'V22', 'V23']
    flagship: FlagshipPolicy | None = None
    costs: CostPolicy = Field(default_factory=CostPolicy)

    @model_validator(mode='after')
    def coherent(self) -> 'FlagshipVariant':
        if (self.strategy == 'V23') != (self.flagship is not None):
            raise ValueError('V23_VARIANT_POLICY_REQUIRED')
        return self


class FlagshipExperimentPlan(StableModel):
    version: Literal['quant-experiment-v2.3'] = 'quant-experiment-v2.3'
    declared_at: AwareDatetime
    dataset_hash: str
    engine_hash: str
    folds: tuple[WalkForwardFold, ...] = Field(min_length=1, max_length=8)
    variants: tuple[FlagshipVariant, ...] = Field(min_length=1, max_length=32)
    risk: RiskPolicy
    automatic_selection: Literal[False] = False
    final_oos_tuning: Literal[False] = False
    label_horizon_sessions: Literal[1] = 1

    @model_validator(mode='after')
    def coherent(self) -> 'FlagshipExperimentPlan':
        if len({v.name for v in self.variants}) != len(self.variants) or len({f.name for f in self.folds}) != len(self.folds):
            raise ValueError('V23_DUPLICATE_EXPERIMENT_IDENTITY')
        ordered = sorted(self.folds, key=lambda f: f.test_start)
        if any(a.test_end >= b.test_start for a, b in zip(ordered, ordered[1:], strict=False)):
            raise ValueError('V23_OVERLAPPING_FINAL_OOS_FOLDS')
        if any(f.embargo_sessions < self.label_horizon_sessions for f in self.folds):
            raise ValueError('V23_LABEL_EMBARGO_TOO_SHORT')
        return self


def run_flagship_experiments(dataset: QuantDataset, plan: FlagshipExperimentPlan,
                             output: Path, *, diagnostic: bool = False) -> dict[str, object]:
    plan = FlagshipExperimentPlan.model_validate(plan.model_dump())
    if dataset.digest != plan.dataset_hash or flagship_engine_hash() != plan.engine_hash:
        raise ValueError('V23_SEALED_INPUT_OR_ENGINE_CHANGED')
    output = isolated_output(output)
    plan_text = plan.stable_json() + '\n'
    plan_hash = hashlib.sha256(plan_text.encode()).hexdigest()
    immutable_record(output / 'plan.json', plan_text)  # Seal before any evaluation.
    registration = hashlib.sha256((dataset.digest + plan.engine_hash).encode()).hexdigest()
    immutable_record(output / 'final-oos-registrations' / (registration + '.json'), plan_text)
    baseline = WalkForwardRunner(dataset, diagnostic=diagnostic)
    results = []
    for fold in plan.folds:
        for partition in ('validation', 'test'):
            for variant in plan.variants:
                if flagship_engine_hash() != plan.engine_hash:
                    raise ValueError('V23_SOURCE_CHANGED_DURING_EVALUATION')
                try:
                    if variant.flagship is not None:
                        runner = FlagshipWalkForwardRunner(dataset, variant.flagship, diagnostic=diagnostic)
                        runner._feature_cache = baseline._feature_cache
                        runner._challenger_cache = baseline._challenger_cache
                        replay = runner.run_flagship(variant.costs, plan.risk, fold, partition=partition)
                    else:
                        controls = QuantPolicy.model_validate({'strategy': variant.strategy if variant.strategy in {'A0', 'A1', 'A2', 'A3', 'A4'} else 'A4'})
                        replay = baseline.run(controls, variant.costs, plan.risk, fold,
                            strategy=variant.strategy, partition='test' if partition == 'test' else 'validation',
                            challenger=ChallengerPolicy(controls=controls) if variant.strategy == 'V22' else None)
                    if flagship_engine_hash() != plan.engine_hash:
                        raise ValueError('V23_SOURCE_CHANGED_DURING_EVALUATION')
                    text = replay.stable_json() + '\n'
                    digest = hashlib.sha256(text.encode()).hexdigest()
                    immutable_record(output / 'replays' / (digest + '.json'), text)
                    row = {'status': 'REPLAY_COMPLETE', 'replay_hash': digest, 'metrics': flagship_metrics(replay)}
                except ValueError as error:
                    row = {'status': 'BLOCKED', 'reason': str(error), 'metrics': None}
                results.append({'variant': variant.name, 'fold': fold.name, 'partition': partition, **row})
    summary = {'version': 'quant-v23-experiment-summary', 'plan_hash': plan_hash,
        'engine_hash': plan.engine_hash, 'dataset_hash': dataset.digest, 'evidence_level': dataset.evidence_status,
        'financial_alpha_demonstrated': False, 'automatic_promotion': False, 'results': results,
        'evaluation_count': len(results), 'trial_count': len(plan.variants),
        'limitations': ['RISK_TRANSFORMATION_IS_NOT_ALPHA', 'ONE_SESSION_LABEL_EMBARGO_NOT_MULTI_HORIZON_IC_PURGE',
            'ADJUSTED_COORDINATE_UNITS_NOT_RAW_SPLIT_DIVIDEND_CASH_LEDGER',
            'MULTIPLE_TRIALS_NO_BEST_VARIANT_PROMOTION', 'SPY_BUY_HOLD_UNCONSTRAINED_REFERENCE']}
    text = json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + '\n'
    immutable_record(output / 'summary.json', text)
    return summary
