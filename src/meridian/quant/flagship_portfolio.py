"""Bounded shadow portfolio construction on the existing V2.2 signal.

The objective trades ordinal portfolio preferences against variance/turnover.
It is NOT a net expected-return objective: no calibrated forecast is supplied.
All numerical safety ceilings precede the objective, with cash as an asset.
"""
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Literal

from meridian.config import RiskPolicy
from meridian.quant.features import ChallengerFeatureSnapshot, FeatureSnapshot
from meridian.quant.flagship_policy import FlagshipPolicy
from meridian.quant.numerics import deterministic_decimal
from meridian.quant.policy import CostPolicy
from meridian.quant.portfolio import (
    ChallengerAllocation,
    allocate_challenger,
    correlation_key,
    estimate_portfolio_risk,
    target_from_weights,
    validate_weights,
    weights,
)
from meridian.quant.regime import RegimeState
from meridian.quant.signals import ChallengerScore
from meridian.schemas import StableModel

D = Decimal
DEFAULT_NAV = D('100000')


class FlagshipAllocation(StableModel):
    version: Literal["quant-allocation-v2.3"] = "quant-allocation-v2.3"
    authority: Literal["SHADOW_ONLY"] = "SHADOW_ONLY"
    allocation: ChallengerAllocation
    policy_hash: str
    objective_before: Decimal | None
    objective_after: Decimal | None
    evaluated_candidates: int
    expected_return: None = None
    reasons: tuple[str, ...]
    factor_model: Literal["FROZEN_V22_SIX_FACTOR_SIGNAL"] = "FROZEN_V22_SIX_FACTOR_SIGNAL"


