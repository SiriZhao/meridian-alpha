"""Opt-in daily shadow and a separate, non-executing paper review boundary."""

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

from meridian.config import Policies, RiskPolicy
from meridian.historical import HistoricalBarSeries
from meridian.host_account import HostAccountSnapshotEnvelope, normalize_host_snapshot
from meridian.quant.backtest import QuantSecurityMetadata, ReplayResult, pit_correlations
from meridian.quant.features import compute_features
from meridian.quant.numerics import deterministic_decimal
from meridian.quant.policy import CostPolicy, QuantPolicy
from meridian.quant.portfolio import allocate, cost_aware_target, weights
from meridian.quant.regime import RegimeState, detect_regime
from meridian.quant.signals import AlphaScoreV2, QuantFactorEngine
from meridian.quant.version import ENGINE_SOURCE_HASH
from meridian.runtime_io import atomic_write, run_lock
from meridian.schemas import (
    AccountSnapshot,
    MarketSnapshot,
    OrderDraft,
    RunStatus,
    StableModel,
    TargetPortfolio,
)
from meridian.security import SecurityMetadata

D = Decimal


class SymbolComparison(StableModel):
    symbol: str
    old_quant_score: Decimal | None
    new_quant_score: Decimal | None
    old_target_weight: Decimal
    new_target_weight: Decimal
    proposed_target_weight: Decimal
    weight_difference: Decimal
    reasons: tuple[str, ...]


class QuantShadowRecord(StableModel):
    schema_version: str = "quant-shadow-comparison.v1"
    run_id: str
    as_of: datetime
    market_snapshot_hash: str
    policy_hash: str
    engine_hash: str
    history_hashes: tuple[str, ...]
    status: Literal["SHADOW_COMPUTED", "INSUFFICIENT_DATA", "SHADOW_BLOCKED"]
    symbols: tuple[SymbolComparison, ...]
    scores: tuple[AlphaScoreV2, ...]
    regime: RegimeState
    expected_turnover: Decimal
    estimated_cost_fraction: Decimal
    risk_violations: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    canonical_orders_changed: Literal[False] = False
    paper_ledger_changed: Literal[False] = False
    automatic_promotion: Literal[False] = False
    broker_submission: Literal["DISABLED"] = "DISABLED"

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


@deterministic_decimal
def build_quant_targets(histories: Mapping[str, HistoricalBarSeries], cutoff: datetime,
                        policies: Policies, policy: QuantPolicy, *, diagnostic: bool = False):
    if any(symbol != series.canonical_symbol for symbol, series in histories.items()):
        raise ValueError("QUANT_HISTORY_SYMBOL_MISMATCH")
    benchmark = histories.get("SPY")
    features = {s: compute_features(h, cutoff, benchmark=benchmark, diagnostic=diagnostic)
                for s, h in sorted(histories.items()) if s in policies.universe.tickers or s == "SPY"}
    state = detect_regime(features.get("SPY"), policy)
    scores = QuantFactorEngine().score([f for s, f in features.items() if s in policies.universe.tickers], policy, state)
    correlations = pit_correlations(histories, cutoff, policy.correlation_lookback) if policy.correlation_limit is not None else None
    target = allocate(scores, features, cutoff, policies.risk, policy, state, correlations=correlations)
    return features, state, scores, target


