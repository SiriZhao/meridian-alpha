"""Constrained long-only target construction and explicit friction decisions."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

from meridian.config import RiskPolicy
from meridian.quant.features import FeatureSnapshot
from meridian.quant.numerics import deterministic_decimal
from meridian.quant.policy import CostPolicy, QuantPolicy
from meridian.quant.regime import RegimeState
from meridian.quant.signals import AlphaScoreV2
from meridian.schemas import StableModel, TargetPortfolio, TargetPosition

D = Decimal


def correlation_key(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left < right else (right, left)


def weights(target: TargetPortfolio) -> dict[str, Decimal]:
    return {p.ticker: p.target_weight for p in target.positions}


@deterministic_decimal
def gross_turnover(current: Mapping[str, Decimal], proposed: Mapping[str, Decimal]) -> Decimal:
    return sum((abs(proposed.get(s, D(0)) - current.get(s, D(0))) for s in sorted(current.keys() | proposed.keys())), D(0))


@deterministic_decimal
def validate_weights(values: Mapping[str, Decimal], risk: RiskPolicy) -> bool:
    return (len([v for v in values.values() if v > 0]) <= risk.max_number_positions
            and all(v.is_finite() and 0 <= v <= risk.max_position_weight for v in values.values())
            and sum((values[s] for s in sorted(values)), D(0)) <= 1 - risk.min_cash_weight)


@deterministic_decimal
def target_from_weights(values: Mapping[str, Decimal], cutoff: datetime, version: str) -> TargetPortfolio:
    if any(not v.is_finite() or v < 0 for v in values.values()):
        raise ValueError("QUANT_INVALID_TARGET_WEIGHT")
    values = {s: values[s].quantize(D("0.000001"), rounding=ROUND_DOWN) for s in sorted(values)}
    invested = sum(values.values(), D(0))
    return TargetPortfolio(as_of=cutoff, cash_weight=1 - invested,
                           positions=tuple(TargetPosition(ticker=s, target_weight=v, conviction=D(0),
                                                          rationale="Deterministic Quant V2 research target; predictive confidence uncalibrated.")
                                           for s, v in sorted(values.items()) if v > 0),
                           allocator_name="quant_v2_constrained", allocator_version=version)


@deterministic_decimal
def allocate(scores: Sequence[AlphaScoreV2], features: Mapping[str, FeatureSnapshot],
             cutoff: datetime, risk: RiskPolicy, policy: QuantPolicy, regime: RegimeState,
             *, correlations: Mapping[tuple[str, str], Decimal] | None = None) -> TargetPortfolio:
    if any(s.as_of != cutoff or features[s.symbol].as_of != cutoff for s in scores):
        raise ValueError("QUANT_ALLOCATION_CUTOFF_MISMATCH")
    if regime.as_of is not None and regime.as_of != cutoff:
        raise ValueError("QUANT_REGIME_CUTOFF_MISMATCH")
    selected: list[AlphaScoreV2] = []
    for score in sorted(scores, key=lambda s: (-s.quant_score, s.symbol)):
        if score.quant_score <= 0 or score.exclusion_reasons:
            continue
        if policy.correlation_limit is not None:
            # Unknown correlation fails closed for adding a second holding.
            if any((correlations or {}).get(correlation_key(score.symbol, p.symbol)) is None
                   or abs((correlations or {})[correlation_key(score.symbol, p.symbol)]) > policy.correlation_limit
                   for p in selected):
                continue
        selected.append(score)
        if len(selected) == risk.max_number_positions:
            break
    budget = 1 - risk.min_cash_weight
    if policy.strategy == "A4":
        budget = min(budget, regime.exposure_ceiling)
    raw = {}
    for score in selected:
        vol = features[score.symbol].value("volatility_60")
        if policy.allocation != "score" and vol is None:
            continue
        raw[score.symbol] = score.quant_score if policy.allocation == "score" else (
            D(1) if policy.allocation == "inverse_volatility" else score.quant_score) / max(vol or D(0), policy.volatility_floor)
    # Water-fill cap overflow across remaining eligible symbols; leave excess
    # cash when the universe cannot absorb the budget within position caps.
    result: dict[str, Decimal] = {}
    remaining = dict(raw)
    while remaining and budget > 0:
        total = sum(remaining.values(), D(0))
        capped = {s for s, v in remaining.items() if budget * v / total >= risk.max_position_weight}
        if not capped:
            result.update({s: (budget * v / total).quantize(D("0.000001"), rounding=ROUND_DOWN) for s, v in remaining.items()})
            break
        for symbol in sorted(capped):
            result[symbol] = risk.max_position_weight
            budget -= risk.max_position_weight
            del remaining[symbol]
    if policy.strategy in {"A3", "A4"} and policy.use_volatility_adjustment and result:
        # Correlation=+1 gives a conservative upper bound on ex-ante portfolio
        # volatility. It requires no estimated high-dimensional covariance.
        upper_bound = sum((v * max(features[s].value("volatility_60") or D(0), policy.volatility_floor)
                           for s, v in result.items()), D(0))
        if upper_bound > policy.target_volatility:
            scale = policy.target_volatility / upper_bound
            result = {s: (v * scale).quantize(D("0.000001"), rounding=ROUND_DOWN) for s, v in result.items()}
    if not validate_weights(result, risk):
        raise ValueError("QUANT_OPTIMIZER_INFEASIBLE")
    return target_from_weights(result, cutoff, policy.version)


class RebalanceDecision(StableModel):
    target: TargetPortfolio
    action: str
    expected_turnover: Decimal
    estimated_cost: Decimal
    expected_benefit: Decimal | None
    reasons: tuple[str, ...]


@deterministic_decimal
def cost_aware_target(target: TargetPortfolio, current: Mapping[str, Decimal], *, nav: Decimal,
                      risk: RiskPolicy, policy: QuantPolicy, costs: CostPolicy,
                      sessions_since_rebalance: int = 5,
                      expected_improvement: Decimal | None = None,
                      dollar_volumes: Mapping[str, Decimal | None] | None = None) -> RebalanceDecision:
    if not nav.is_finite() or nav <= 0 or any(not v.is_finite() or v < 0 for v in current.values()):
        raise ValueError("QUANT_INVALID_PORTFOLIO_INPUT")
    if expected_improvement is not None and not expected_improvement.is_finite():
        raise ValueError("QUANT_INVALID_BENEFIT_ESTIMATE")
    desired = weights(target)
    safe = validate_weights(current, risk)
    reasons = []
    # Eligibility exits and regime exposure reductions take priority over a
    # calendar/band. They still pass the existing RiskEngine and OrderPlanner.
    risk_reduction = not safe or any(current.get(s, D(0)) > v and (v == 0 or sum(desired.values(), D(0)) < sum((current[s] for s in sorted(current)), D(0)))
                                     for s, v in {s: desired.get(s, D(0)) for s in current}.items())
    if policy.use_cost_gate and safe and not risk_reduction:
        if policy.rebalance == "weekly" and sessions_since_rebalance < 5:
            reasons.append("WEEKLY_NOT_DUE")
        if policy.rebalance == "threshold" and gross_turnover(current, desired) < policy.rebalance_threshold:
            reasons.append("BELOW_REBALANCE_THRESHOLD")
        for symbol in sorted(current.keys() | desired.keys()):
            delta = desired.get(symbol, D(0)) - current.get(symbol, D(0))
            if abs(delta) < policy.no_trade_band or abs(delta) * nav < policy.minimum_trade_notional:
                desired[symbol] = current.get(symbol, D(0))
        if not validate_weights(desired, risk):
            reasons.append("NO_TRADE_BAND_CONSTRAINT_CONFLICT")
    turnover = gross_turnover(current, desired)
    limit = min(policy.max_turnover, risk.max_daily_turnover)
    if turnover > limit and safe:
        scale = limit / turnover
        scaled = {s: (current.get(s, D(0)) + scale * (desired.get(s, D(0)) - current.get(s, D(0)))).quantize(D("0.000001"), rounding=ROUND_DOWN)
                  for s in sorted(current.keys() | desired.keys())}
        if validate_weights(scaled, risk):
            desired = scaled
        else:
            return RebalanceDecision(target=target, action="BLOCKED", expected_turnover=turnover,
                                     estimated_cost=costs.estimate(nav * turnover, len(desired)),
                                     expected_benefit=None, reasons=("TURNOVER_CONSTRAINT_INFEASIBLE_HOLD_FOR_REVIEW",))
    elif turnover > limit:
        return RebalanceDecision(target=target, action="BLOCKED", expected_turnover=turnover,
                                 estimated_cost=costs.estimate(nav * turnover, len(desired)),
                                 expected_benefit=None, reasons=("RISK_REDUCTION_EXCEEDS_TURNOVER_REVIEW_REQUIRED",))
    if dollar_volumes is not None:
        for symbol in sorted(current.keys() | desired.keys()):
            amount = abs(desired.get(symbol, D(0)) - current.get(symbol, D(0))) * nav
            volume = dollar_volumes.get(symbol)
            if amount > 0 and (volume is None or amount > volume * policy.max_volume_participation):
                reasons.append("LIQUIDITY_TURNOVER_NOT_FEASIBLE:" + symbol)
    count = sum(desired.get(s, D(0)) != current.get(s, D(0)) for s in current.keys() | desired.keys())
    turnover = gross_turnover(current, desired)
    estimated = costs.estimate(nav * turnover, count)
    benefit = expected_improvement * nav if expected_improvement is not None else None
    if policy.use_cost_gate and safe and not risk_reduction and benefit is not None and benefit <= estimated * policy.minimum_benefit_cost_ratio:
        reasons.append("EXPECTED_BENEFIT_BELOW_COST")
    if reasons and safe and not risk_reduction:
        desired = dict(current)
        turnover, estimated = D(0), D(0)
    elif any(r.startswith("LIQUIDITY_") for r in reasons):
        # A forced risk exit with no executable liquidity needs human review;
        # retain a constrained target but no authorization to trade.
        return RebalanceDecision(target=target, action="BLOCKED", expected_turnover=turnover,
                                 estimated_cost=estimated, expected_benefit=benefit, reasons=tuple(reasons))
    if not validate_weights(desired, risk):
        raise ValueError("QUANT_REBALANCE_INFEASIBLE")
    if benefit is None:
        reasons.append("EXPECTED_RETURN_UNCALIBRATED_COSTS_REPORTED_ONLY")
    return RebalanceDecision(target=target_from_weights(desired, target.as_of, policy.version),
                             action="REBALANCE" if turnover > 0 else "NO_ACTION",
                             expected_turnover=turnover, estimated_cost=estimated, expected_benefit=benefit,
                             reasons=tuple(reasons))
