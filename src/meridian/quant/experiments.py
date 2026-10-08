"""Frozen experiment manifests and append-only, hash-bound evaluation records."""

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from meridian.config import RiskPolicy
from meridian.quant.backtest import QuantDataset, WalkForwardFold, WalkForwardRunner
from meridian.quant.integration import immutable_record
from meridian.quant.metrics import performance
from meridian.quant.policy import CostPolicy, QuantPolicy
from meridian.quant.version import ENGINE_SOURCE_HASH
from meridian.schemas import StableModel


class ExperimentVariant(StableModel):
    name: str
    strategy: Literal["CASH", "SPY_BUY_HOLD", "EQUAL_WEIGHT", "A0", "A1", "A2", "A3", "A4"]
    policy: QuantPolicy
    costs: CostPolicy
    purpose: str


class ExperimentPlan(StableModel):
    version: str = "quant-experiment-plan-v1"
    declared_at: datetime
    folds: tuple[WalkForwardFold, ...]
    variants: tuple[ExperimentVariant, ...]
    risk: RiskPolicy
    selection: Literal["NONE_FIXED_PREDECLARED_MODELS"] = "NONE_FIXED_PREDECLARED_MODELS"
    final_oos_tuning: Literal[False] = False

    @model_validator(mode="after")
    def coherent(self) -> "ExperimentPlan":
        if not self.folds or not self.variants:
            raise ValueError("EXPERIMENT_EMPTY_PLAN")
        if len({v.name for v in self.variants}) != len(self.variants):
            raise ValueError("EXPERIMENT_DUPLICATE_VARIANT")
        if len({f.name for f in self.folds}) != len(self.folds):
            raise ValueError("EXPERIMENT_DUPLICATE_FOLD")
        ordered = sorted(self.folds, key=lambda f: f.test_start)
        if any(a.test_end >= b.test_start for a, b in zip(ordered, ordered[1:], strict=False)):
            raise ValueError("EXPERIMENT_OVERLAPPING_OOS_FOLDS")
        for variant in self.variants:
            if variant.strategy.startswith("A") and variant.strategy != variant.policy.strategy:
                raise ValueError("EXPERIMENT_STRATEGY_MISMATCH")
            if variant.policy.mode != "QUANT_V1_BASELINE" or variant.policy.paper_approved:
                raise ValueError("EXPERIMENT_MUST_NOT_ENABLE_PAPER")
        return self

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


def isolated_output(output: Path) -> Path:
    resolved = output.resolve()
    canonical = Path("E:/MeridianAlphaRuntime").resolve()
    if resolved == canonical or canonical in resolved.parents:
        raise ValueError("QUANT_EXPERIMENT_CANONICAL_RUNTIME_FORBIDDEN")
    return resolved


def run_experiments(dataset: QuantDataset, plan: ExperimentPlan, output: Path,
                    *, diagnostic: bool = False) -> dict[str, object]:
    output = isolated_output(output)
    # Sealing precedes evaluating either validation or final OOS. Reusing the
    # same dataset/fold under changed parameters in this registry is rejected.
    manifest = {"dataset_hash": dataset.digest, "plan_hash": plan.digest,
                "engine_source_hash": ENGINE_SOURCE_HASH,
                "dataset_evidence": dataset.evidence_status, "plan": plan.model_dump(mode="json")}
    text = json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    immutable_record(output / "plans" / (plan.digest + "-" + ENGINE_SOURCE_HASH + ".json"), text)
    for fold in plan.folds:
        key_source = dataset.digest + fold.test_start.isoformat() + fold.test_end.isoformat()
        if diagnostic and dataset.evidence_status == "SYNTHETIC_DIAGNOSTIC":
            # Synthetic engineering replays may exercise a revised engine;
            # genuinely financial OOS cannot be consumed by a revised engine.
            key_source += ENGINE_SOURCE_HASH
        key = hashlib.sha256(key_source.encode()).hexdigest()
        immutable_record(output / "final-oos-registrations" / (key + ".json"), text)
    runner = WalkForwardRunner(dataset, diagnostic=diagnostic)
    results = []
    for fold in plan.folds:
        for partition in ("validation", "test"):
            for variant in plan.variants:
                row: dict[str, object] = {"fold": fold.name, "partition": partition, "variant": variant.name,
                                          "strategy": variant.strategy, "purpose": variant.purpose}
                try:
                    replay = runner.run(variant.policy, variant.costs, plan.risk, fold,
                                        partition=partition, strategy=variant.strategy)
                    digest = hashlib.sha256(replay.stable_json().encode()).hexdigest()
                    immutable_record(output / "replays" / (digest + ".json"), replay.stable_json() + "\n")
                    row.update({"status": "REPLAY_COMPLETE", "replay_hash": digest,
                                "metrics": performance(replay), "warnings": list(replay.warnings)})
                except ValueError as error:
                    row.update({"status": "BLOCKED", "reason": str(error), "metrics": None})
                results.append(row)
    summary = {"schema_version": "quant-experiment-summary.v1", "dataset_hash": dataset.digest,
               "engine_source_hash": ENGINE_SOURCE_HASH,
               "plan_hash": plan.digest, "evidence_status": dataset.evidence_status,
               "status": "DIAGNOSTIC_ONLY" if dataset.evidence_status == "SYNTHETIC_DIAGNOSTIC" else "EVALUATION_COMPLETE" if all(r["status"] == "REPLAY_COMPLETE" for r in results) else "INSUFFICIENT_EVIDENCE",
               "financial_alpha_demonstrated": False,
               "paper_candidate_readiness": "INSUFFICIENT_EVIDENCE" if dataset.evidence_status != "VERIFIED_PIT" else "INDEPENDENT_REVIEW_REQUIRED",
               "automatic_promotion": False, "trial_count": len(plan.variants), "evaluation_count": len(results),
               "universe_basis": dataset.universe_basis,
               "corporate_action_source": dataset.corporate_action_source,
               "coverage": {s.canonical_symbol: {"bars": len(s.bars), "first": str(min(b.session for b in s.bars)) if s.bars else None,
                                                 "last": str(max(b.session for b in s.bars)) if s.bars else None} for s in dataset.series},
               "results": results,
               "limitations": ["NO_AUTOMATIC_WINNER_SELECTION", "NO_DEFLECTED_OR_DEFLATED_SHARPE_CLAIM",
                               "PAIRED_BLOCK_INTERVALS_ARE_POINTWISE_NOT_FAMILYWISE_CORRECTED",
                               "SHOCK_OR_UNIVERSE_SENSITIVITY_IS_NOT_INDEPENDENT_OOS",
                               "NO_TRUSTED_FUNDAMENTALS_OR_SECTOR_HISTORY", "NO_HIGH_DIMENSIONAL_COVARIANCE_OPTIMIZATION"]}
    summary_text = json.dumps(summary, sort_keys=True, indent=2, allow_nan=False) + "\n"
    summary_hash = hashlib.sha256(summary_text.encode()).hexdigest()
    path = immutable_record(output / ("summary-" + summary_hash + ".json"), summary_text)
    return {**summary, "summary_path": str(path)}
