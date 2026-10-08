"""Constrained long-only target construction and explicit friction decisions."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

from meridian.config import RiskPolicy
from meridian.quant.features import FeatureSnapshot
from meridian.quant.numerics import deterministic_decimal
from meridian.quant.policy import CostPolicy, QuantPolicy
from meridian.quant.regime import RegimeState
from meridian.quant.signals import AlphaScoreV2
from meridian.schemas import StableModel, TargetPortfolio, TargetPosition

D = Decimal

if TYPE_CHECKING:
    from meridian.quant.contracts import ExpectedReturnEstimate
    from meridian.quant.policy import ChallengerPolicy
    from meridian.quant.signals import ChallengerScore


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


class PortfolioRiskEstimate(StableModel):
    conservative_volatility_bound: Decimal
    shrunk_volatility_estimate: Decimal | None
    covariance_status: str
    correlated_components: tuple[tuple[str, ...], ...]
    assumptions: tuple[str, ...]


class ChallengerAllocation(StableModel):
    preferred_target: TargetPortfolio
    feasible_target: TargetPortfolio
    risk: PortfolioRiskEstimate
    modifications: tuple[str, ...]


def _positive_semidefinite(matrix: list[list[Decimal]]) -> bool:
    # LDL' without a numerical optimizer. Zero pivots require zero residuals.
    n = len(matrix)
    lower = [[D(0)] * n for _ in range(n)]
    diagonal = [D(0)] * n
    tolerance = D("1e-20")
    for i in range(n):
        diagonal[i] = matrix[i][i] - sum((lower[i][k] ** 2 * diagonal[k] for k in range(i)), D(0))
        if diagonal[i] < -tolerance:
            return False
        diagonal[i] = max(D(0), diagonal[i])
        lower[i][i] = D(1)
        for j in range(i + 1, n):
            residual = matrix[j][i] - sum((lower[j][k] * lower[i][k] * diagonal[k] for k in range(i)), D(0))
            if diagonal[i] <= tolerance:
                if abs(residual) > tolerance:
                    return False
            else:
                lower[j][i] = residual / diagonal[i]
    return True


@deterministic_decimal
def estimate_portfolio_risk(values: Mapping[str, Decimal], features: Mapping[str, FeatureSnapshot],
                            correlations: Mapping[tuple[str, str], Decimal], policy: "ChallengerPolicy") -> PortfolioRiskEstimate:
    if any(not v.is_finite() or v < 0 for v in values.values()) or sum(values.values(), D(0)) > 1:
        raise ValueError("CHALLENGER_INVALID_RISK_WEIGHTS")
    symbols = sorted(s for s, v in values.items() if v > 0)
    for (a, b), value in correlations.items():
        if a >= b or not value.is_finite() or abs(value) > 1:
            raise ValueError("CHALLENGER_INVALID_CORRELATION_INPUT")
    vol = {s: features[s].value("volatility_60") for s in symbols}
    if any(v is None or v < 0 for v in vol.values()):
        raise ValueError("CHALLENGER_RISK_VOLATILITY_UNKNOWN")
    bounded_vol = {s: max(vol[s] or D(0), policy.controls.volatility_floor) for s in symbols}
    bound = sum((values[s] * bounded_vol[s] for s in symbols), D(0))
    missing = any(correlation_key(a, b) not in correlations for i, a in enumerate(symbols) for b in symbols[i + 1:])
    matrix = [[D(1) if a == b else correlations.get(correlation_key(a, b), D(1)) for b in symbols] for a in symbols]
    valid = not missing and _positive_semidefinite(matrix)
    estimate = None
    if valid:
        variance = sum((values[a] * values[b] * bounded_vol[a] * bounded_vol[b] *
                        (D(1) if a == b else (1 - policy.covariance_diagonal_shrinkage) * matrix[i][j])
                        for i, a in enumerate(symbols) for j, b in enumerate(symbols)), D(0))
        estimate = max(D(0), variance).sqrt()
    unseen = set(symbols)
    components = []
    while unseen:
        component = {min(unseen)}
        frontier = set(component)
        while frontier:
            additions = {b for a in frontier for b in unseen - component
                         if correlations.get(correlation_key(a, b), D(-1)) >= policy.cluster_correlation}
            component |= additions
            frontier = additions
        unseen -= component
        components.append(tuple(sorted(component)))
    return PortfolioRiskEstimate(conservative_volatility_bound=bound, shrunk_volatility_estimate=estimate,
        covariance_status="UNKNOWN_MISSING_PAIRS" if missing else "UNKNOWN_NON_PSD" if not valid else "PSD_FIXED_DIAGONAL_SHRINKAGE",
        correlated_components=tuple(components), assumptions=("TRAILING_60_SESSION_VOLATILITY_NOT_A_FORECAST",
        "PLUS_ONE_CORRELATION_BOUND_IS_HARD_CEILING", "FIXED_SHRINKAGE_NOT_OOS_FITTED", "CORRELATION_COMPONENTS_ARE_SINGLE_LINK_CONSERVATIVE"))


@deterministic_decimal
def allocate_challenger(scores: Sequence["ChallengerScore"], features: Mapping[str, FeatureSnapshot],
                        cutoff: datetime, risk: RiskPolicy, policy: "ChallengerPolicy", regime: RegimeState,
                        *, correlations: Mapping[tuple[str, str], Decimal],
                        sector_map: Mapping[str, str | None] | None = None,
                        diagnostic: bool = False) -> ChallengerAllocation:
    if policy.diagnostic_exposure is not None and not diagnostic:
        raise ValueError("CHALLENGER_FIXED_EXPOSURE_IS_DIAGNOSTIC_ONLY")
    if any(s.policy_hash != policy.digest for s in scores):
        raise ValueError("CHALLENGER_SCORE_POLICY_MISMATCH")
    eligible = [s.bridge for s in scores if s.bridge.quant_score > 0 and not s.bridge.exclusion_reasons]
    total = sum((s.quant_score for s in eligible), D(0))
    preferred = {s.symbol: (1 - risk.min_cash_weight) * s.quant_score / total for s in eligible} if total else {}
    # No security or regime multiplier is hidden in predictive strength.
    controls = QuantPolicy.model_validate({**policy.controls.model_dump(), "strategy": "A2",
                                          "allocation": "risk_adjusted", "correlation_limit": None})
    initial = allocate([s.bridge for s in scores], features, cutoff, risk, controls, regime)
    values = weights(initial)
    changes = ["POSITION_COUNT_CAP_AND_SINGLE_INVERSE_VOLATILITY_SIZING"]
    exposure = min(1 - risk.min_cash_weight, regime.exposure_ceiling)
    if policy.diagnostic_exposure is not None:
        exposure = min(exposure, policy.diagnostic_exposure)
        changes.append("PREDECLARED_MATCHED_NOMINAL_EXPOSURE_NOT_GUARANTEED_REALIZED_EXPOSURE")
    estimated = estimate_portfolio_risk(values, features, correlations, policy)
    if estimated.covariance_status.startswith("UNKNOWN"):
        exposure = min(exposure, policy.unknown_correlation_exposure)
        changes.append(estimated.covariance_status)
    if sum(values.values(), D(0)) > exposure:
        scale = exposure / sum(values.values(), D(0))
        values = {s: v * scale for s, v in values.items()}
        changes.append("PORTFOLIO_EXPOSURE_CEILING_ONCE")
    for component in estimated.correlated_components:
        mass = sum((values[s] for s in component), D(0))
        if len(component) > 1 and mass > policy.cluster_weight_cap:
            for symbol in component:
                values[symbol] *= policy.cluster_weight_cap / mass
            changes.append("CORRELATED_COMPONENT_CAP:" + ",".join(component))
    if risk.max_sector_weight < 1:
        for symbol in sorted(values):
            if sector_map is None or symbol not in sector_map:
                values[symbol] = D(0)
                changes.append("SECTOR_METADATA_UNKNOWN:" + symbol)
        sectors = sorted({v for v in (sector_map or {}).values() if v})
        for sector in sectors:
            names = [s for s in sorted(values) if (sector_map or {}).get(s) == sector]
            mass = sum((values[s] for s in names), D(0))
            if mass > risk.max_sector_weight:
                for symbol in names:
                    values[symbol] *= risk.max_sector_weight / mass
                changes.append("SECTOR_EXPOSURE_CAP:" + sector)
    estimated = estimate_portfolio_risk(values, features, correlations, policy)
    if estimated.conservative_volatility_bound > policy.controls.target_volatility:
        scale = policy.controls.target_volatility / estimated.conservative_volatility_bound
        values = {s: v * scale for s, v in values.items()}
        changes.append("PORTFOLIO_CONSERVATIVE_VOLATILITY_CEILING_ONCE")
    feasible = target_from_weights(values, cutoff, policy.version)
    if not validate_weights(weights(feasible), risk):
        raise ValueError("CHALLENGER_INFEASIBLE_RISK_TARGET")
    return ChallengerAllocation(preferred_target=target_from_weights(preferred, cutoff, policy.version),
        feasible_target=feasible, risk=estimate_portfolio_risk(weights(feasible), features, correlations, policy),
        modifications=tuple(changes))


def rebalance_decision_hash(target: TargetPortfolio, current: Mapping[str, Decimal], *, nav: Decimal,
                            risk: RiskPolicy, policy: "ChallengerPolicy", costs: CostPolicy) -> str:
    import hashlib
    import json
    return hashlib.sha256(json.dumps({"target": target.model_dump(mode="json"),
        "current": {s: str(current[s]) for s in sorted(current)}, "nav": str(nav),
        "risk": risk.model_dump(mode="json"), "policy": policy.digest,
        "costs": costs.model_dump(mode="json")}, sort_keys=True).encode()).hexdigest()


@deterministic_decimal
def challenger_rebalance(allocation: ChallengerAllocation, current: Mapping[str, Decimal], *, nav: Decimal,
                         risk: RiskPolicy, policy: "ChallengerPolicy", costs: CostPolicy,
                         dollar_volumes: Mapping[str, Decimal | None], sessions_since_rebalance: int = 5,
                         estimate: "ExpectedReturnEstimate | None" = None, feature_hash: str = "",
                         horizon_sessions: int = 20) -> RebalanceDecision:
    # Bind a forecast to the actual cost-adjusted proposal, after bands and
    # turnover scaling. A forecast for an unconstrained target is not reusable.
    result = cost_aware_target(allocation.feasible_target, current, nav=nav, risk=risk,
        policy=policy.controls, costs=costs, sessions_since_rebalance=sessions_since_rebalance,
        dollar_volumes=dollar_volumes)
    result = result.model_copy(update={"target": target_from_weights(weights(result.target), result.target.as_of, policy.version)})
    decision_hash = rebalance_decision_hash(result.target, current, nav=nav, risk=risk, policy=policy, costs=costs)
    improvement = None if estimate is None else estimate.conservative_improvement(
        decision_at=allocation.feasible_target.as_of, feature_hash=feature_hash,
        decision_hash=decision_hash, horizon_sessions=horizon_sessions)
    if improvement is not None and result.action == "REBALANCE":
        result = cost_aware_target(result.target, current, nav=nav, risk=risk,
            policy=policy.controls, costs=costs, sessions_since_rebalance=sessions_since_rebalance,
            expected_improvement=improvement, dollar_volumes=dollar_volumes)
    reasons = list(result.reasons)
    if improvement is None:
        reasons.append("EXPECTED_RETURN_UNCALIBRATED")
    if costs.spread_bps is None:
        reasons.append("SPREAD_UNKNOWN")
    return result.model_copy(update={"reasons": tuple(dict.fromkeys(reasons)),
        "target": target_from_weights(weights(result.target), result.target.as_of, policy.version)})
