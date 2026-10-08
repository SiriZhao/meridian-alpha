"""Contract completeness, version identity, feeds and final OOS anti-retuning."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from meridian.historical import HistoricalQuality, compare_historical_series
from meridian.quant.backtest import WalkForwardRunner
from meridian.quant.features import FeatureSnapshot, compute_features
from meridian.quant.policy import CostPolicy, QuantPolicy
from meridian.quant.portfolio import allocate, cost_aware_target, target_from_weights
from meridian.quant.regime import detect_regime
from meridian.quant.signals import QuantFactorEngine
from tests.quant_helpers import cutoff, folds, histories, risk_policy, synthetic_dataset

D = Decimal


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
