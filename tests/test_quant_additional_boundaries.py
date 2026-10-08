"""Contract completeness, version identity, feeds and final OOS anti-retuning."""

from dataclasses import replace
from datetime import timedelta
from decimal import ROUND_DOWN, ROUND_UP, Context, Decimal, DefaultContext, Inexact, localcontext
from pathlib import Path

import pytest

from meridian.historical import (
    HistoricalAdjustmentStatus,
    HistoricalBar,
    HistoricalBarCertification,
    HistoricalBarSeries,
    HistoricalQuality,
    compare_historical_series,
)
from meridian.quant.backtest import WalkForwardRunner
from meridian.quant.features import FeatureSnapshot, compute_features
from meridian.quant.policy import CostPolicy, QuantPolicy
from meridian.quant.portfolio import (
    allocate,
    cost_aware_target,
    gross_turnover,
    target_from_weights,
)
from meridian.quant.regime import detect_regime
from meridian.quant.signals import QuantFactorEngine
from tests.quant_helpers import cutoff, folds, histories, risk_policy, synthetic_dataset

D = Decimal


def test_decimal_default_context_is_not_a_hidden_quant_parameter():
    costs = CostPolicy()
    expected = costs.estimate(D("12345.6789"), 3)
    previous = DefaultContext.copy()
    try:
        DefaultContext.Emax = 2
        DefaultContext.Emin = -2
        DefaultContext.traps[Inexact] = True
        assert costs.estimate(D("12345.6789"), 3) == expected
    finally:
        DefaultContext.Emax = previous.Emax
        DefaultContext.Emin = previous.Emin
        DefaultContext.traps = previous.traps.copy()


def test_turnover_sum_order_is_canonical_for_high_precision_weights():
    values = {"AAPL": D(".2000000000000000000000000001"),
              "MSFT": D(".1000000000000000000000000007"),
              "NVDA": D(".3000000000000000000000000001")}
    assert gross_turnover(values, {}) == gross_turnover(dict(reversed(list(values.items()))), {})


def test_adjusted_pit_research_contract_survives_json_without_raw_price_authority():
    # A declared contract stub, not a newly certified real observation.
    series = synthetic_dataset().series[0]
    raw = series.model_dump(mode="json")
    for bar in raw["bars"]:
        bar["certification"] = "CERTIFIED_RESEARCH_PIT_ADJUSTED"
    parsed = HistoricalBarSeries.model_validate(raw)
    assert parsed == HistoricalBarSeries.model_validate_json(parsed.stable_json())
    assert all(not bar.execution_price_eligible for bar in parsed.bars)
    feature = compute_features(parsed, cutoff(synthetic_dataset()))
    assert feature.quality_status == "VERIFIED" and feature.value("momentum_6m") is not None
    invalid = {**raw["bars"][0], "certification": "CERTIFIED_MARKET_SESSION"}
    with pytest.raises(ValueError, match="adjusted bars cannot be certified as raw"):
        HistoricalBar.model_validate(invalid)


@pytest.mark.parametrize("updates", [
    {"adjustment_status": HistoricalAdjustmentStatus.RAW},
    {"quality": HistoricalQuality.UNVERIFIED},
    {"observed_at": synthetic_dataset().series[0].bars[0].observed_at - timedelta(seconds=1)},
    {"available_at": synthetic_dataset().series[0].bars[0].available_at - timedelta(seconds=1)},
])
def test_adjusted_pit_certification_rejects_incomplete_or_premature_contract(updates):
    bar = synthetic_dataset().series[0].bars[0]
    with pytest.raises(ValueError, match="PIT adjusted research certification"):
        HistoricalBar.model_validate({**bar.model_dump(),
                                      "certification": HistoricalBarCertification.CERTIFIED_RESEARCH_PIT_ADJUSTED,
                                      **updates})


def test_backtest_cannot_skip_missing_last_or_internal_benchmark_session():
    dataset = synthetic_dataset()
    fold = folds(dataset)[0]
    for missing in (fold.test_end, dataset.series[-1].bars[300].session):
        altered = dataset.model_copy(update={"series": tuple(
            s.model_copy(update={"bars": tuple(b for b in s.bars if b.session != missing)})
            if s.canonical_symbol == "SPY" else s for s in dataset.series)})
        with pytest.raises(ValueError, match="MISSING_BENCHMARK_SESSION"):
            WalkForwardRunner(altered, diagnostic=True).run(QuantPolicy(), CostPolicy(), risk_policy(), fold)


@pytest.mark.parametrize("updates", [
    {"certification": HistoricalBarCertification.UNVERIFIED},
    {"currency": "EUR"}, {"canonical_symbol": "AAPL"}, {"open": D(0)},
])
def test_last_benchmark_mark_must_be_verified_even_without_a_trade(updates):
    dataset = synthetic_dataset()
    fold = folds(dataset)[0]
    changed = dataset.model_copy(update={"series": tuple(
        s.model_copy(update={"bars": tuple(b.model_copy(update=updates) if b.session == fold.test_end else b for b in s.bars)})
        if s.canonical_symbol == "SPY" else s for s in dataset.series)})
    with pytest.raises(ValueError, match="EXECUTION_OR_MARK_PRICE_UNVERIFIED"):
        WalkForwardRunner(changed, diagnostic=True).run(QuantPolicy(strategy="A2"), CostPolicy(), risk_policy(), fold, strategy="CASH")