@deterministic_decimal
def observe_shadow(*, run_id: str, cutoff: datetime, market_hash: str,
                   account: AccountSnapshot, quotes: Mapping[str, MarketSnapshot],
                   baseline_target: TargetPortfolio | None,
                   histories: Mapping[str, HistoricalBarSeries], policies: Policies,
                   policy: QuantPolicy, metadata: dict[str, SecurityMetadata] | None = None,
                   diagnostic: bool = False) -> QuantShadowRecord:
    from meridian.risk import RiskEngine

    features, state, scores, target = build_quant_targets(histories, cutoff, policies, policy, diagnostic=diagnostic)
    current = {h.ticker: h.market_value / account.total_equity for h in account.holdings} if account.total_equity else {}
    risk = RiskEngine().approve(target, account, "NORMAL", policies.risk, metadata=metadata)
    if account.total_equity > 0:
        rebalance = cost_aware_target(risk.approved, current, nav=account.total_equity,
                                     risk=policies.risk, policy=policy, costs=CostPolicy(),
                                     dollar_volumes={s: f.value("dollar_volume_20") for s, f in features.items()})
        new = weights(rebalance.target)
        turnover, cost_fraction = rebalance.expected_turnover, rebalance.estimated_cost / account.total_equity
    else:
        new, turnover, cost_fraction = {}, D(0), D(0)
    old = weights(baseline_target) if baseline_target else {}
    proposed = weights(target)
    scored = {s.symbol: s for s in scores}
    rows = tuple(SymbolComparison(symbol=s, old_quant_score=max(D(0), quotes[s].daily_return) if s in quotes else None,
                                  new_quant_score=scored[s].quant_score if s in scored else None,
                                  old_target_weight=old.get(s, D(0)), new_target_weight=new.get(s, D(0)),
                                  proposed_target_weight=proposed.get(s, D(0)),
                                  weight_difference=new.get(s, D(0)) - old.get(s, D(0)),
                                  reasons=scored[s].exclusion_reasons + scored[s].risk_adjustments if s in scored else ("HISTORY_UNAVAILABLE",))
                 for s in sorted(set(policies.universe.tickers) | set(current)))
    coverage = all(s in features and features[s].quality_status != "REJECTED" for s in policies.universe.tickers)
    if coverage and any(s.quant_score > 0 for s in scores):
        status = "SHADOW_COMPUTED"
    elif not coverage or state.trend == "INSUFFICIENT_DATA":
        status = "INSUFFICIENT_DATA"
    else:
        status = "SHADOW_COMPUTED"
    return QuantShadowRecord(run_id=run_id, as_of=cutoff, market_snapshot_hash=market_hash,
                             engine_hash=ENGINE_SOURCE_HASH,
                             policy_hash=hashlib.sha256(policy.stable_json().encode()).hexdigest(),
                             history_hashes=tuple(features[s].input_hash for s in sorted(features)),
                             status=status, symbols=rows, scores=scores, regime=state,
                             expected_turnover=turnover, estimated_cost_fraction=cost_fraction,
                             risk_violations=risk.violations,
                             reasons=("RAW_ACCOUNT_NOT_PERSISTED", "PREDICTIVE_CONFIDENCE_UNCALIBRATED", "EXISTING_RISK_GATES_APPLIED"))