@deterministic_decimal
def construct_flagship(
    scores: Sequence[ChallengerScore], features: Mapping[str, FeatureSnapshot],
    cutoff: datetime, risk: RiskPolicy, policy: FlagshipPolicy, regime: RegimeState,
    *, current: Mapping[str, Decimal], correlations: Mapping[tuple[str, str], Decimal],
    sector_map: Mapping[str, str | None], asset_types: Mapping[str, str],
    extended: Mapping[str, ChallengerFeatureSnapshot] | None = None,
    costs: CostPolicy | None = None, nav: Decimal = DEFAULT_NAV,
    diagnostic: bool = False,
) -> FlagshipAllocation:
    policy = FlagshipPolicy.model_validate(policy.model_dump())
    risk = RiskPolicy.model_validate(risk.model_dump())
    if not risk.long_only or risk.allow_leverage:
        raise ValueError('V23_LONG_ONLY_UNLEVERED_REQUIRED')
    if any(not value.is_finite() or not -1 <= value <= 1 or left >= right
            for (left, right), value in correlations.items()):
        raise ValueError('V23_INVALID_CORRELATION_MATRIX_INPUT')
    costs = CostPolicy.model_validate((costs or CostPolicy()).model_dump())
    if not nav.is_finite() or nav <= 0 or any(not v.is_finite() for v in (costs.commission_per_order, costs.slippage_bps)) or (costs.spread_bps is not None and not costs.spread_bps.is_finite()):
        raise ValueError('V23_INVALID_NAV_OR_COSTS')
    if cutoff.tzinfo is None or regime.as_of != cutoff:
        raise ValueError("V23_SHARED_CUTOFF_REQUIRED")
    if any(not v.is_finite() or v < 0 for v in current.values()) or sum(current.values(), D(0)) > 1:
        raise ValueError("V23_INVALID_CURRENT_WEIGHTS")
    if len(scores) > policy.maximum_symbols or len({s.bridge.symbol for s in scores}) != len(scores):
        raise ValueError("V23_SYMBOL_LIMIT_OR_DUPLICATE")
    if any(s.bridge.as_of != cutoff or s.bridge.symbol not in features or any(
        f.as_of != cutoff or f.availability_cutoff > cutoff or f.symbol != s.bridge.symbol for f in s.factor_attribution
    ) for s in scores):
        raise ValueError("V23_SCORE_IDENTITY_OR_FUTURE_INFORMATION")
    if extended and any(s not in features or f.base != features[s] or f.availability_cutoff > cutoff for s, f in extended.items()):
        raise ValueError("V23_EXTENDED_FEATURE_IDENTITY_OR_FUTURE_INFORMATION")
    for symbol, feature in features.items():
        if any(f.raw_value is not None and not f.raw_value.is_finite() for f in feature.factors):
            raise ValueError('V23_NONFINITE_FACTOR_INPUT')
        if feature.symbol != symbol or feature.as_of != cutoff or any(
            f.as_of != cutoff or f.symbol != symbol or f.availability_cutoff > cutoff for f in feature.factors
        ):
            raise ValueError("V23_FEATURE_IDENTITY_OR_FUTURE_INFORMATION")
    base = allocate_challenger(scores, features, cutoff, risk, policy.baseline, regime,
        correlations=correlations, sector_map=sector_map, asset_types=asset_types, diagnostic=diagnostic)
    anchor = weights(base.feasible_target)
    symbols = sorted(s for s, value in anchor.items() if value > 0)
    reasons = ["EXPECTED_RETURN_UNCALIBRATED", "OBJECTIVE_IS_PREFERENCE_RISK_TURNOVER_NOT_EXPECTED_PROFIT",
               "SPREAD_AND_ETF_LOOKTHROUGH_UNKNOWN", "HARD_V22_RISK_CEILINGS_PRESERVED"]
    if policy.construction in {"V22_BASELINE", "INVERSE_VOLATILITY"} or not symbols:
        return FlagshipAllocation(allocation=base, policy_hash=policy.digest, objective_before=None,
            objective_after=None, evaluated_candidates=0, reasons=tuple(reasons + ["V22_ALREADY_USES_SINGLE_INVERSE_VOLATILITY_STEP"]))
    estimated = estimate_portfolio_risk(anchor, features, correlations, policy.baseline)
    if estimated.shrunk_volatility_estimate is None:
        return FlagshipAllocation(allocation=base, policy_hash=policy.digest, objective_before=None,
            objective_after=None, evaluated_candidates=0, reasons=tuple(reasons + ["COVARIANCE_UNKNOWN_USE_CONSERVATIVE_V22_FALLBACK"]))
    vol = {s: max(features[s].value("volatility_60") or D(0), policy.baseline.controls.volatility_floor) for s in symbols}
    covariance = {(a, b): vol[a] * vol[b] * (D(1) if a == b else
        (1 - policy.baseline.covariance_diagonal_shrinkage) * correlations[correlation_key(a, b)]) for a in symbols for b in symbols}
    budgets = {s: anchor[s] / sum(anchor.values(), D(0)) for s in symbols}
    maximum_exposure = min(1 - risk.min_cash_weight, regime.exposure_ceiling)
    if policy.baseline.diagnostic_exposure is not None:
        maximum_exposure = min(maximum_exposure, policy.baseline.diagnostic_exposure)
    conditional = policy.construction == "REGIME_CONDITIONED"
    if conditional:
        for s in symbols:
            if features[s].value("beta_60") is None or features[s].value("downside_deviation") is None:
                return FlagshipAllocation(allocation=base.model_copy(update={"feasible_target": target_from_weights({}, cutoff, policy.version), "risk": estimate_portfolio_risk({}, features, correlations, policy.baseline)}),
                    policy_hash=policy.digest, objective_before=None, objective_after=None, evaluated_candidates=0,
                    reasons=tuple(reasons + ["CONDITIONAL_BETA_OR_DOWNSIDE_UNKNOWN_CASH_ONLY_TARGET"]))
            if extended is None or s not in extended or extended[s].trend_instability is None:
                return FlagshipAllocation(allocation=base.model_copy(update={"feasible_target": target_from_weights({}, cutoff, policy.version), "risk": estimate_portfolio_risk({}, features, correlations, policy.baseline)}),
                    policy_hash=policy.digest, objective_before=None, objective_after=None, evaluated_candidates=0,
                    reasons=tuple(reasons + ["CONDITIONAL_INSTABILITY_UNKNOWN_CASH_ONLY_TARGET"]))
    def feasible(w: Mapping[str, Decimal]) -> bool:
        if not validate_weights(w, risk) or sum(w.values(), D(0)) > maximum_exposure:
            return False
        if sum((w[s] * vol[s] for s in symbols), D(0)) > policy.baseline.controls.target_volatility:
            return False
        for component in estimated.correlated_components:
            if len(component) > 1 and sum((w.get(s, D(0)) for s in component), D(0)) > policy.baseline.cluster_weight_cap:
                return False
        for sector in {x for x in sector_map.values() if x}:
            if sum((w[s] for s in symbols if sector_map.get(s) == sector), D(0)) > risk.max_sector_weight:
                return False
        if conditional:
            if sum((w[s] * abs(features[s].value("beta_60") or D(0)) for s in symbols), D(0)) > policy.beta_budget:
                return False
            if sum((w[s] * (features[s].value("downside_deviation") or D(0)) for s in symbols), D(0)) > policy.downside_budget:
                return False
            if extended and any(w[s] > 0 and (extended[s].trend_instability or D(0)) > policy.instability_ceiling for s in symbols):
                return False
        return True
    def objective(w: Mapping[str, Decimal]) -> Decimal:
        marginal = {a: sum((covariance[a, b] * w[b] for b in symbols), D(0)) for a in symbols}
        variance = sum((w[s] * marginal[s] for s in symbols), D(0))
        tracking = sum(((w[s] - anchor[s]) ** 2 for s in symbols), D(0))
        if policy.construction == "SHRUNK_RISK_BUDGET":
            contribution_error = sum(((w[s] * marginal[s] / variance - budgets[s]) ** 2 for s in symbols), D(0)) if variance > 0 else D(1)
            return contribution_error + tracking + (sum(w.values(), D(0)) - sum(anchor.values(), D(0))) ** 2
        turnover = sum((abs(w.get(s, D(0)) - current.get(s, D(0))) for s in sorted(set(symbols) | set(current))), D(0))
        order_count = sum(abs(w.get(s, D(0)) - current.get(s, D(0))) >= D('.000001') for s in sorted(set(symbols) | set(current)))
        assumed_cost_fraction = costs.estimate(turnover * nav, order_count) / nav
        return (policy.preference_weight * tracking + policy.risk_weight * variance / policy.baseline.controls.target_volatility ** 2
            + policy.turnover_weight * turnover + policy.cost_weight * assumed_cost_fraction)
    start = dict(anchor)
    if not feasible(start):
        # Only remove exposure to satisfy the additional, stricter conditional budget.
        for _ in range(64):
            start = {s: v * D('.9') for s, v in start.items()}
            if conditional and extended:
                start = {s: v if (extended[s].trend_instability or D(0)) <= policy.instability_ceiling else D(0) for s, v in start.items()}
            if feasible(start):
                break
        if not feasible(start):
            start = dict.fromkeys(symbols, D(0))
        reasons.append("CONDITIONAL_BUDGET_REDUCTION_BEFORE_OPTIMIZATION")
    before = objective(start)
    chosen, best, evaluations = start, before, 0
    # Deterministic coordinate moves between each security and cash; reject
    # infeasible proposals before evaluating the objective. Lexical ties stay put.
    for step in policy.step_sizes:
        for _ in range(policy.sweeps_per_step):
            improved = False
            for s in symbols:
                for direction in (-1, 1):
                    candidate = dict(chosen)
                    candidate[s] += direction * step
                    evaluations += 1
                    if not feasible(candidate):
                        continue
                    value = objective(candidate)
                    if value < best - D('1e-18'):
                        chosen, best, improved = candidate, value, True
            if not improved:
                break
    target = target_from_weights(chosen, cutoff, policy.version)
    actual = weights(target)
    actual = {s: actual.get(s, D(0)) for s in symbols}
    if not feasible(actual):
        raise ValueError("V23_ROUNDED_TARGET_INFEASIBLE")
    final = base.model_copy(update={"feasible_target": target,
        "risk": estimate_portfolio_risk(actual, features, correlations, policy.baseline),
        "modifications": base.modifications + ("V23_BOUNDED_" + policy.construction,)})
    return FlagshipAllocation(allocation=final, policy_hash=policy.digest, objective_before=before,
        objective_after=objective(actual), evaluated_candidates=evaluations,
        reasons=tuple(reasons + ["BOUNDED_LOCAL_SEARCH_NO_GLOBAL_OPTIMALITY_CLAIM"]))