@pytest.mark.parametrize("precision,rounding", [(6, ROUND_UP), (60, ROUND_DOWN)])
def test_embedding_decimal_context_cannot_change_features_scores_targets_or_replay(precision, rounding):
    dataset = synthetic_dataset()
    data = histories(dataset)
    when = cutoff(dataset)
    policy, costs, risk = QuantPolicy(), CostPolicy(), risk_policy()

    def compute():
        features = {s: compute_features(h, when, benchmark=data["SPY"], diagnostic=True) for s, h in data.items()}
        state = detect_regime(features["SPY"], policy)
        scores = QuantFactorEngine().score(list(features.values()), policy, state)
        target = allocate(scores, features, when, risk, policy, state)
        decision = cost_aware_target(target, {}, nav=D(100000), risk=risk, policy=policy,
                                    costs=costs, dollar_volumes={s: f.value("dollar_volume_20") for s, f in features.items()})
        replay = WalkForwardRunner(dataset, diagnostic=True).run(policy, costs, risk, folds(dataset)[0])
        return ([f.stable_json() for f in features.values()], [s.stable_json() for s in scores],
                target.stable_json(), decision.stable_json(), replay.stable_json(), costs.estimate(D("12345.6789"), 3))

    expected = compute()
    with localcontext(Context(prec=precision, rounding=rounding)) as context:
        context.traps[Inexact] = True
        actual = compute()
        assert context.prec == precision and context.rounding == rounding and context.traps[Inexact]
    assert actual == expected


def test_verified_factor_contract_cannot_hide_missing_columns():
    dataset = synthetic_dataset()
    feature = compute_features(dataset.series[0], cutoff(dataset), diagnostic=True)
    with pytest.raises(ValueError, match="CONTRACT_INCOMPLETE"):
        FeatureSnapshot.model_validate({**feature.model_dump(), "factors": feature.factors[:1]})


def test_provider_discrepancy_must_not_be_silently_blended():
    dataset = synthetic_dataset()
    source = dataset.series[0]
    bars = list(source.bars)
    bars[275] = bars[275].model_copy(update={"close": bars[275].close * D("1.001")})
    second = source.model_copy(update={"provider": "provider-discrepancy-fixture", "bars": tuple(bars)})
    assert compare_historical_series((source, second)).status == "MARKET_DATA_CONFLICT"
    conflicted = source.model_copy(update={"bars": tuple(b.model_copy(update={"quality": HistoricalQuality.CONFLICT}) for b in source.bars)})
    result = compute_features(conflicted, cutoff(dataset), diagnostic=True)
    assert result.quality_status == "REJECTED"


def test_allocation_future_signal_and_variance_budget():
    dataset = synthetic_dataset()
    data = histories(dataset)
    when = cutoff(dataset)
    features = {s: compute_features(h, when, benchmark=data["SPY"], diagnostic=True) for s, h in data.items()}
    policy = QuantPolicy(strategy="A3", target_volatility=D(".01"))
    state = detect_regime(features["SPY"], policy)
    scores = QuantFactorEngine().score(list(features.values()), policy, state)
    target = allocate(scores, features, when, risk_policy(), policy, state)
    bound = sum((p.target_weight * max(features[p.ticker].value("volatility_60") or D(0), policy.volatility_floor) for p in target.positions), D(0))
    assert bound <= policy.target_volatility
    future = [s.model_copy(update={"as_of": when + timedelta(days=1)}) for s in scores]
    with pytest.raises(ValueError, match="CUTOFF_MISMATCH"):
        allocate(future, features, when, risk_policy(), policy, state)


def test_turnover_infeasible_requires_review_not_risk_relaxation():
    when = cutoff(synthetic_dataset())
    risk = risk_policy().model_copy(update={"max_number_positions": 4})
    current = {"AAPL": D(".25"), "MSFT": D(".25"), "NVDA": D(".2"), "SPY": D(".2")}
    target = target_from_weights({"QQQ": D(".25"), "GLD": D(".25")}, when, "quant-v2.1")
    result = cost_aware_target(target, current, nav=D(100000), risk=risk,
                              policy=QuantPolicy(), costs=CostPolicy())
    assert result.action == "BLOCKED"


def test_universe_perturbation_preserves_replay_safety():
    dataset = synthetic_dataset()
    changed = dataset.model_copy(update={"memberships": tuple(m for m in dataset.memberships if m.symbol != "NVDA")})
    replay = WalkForwardRunner(changed, diagnostic=True).run(QuantPolicy(strategy="A2"), CostPolicy(), risk_policy(), folds(dataset)[0])
    assert all(t.symbol != "NVDA" for t in replay.trades)
    assert all(d.cash >= 0 for d in replay.days)


def test_market_service_passes_same_history_without_second_fetch(tmp_path: Path):
    from meridian.operational_data import OperationalCache, OperationalRefreshService
    from meridian.operational_market_snapshot import OperationalMarketSnapshotService
    from tests.test_operational_market_snapshot import NOW, Bars, QuoteProvider, observation
    class CountedBars(Bars):
        calls = 0
        def get_series(self, *args, **kwargs):
            self.calls += 1
            return super().get_series(*args, **kwargs)
    bars = CountedBars()
    service = OperationalMarketSnapshotService(OperationalRefreshService(QuoteProvider("primary", observation()), QuoteProvider("secondary", observation()), cache=OperationalCache(tmp_path)), bars)
    result = service.build(["AAPL"], analysis_time=NOW)
    assert bars.calls == 1 and set(result.quant_histories) == {"AAPL"}
    assert result.snapshot_hash == replace(result, quant_histories={}).snapshot_hash
