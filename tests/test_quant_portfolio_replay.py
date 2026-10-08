"""Portfolio invariants, costs, chronological replay and research isolation."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from meridian.quant.backtest import WalkForwardFold, WalkForwardRunner
from meridian.quant.experiments import (
    ExperimentPlan,
    ExperimentVariant,
    isolated_output,
    run_experiments,
)
from meridian.quant.features import compute_features
from meridian.quant.metrics import paired_block_interval, performance
from meridian.quant.policy import CostPolicy, QuantPolicy
from meridian.quant.portfolio import (
    allocate,
    cost_aware_target,
    target_from_weights,
    validate_weights,
    weights,
)
from meridian.quant.regime import detect_regime
from meridian.quant.signals import QuantFactorEngine
from tests.quant_helpers import cutoff, folds, histories, risk_policy, synthetic_dataset

D = Decimal


@pytest.fixture
def inputs():
    dataset = synthetic_dataset()
    data = histories(dataset)
    when = cutoff(dataset)
    features = {s: compute_features(h, when, benchmark=data["SPY"], diagnostic=True) for s, h in data.items()}
    return dataset, when, features


@pytest.mark.parametrize("allocation", ["score", "inverse_volatility", "risk_adjusted"])
@pytest.mark.parametrize("strategy", ["A1", "A2", "A3", "A4"])
def test_allocation_constraints(inputs, allocation, strategy):
    _, when, features = inputs
    policy = QuantPolicy(strategy=strategy, allocation=allocation)
    regime = detect_regime(features["SPY"], policy)
    scores = QuantFactorEngine().score(list(features.values()), policy, regime)
    target = allocate(scores, features, when, risk_policy(), policy, regime)
    assert validate_weights(weights(target), risk_policy())
    assert target.cash_weight >= risk_policy().min_cash_weight
    assert sum(weights(target).values(), D(0)) + target.cash_weight == 1
    if strategy == "A4":
        assert 1 - target.cash_weight <= regime.exposure_ceiling


def test_unknown_correlation_and_underfilled_universe_fail_closed(inputs):
    _, when, features = inputs
    policy = QuantPolicy(strategy="A2", allocation="score", correlation_limit=D(".9"))
    regime = detect_regime(features["SPY"], policy)
    scores = QuantFactorEngine().score(list(features.values()), policy, regime)
    target = allocate(scores, features, when, risk_policy(), policy, regime)
    assert len(target.positions) <= 1
    assert target.cash_weight >= D(".75")


def test_no_trade_band_and_cost_benefit_gate(inputs):
    _, when, _ = inputs
    policy = QuantPolicy(strategy="A2")
    costs = CostPolicy()
    risk = risk_policy()
    target = target_from_weights({"AAPL": D(".101")}, when, policy.version)
    result = cost_aware_target(target, {"AAPL": D(".1")}, nav=D(100000), risk=risk, policy=policy, costs=costs)
    assert result.action == "NO_ACTION"
    target = target_from_weights({"AAPL": D(".2")}, when, policy.version)
    result = cost_aware_target(target, {"AAPL": D(".1")}, nav=D(100000), risk=risk, policy=policy, costs=costs, expected_improvement=D(".000001"))
    assert result.action == "NO_ACTION" and "EXPECTED_BENEFIT_BELOW_COST" in result.reasons


def test_turnover_cap_liquidity_and_weekly(inputs):
    _, when, _ = inputs
    policy = QuantPolicy(strategy="A2", rebalance="weekly")
    risk = risk_policy()
    target = target_from_weights({"AAPL": D(".25"), "MSFT": D(".25")}, when, policy.version)
    result = cost_aware_target(target, {}, nav=D(100000), risk=risk, policy=policy, costs=CostPolicy(), sessions_since_rebalance=5)
    assert result.expected_turnover <= policy.max_turnover
    result = cost_aware_target(target, {}, nav=D(100000), risk=risk, policy=policy, costs=CostPolicy(), sessions_since_rebalance=0)
    assert result.action == "NO_ACTION"
    result = cost_aware_target(target, {}, nav=D(100000), risk=risk, policy=policy, costs=CostPolicy(), dollar_volumes={"AAPL": None, "MSFT": D(1)})
    assert result.action == "NO_ACTION" and any(r.startswith("LIQUIDITY") for r in result.reasons)


def test_forced_risk_exit_is_not_suppressed_by_band(inputs):
    _, when, _ = inputs
    target = target_from_weights({}, when, "quant-v2.1")
    result = cost_aware_target(target, {"AAPL": D(".2")}, nav=D(100000), risk=risk_policy(),
                              policy=QuantPolicy(rebalance="weekly", no_trade_band=D(".3")), costs=CostPolicy(), sessions_since_rebalance=0)
    assert result.action == "REBALANCE" and not result.target.positions


@pytest.mark.parametrize("nav", [D(0), D(-1), D("NaN")])
def test_invalid_nav_rejected(inputs, nav):
    _, when, _ = inputs
    with pytest.raises(ValueError):
        cost_aware_target(target_from_weights({}, when, "v2"), {}, nav=nav, risk=risk_policy(), policy=QuantPolicy(), costs=CostPolicy())


def test_cost_golden_unknown_spread_and_input_bounds():
    costs = CostPolicy()
    assert costs.estimate(D(10000), 2) == D(7)
    assert costs.spread_bps is None
    assert CostPolicy(spread_bps=D(4)).estimate(D(10000), 2) == D(9)
    with pytest.raises(ValueError):
        costs.estimate(D(-1), 1)


@pytest.mark.parametrize("strategy", ["CASH", "SPY_BUY_HOLD", "EQUAL_WEIGHT", "A0", "A1", "A2", "A3", "A4"])
def test_replay_delay_cash_costs_and_determinism(strategy):
    dataset = synthetic_dataset()
    policy = QuantPolicy(strategy=strategy if strategy.startswith("A") else "A2", allocation="score", rebalance="daily", use_cost_gate=False)
    runner = WalkForwardRunner(dataset, diagnostic=True)
    result = runner.run(policy, CostPolicy(), risk_policy(), folds(dataset)[0], strategy=strategy)
    assert result == runner.run(policy, CostPolicy(), risk_policy(), folds(dataset)[0], strategy=strategy)
    assert all(t.signal_at < t.execution_at and t.quantity % 1 == 0 for t in result.trades)
    assert all(d.cash >= 0 and 0 <= d.exposure <= 1 and d.costs >= 0 for d in result.days)
    assert not result.automatic_promotion
    metrics = performance(result)
    assert metrics["status"] == "SYNTHETIC_DIAGNOSTIC"
    if strategy == "CASH":
        assert metrics["CAGR"] == 0 and not result.trades
    elif strategy == "SPY_BUY_HOLD":
        assert len(result.trades) == 1


def test_replay_higher_cost_stress_buy_hold():
    dataset = synthetic_dataset()
    runner = WalkForwardRunner(dataset, diagnostic=True)
    policy = QuantPolicy(strategy="A2")
    base = runner.run(policy, CostPolicy(), risk_policy(), folds(dataset)[0], strategy="SPY_BUY_HOLD")
    stressed = runner.run(policy, CostPolicy(slippage_bps=D(50), commission_per_order=D(10)), risk_policy(), folds(dataset)[0], strategy="SPY_BUY_HOLD")
    assert stressed.days[-1].nav < base.days[-1].nav
    assert all(d.cash >= 0 for d in stressed.days)


@pytest.mark.parametrize("updates,diagnostic,reason", [({"evidence_status": "UNVERIFIED"}, True, "PIT_DATA"),
                                                       ({}, False, "SYNTHETIC"),
                                                       ({"universe_basis": "CURRENT_SURVIVORS"}, True, "SURVIVORSHIP"),
                                                       ({"corporate_actions_covered_until": None}, True, "CORPORATE_ACTION")])
def test_dataset_preflight_blocks_bad_evidence(updates, diagnostic, reason):
    dataset = synthetic_dataset()
    altered = dataset.model_copy(update=updates)
    with pytest.raises(ValueError, match=reason):
        WalkForwardRunner(altered, diagnostic=diagnostic).run(QuantPolicy(), CostPolicy(), risk_policy(), folds(dataset)[0])


def test_chronological_and_embargo_checks():
    dataset = synthetic_dataset()
    fold = folds(dataset)[0]
    with pytest.raises(ValueError, match="CHRONOLOGY"):
        WalkForwardFold.model_validate({**fold.model_dump(), "test_start": fold.validation_end})
    bad = fold.model_copy(update={"embargo_sessions": 99})
    with pytest.raises(ValueError, match="EMBARGO"):
        WalkForwardRunner(dataset, diagnostic=True).run(QuantPolicy(), CostPolicy(), risk_policy(), bad)


def test_future_history_revision_cannot_change_earlier_fills():
    dataset = synthetic_dataset()
    fold = folds(dataset)[0]
    cutoff_date = dataset.series[0].bars[300].session
    changed_series = tuple(s.model_copy(update={"bars": tuple(b if b.session <= cutoff_date else b.model_copy(update={"close": b.close * D("1.001")}) for b in s.bars)}) for s in dataset.series)
    changed = dataset.model_copy(update={"series": changed_series})
    policy = QuantPolicy(strategy="A2", allocation="score")
    left = WalkForwardRunner(dataset, diagnostic=True).run(policy, CostPolicy(), risk_policy(), fold)
    right = WalkForwardRunner(changed, diagnostic=True).run(policy, CostPolicy(), risk_policy(), fold)
    assert [t for t in left.trades if t.execution_at.date() <= cutoff_date] == [t for t in right.trades if t.execution_at.date() <= cutoff_date]
    assert [d for d in left.days if d.session <= cutoff_date] == [d for d in right.days if d.session <= cutoff_date]


def test_registry_freezes_plan_before_oos_and_resume(tmp_path: Path):
    dataset = synthetic_dataset()
    policy = QuantPolicy(strategy="A2")
    variant = ExperimentVariant(name="A2", strategy="A2", policy=policy, costs=CostPolicy(), purpose="engineering diagnostic")
    plan = ExperimentPlan(declared_at=cutoff(dataset), folds=(folds(dataset)[0],), variants=(variant,), risk=risk_policy())
    result = run_experiments(dataset, plan, tmp_path, diagnostic=True)
    assert result["status"] == "DIAGNOSTIC_ONLY" and not result["financial_alpha_demonstrated"]
    assert result == run_experiments(dataset, plan, tmp_path, diagnostic=True)
    altered = plan.model_copy(update={"variants": (variant.model_copy(update={"policy": policy.model_copy(update={"trend_weight": D(".25"), "momentum_weight": D(".75")})}),)})
    with pytest.raises(ValueError, match="IMMUTABLE"):
        run_experiments(dataset, altered, tmp_path, diagnostic=True)
    assert json.loads(Path(str(result["summary_path"])).read_text(encoding="utf-8"))["plan_hash"] == plan.digest


def test_research_output_denies_canonical_runtime():
    with pytest.raises(ValueError, match="CANONICAL"):
        isolated_output(Path("E:/MeridianAlphaRuntime/reports/quant-test"))


def test_paired_dependence_interval_determinism():
    left = [.001 * (i % 7 - 3) for i in range(120)]
    right = [.0002 for _ in left]
    assert paired_block_interval(left, right) == paired_block_interval(left, right)
    assert paired_block_interval(left[:5], right[:5])["interval"] is None


def test_synthetic_cannot_be_relabelled_as_financial_evidence():
    dataset = synthetic_dataset().model_copy(update={"evidence_status": "VERIFIED_PIT"})
    with pytest.raises(ValueError, match="SYNTHETIC_EVIDENCE_STATUS_MISMATCH"):
        WalkForwardRunner(dataset, diagnostic=True).run(QuantPolicy(), CostPolicy(), risk_policy(), folds(dataset)[0])


def test_no_action_means_no_simulated_trades():
    dataset = synthetic_dataset()
    policy = QuantPolicy(strategy="A2", allocation="score", rebalance_threshold=D(2))
    result = WalkForwardRunner(dataset, diagnostic=True).run(policy, CostPolicy(), risk_policy(), folds(dataset)[0])
    assert all(d.decision == "NO_ACTION" for d in result.days)
    assert not result.trades


def test_missing_pit_sector_cannot_be_guessed():
    dataset = synthetic_dataset().model_copy(update={"security_metadata": ()})
    with pytest.raises(ValueError, match="PIT_SECURITY_METADATA"):
        WalkForwardRunner(dataset, diagnostic=True).run(QuantPolicy(strategy="A2"), CostPolicy(), risk_policy(), folds(dataset)[0])


def test_missing_execution_bar_fails_instead_of_being_filled():
    dataset = synthetic_dataset()
    data = list(dataset.series)
    source = data[0]
    data[0] = source.model_copy(update={"bars": tuple(b for i, b in enumerate(source.bars) if i != 290)})
    changed = dataset.model_copy(update={"series": tuple(data)})
    with pytest.raises(ValueError, match="MISSING_EXECUTION|MISSING_SESSION"):
        WalkForwardRunner(changed, diagnostic=True).run(QuantPolicy(strategy="A2"), CostPolicy(), risk_policy(), folds(dataset)[0])


def test_future_membership_is_not_an_eligible_candidate():
    dataset = synthetic_dataset()
    late = dataset.series[0].bars[-1].available_at
    changed = dataset.model_copy(update={"memberships": tuple(m.model_copy(update={"known_at": late}) for m in dataset.memberships)})
    result = WalkForwardRunner(changed, diagnostic=True).run(QuantPolicy(strategy="A2"), CostPolicy(), risk_policy(), folds(dataset)[0])
    assert not result.trades