def immutable_record(path: Path, content: str) -> Path:
    """Writers cooperate through the existing lock; existing content is sealed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with run_lock(path.parent / ".locks", "quant-immutable", name="quant-record"):
        if path.exists():
            if path.read_text(encoding="utf-8") != content:
                raise ValueError("QUANT_IMMUTABLE_RECORD_CONFLICT")
            return path
        atomic_write(path, content)
    return path


def persist_shadow(record: QuantShadowRecord, directory: Path) -> Path:
    return immutable_record(directory / (record.digest + ".json"), record.stable_json() + "\n")


class PaperCandidateReview(StableModel):
    status: Literal["INSUFFICIENT_EVIDENCE", "READY_FOR_PAPER_REVIEW", "PAPER_CANDIDATE_BLOCKED"]
    target: TargetPortfolio | None = None
    orders: tuple[OrderDraft, ...] = ()
    reasons: tuple[str, ...]
    authority: Literal["PAPER_REVIEW_ONLY_NOT_FOR_REAL_ENTRY"] = "PAPER_REVIEW_ONLY_NOT_FOR_REAL_ENTRY"
    canonical_strategy_changed: Literal[False] = False
    ledger_changed: Literal[False] = False
    broker_submission: Literal["DISABLED"] = "DISABLED"


def sufficient_engineering_evidence(records: tuple[ReplayResult, ...], policy: QuantPolicy, risk: RiskPolicy) -> bool:
    # Readiness means an adequate evaluation exists, not that it made money.
    # Synthetic replays and duplicated/overlapping portfolio days never count.
    if len(records) < policy.minimum_oos_folds or any(r.evidence_status != "VERIFIED_PIT" or r.partition != "test"
                              or r.strategy != policy.strategy or not r.days for r in records):
        return False
    dates = [d.session for r in records for d in r.days]
    if len(dates) < policy.minimum_oos_sessions or len(set(dates)) != len(dates):
        return False
    if len({r.fold for r in records}) != len(records):
        return False
    if len({r.dataset_hash for r in records}) != 1:
        return False
    # Bind the full policy excluding only the administrative switch/approval.
    accepted = policy.model_copy(update={"mode": "QUANT_V1_BASELINE", "paper_approved": False, "approval_reference": None})
    digest = hashlib.sha256(accepted.stable_json().encode()).hexdigest()
    cost_hash = hashlib.sha256(CostPolicy().stable_json().encode()).hexdigest()
    risk_hash = hashlib.sha256(risk.model_dump_json().encode()).hexdigest()
    return all(r.policy_hash == digest and r.cost_hash == cost_hash and r.risk_hash == risk_hash
               and r.engine_hash == ENGINE_SOURCE_HASH for r in records)


@deterministic_decimal
def plan_paper_candidate(envelope: HostAccountSnapshotEnvelope, quotes: dict[str, MarketSnapshot],
                         histories: Mapping[str, HistoricalBarSeries], cutoff: datetime,
                         policies: Policies, policy: QuantPolicy, *,
                         records: tuple[ReplayResult, ...] = (),
                         pit_metadata: tuple[QuantSecurityMetadata, ...] = ()) -> PaperCandidateReview:
    from meridian.daily_closure import DailyClosureService
    from meridian.orders import OrderPlanner, ProjectedPortfolioValidator
    from meridian.reconciliation import ReconciliationEngine
    from meridian.risk import RiskEngine

    if policy.mode != "QUANT_V2_PAPER_CANDIDATE" or not policy.paper_approved or not policy.approval_reference:
        return PaperCandidateReview(status="PAPER_CANDIDATE_BLOCKED", reasons=("EXPLICIT_PAPER_APPROVAL_REQUIRED",))
    if envelope.source_kind != "PAPER_LEDGER" or envelope.source_name != "Schwab-Paper":
        return PaperCandidateReview(status="PAPER_CANDIDATE_BLOCKED", reasons=("SANITIZED_PAPER_LEDGER_SNAPSHOT_REQUIRED",))
    if not sufficient_engineering_evidence(records, policy, policies.risk):
        return PaperCandidateReview(status="INSUFFICIENT_EVIDENCE", reasons=("VERIFIED_NONOVERLAPPING_OOS_EVALUATION_REQUIRED",))
    account = normalize_host_snapshot(envelope)
    blockers = DailyClosureService(policies)._gates(account, quotes, cutoff)
    if blockers:
        return PaperCandidateReview(status="PAPER_CANDIDATE_BLOCKED", reasons=blockers)
    features, state, scores, target = build_quant_targets(histories, cutoff, policies, policy)
    if any(f.synthetic or f.quality_status == "REJECTED" for f in features.values()) or not scores or any(s not in features for s in policies.universe.tickers):
        return PaperCandidateReview(status="PAPER_CANDIDATE_BLOCKED", reasons=("CERTIFIED_FEATURES_REQUIRED",))
    from meridian.security import AssetType
    if any(m.known_at > cutoff for m in pit_metadata):
        return PaperCandidateReview(status="PAPER_CANDIDATE_BLOCKED", reasons=("FUTURE_SECURITY_METADATA",))
    if len({m.symbol for m in pit_metadata}) != len(pit_metadata):
        return PaperCandidateReview(status="PAPER_CANDIDATE_BLOCKED", reasons=("DUPLICATE_SECURITY_METADATA",))
    metadata = {m.symbol: SecurityMetadata(m.symbol, AssetType(m.asset_type), m.sector, None) for m in pit_metadata}
    required = {h.ticker for h in account.holdings} | {p.ticker for p in target.positions}
    if policies.risk.max_sector_weight < 1 and required - metadata.keys():
        return PaperCandidateReview(status="PAPER_CANDIDATE_BLOCKED", reasons=("HELD_AND_TARGET_SECURITY_METADATA_REQUIRED",))
    risk_report = RiskEngine().approve(target, account, "NORMAL", policies.risk, metadata=metadata)
    if risk_report.violations:
        return PaperCandidateReview(status="PAPER_CANDIDATE_BLOCKED", reasons=risk_report.violations)
    current = {h.ticker: h.market_value / account.total_equity for h in account.holdings}
    decision = cost_aware_target(risk_report.approved, current, nav=account.total_equity,
                                 risk=policies.risk, policy=policy, costs=CostPolicy(),
                                 dollar_volumes={s: f.value("dollar_volume_20") for s, f in features.items()})
    if decision.action == "BLOCKED":
        return PaperCandidateReview(status="PAPER_CANDIDATE_BLOCKED", reasons=decision.reasons)
    reconciliation = ReconciliationEngine().reconcile(account, decision.target)
    orders = OrderPlanner().plan(account, reconciliation, quotes, policies.execution, policies.risk, account.total_equity)
    projection = ProjectedPortfolioValidator().validate(account, orders, account.total_equity,
                                                        policies.risk.min_cash_weight, policies.risk.max_position_weight,
                                                        policies.risk.max_number_positions,
                                                        sector_map={s: m.sector for s, m in metadata.items() if m.sector},
                                                        max_sector_weight=policies.risk.max_sector_weight)
    if projection.violations:
        return PaperCandidateReview(status="PAPER_CANDIDATE_BLOCKED", reasons=projection.violations)
    return PaperCandidateReview(status="READY_FOR_PAPER_REVIEW", target=decision.target,
                                orders=orders, reasons=("HUMAN_APPROVAL_RECORDED", "CANONICAL_SWITCH_NOT_PERFORMED", RunStatus.DRAFT.value if orders else RunStatus.NO_ACTION.value))


def rejection_payload(error: Exception) -> dict[str, object]:
    # Do not persist exception text that might include caller-supplied account
    # or filesystem data. Structured reason type is adequate for isolation.
    return {"status": "SHADOW_BLOCKED", "authority": "SHADOW_ONLY", "reason": type(error).__name__,
            "canonical_orders_changed": False, "paper_ledger_changed": False}


def shadow_payload(record: QuantShadowRecord) -> dict[str, object]:
    return json.loads(record.stable_json())
