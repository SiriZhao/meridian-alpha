"""PIT, golden formula, normalization and regime regression coverage."""

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from meridian.historical import HistoricalAdjustmentStatus, HistoricalQuality
from meridian.quant.features import compute_features
from meridian.quant.policy import QuantPolicy
from meridian.quant.regime import detect_regime
from meridian.quant.signals import QuantFactorEngine
from tests.quant_helpers import cutoff, histories, synthetic_dataset

D = Decimal


@pytest.fixture
def inputs():
    dataset = synthetic_dataset()
    data = histories(dataset)
    when = cutoff(dataset)
    features = {s: compute_features(h, when, benchmark=data["SPY"], diagnostic=True) for s, h in data.items()}
    return dataset, data, when, features


@pytest.mark.parametrize("name,n", [("momentum_1m", 21), ("momentum_3m", 63), ("momentum_6m", 126), ("momentum_12m", 252)])
def test_golden_momentum_formula(inputs, name, n):
    _, data, _, features = inputs
    bars = data["AAPL"].bars[:280]
    assert features["AAPL"].value(name) == bars[-1].close / bars[-n - 1].close - 1
    assert features["AAPL"].synthetic
    assert features["AAPL"].quality_status == "SYNTHETIC_DIAGNOSTIC"


def test_golden_skip_month_and_relative_momentum(inputs):
    _, data, _, features = inputs
    bars = data["AAPL"].bars[:280]
    assert features["AAPL"].value("momentum_12_1") == bars[-22].close / bars[-253].close - 1
    assert features["AAPL"].value("relative_momentum_6m") == features["AAPL"].value("momentum_6m") - features["SPY"].value("momentum_6m")


def test_future_bar_changes_do_not_change_past_snapshot(inputs):
    _, data, when, features = inputs
    source = data["AAPL"]
    bars = tuple(b if b.available_at <= when else b.model_copy(update={"close": b.close * 9, "high": b.high * 10}) for b in source.bars)
    altered = source.model_copy(update={"bars": bars})
    assert compute_features(altered, when, benchmark=data["SPY"], diagnostic=True) == features["AAPL"]


def test_price_revision_changes_lineage_not_just_row_id(inputs):
    _, data, when, features = inputs
    source = data["AAPL"]
    bars = list(source.bars)
    bars[275] = bars[275].model_copy(update={"close": bars[275].close * D("1.0001")})
    altered = compute_features(source.model_copy(update={"bars": tuple(bars)}), when, benchmark=data["SPY"], diagnostic=True)
    assert altered.input_hash != features["AAPL"].input_hash


@pytest.mark.parametrize("updates,reason", [({"adjustment_status": HistoricalAdjustmentStatus.RAW}, "UNVERIFIED_ADJUSTMENT_BASIS"),
                                           ({"quality": HistoricalQuality.UNVERIFIED}, "UNVERIFIED_PRICE_SERIES"),
                                           ({"close": D(0)}, "NONPOSITIVE_PRICE"),
                                           ({"canonical_symbol": "MSFT"}, "SYMBOL_MISMATCH")])
def test_bad_bar_quality_is_explicit(inputs, updates, reason):
    _, data, when, _ = inputs
    source = data["AAPL"]
    bars = list(source.bars)
    bars[275] = bars[275].model_copy(update=updates)
    result = compute_features(source.model_copy(update={"bars": tuple(bars)}), when, diagnostic=True)
    assert reason in result.reasons
    assert all(f.raw_value is None and f.missing_reason for f in result.factors)


def test_missing_session_and_late_availability_no_fill(inputs):
    _, data, when, _ = inputs
    source = data["AAPL"]
    for bars in (tuple(b for i, b in enumerate(source.bars) if i != 275),
                 tuple(b if i != 275 else b.model_copy(update={"available_at": when + timedelta(days=1)}) for i, b in enumerate(source.bars))):
        result = compute_features(source.model_copy(update={"bars": bars}), when, diagnostic=True)
        assert "MISSING_SESSION_NO_FORWARD_FILL" in result.reasons


def test_missing_latest_bar_is_stale(inputs):
    _, data, when, _ = inputs
    source = data["AAPL"]
    bars = tuple(b for i, b in enumerate(source.bars) if i != 279)
    assert "STALE_HISTORY" in compute_features(source.model_copy(update={"bars": bars}), when, diagnostic=True).reasons


def test_no_volume_is_unknown_liquidity_not_zero(inputs):
    _, data, when, _ = inputs
    source = data["AAPL"]
    bars = tuple(b.model_copy(update={"volume": D(0)}) if i == 275 else b for i, b in enumerate(source.bars))
    features = compute_features(source.model_copy(update={"bars": bars}), when, diagnostic=True)
    factor = next(f for f in features.factors if f.name == "dollar_volume_20")
    assert factor.raw_value is None and factor.missing_reason == "ZERO_OR_UNAVAILABLE_VOLUME"
    with pytest.raises(ValidationError):
        source.bars[0].model_validate({**source.bars[0].model_dump(), "volume": None})


@pytest.mark.parametrize("n", [1, 20, 60, 126, 199, 252])
def test_insufficient_history_explicit(inputs, n):
    _, data, _, _ = inputs
    source = data["AAPL"]
    when = source.bars[n - 1].available_at
    result = compute_features(source, when, diagnostic=True)
    assert result.value("momentum_12_1") is None
    factor = next(f for f in result.factors if f.name == "momentum_12_1")
    assert factor.missing_reason


def test_synthetic_never_eligible_by_default(inputs):
    _, data, when, _ = inputs
    result = compute_features(data["AAPL"], when)
    assert "UNVERIFIED_PRICE_SERIES" in result.reasons


def test_cutoff_timezone_and_benchmark_identity(inputs):
    _, data, when, _ = inputs
    with pytest.raises(ValueError, match="TIMEZONE"):
        compute_features(data["AAPL"], when.replace(tzinfo=None))
    with pytest.raises(ValueError, match="SPY"):
        compute_features(data["AAPL"], when, benchmark=data["MSFT"], diagnostic=True)


@pytest.mark.parametrize("strategy", ["A0", "A1", "A2", "A3", "A4"])
def test_scores_reproducible_explained_and_uncalibrated(inputs, strategy):
    _, _, _, features = inputs
    policy = QuantPolicy(strategy=strategy)
    regime = detect_regime(features["SPY"], policy)
    engine = QuantFactorEngine()
    scores = engine.score(list(features.values()), policy, regime)
    assert scores == engine.score(list(reversed(list(features.values()))), policy, regime)
    assert all(0 <= s.quant_score <= 1 and s.predictive_confidence is None and s.domain_score().confidence == 0 for s in scores)
    for score in scores:
        total = sum((c.contribution for c in score.contributions), D(0))
        if not score.exclusion_reasons:
            assert score.quant_score == min(D(1), total * score.risk_multiplier)


def test_small_universe_fallback_and_prior_guard(inputs):
    _, _, when, features = inputs
    policy = QuantPolicy(strategy="A2")
    state = detect_regime(features["SPY"], policy)
    result = QuantFactorEngine().score([features["AAPL"]], policy, state)
    assert all(c.normalization == "ABSOLUTE_BOUNDED_SMALL_N_OR_TIES" for c in result[0].contributions)
    with pytest.raises(ValueError, match="NOT_PRIOR"):
        QuantFactorEngine().score([features["AAPL"]], policy, state, prior={"AAPL": result[0]})
    prior = result[0].model_copy(update={"as_of": when - timedelta(days=1), "quant_score": D(0)})
    changed = QuantFactorEngine().score([features["AAPL"]], policy, state, prior={"AAPL": prior})
    assert changed[0].score_change == changed[0].quant_score


def test_regime_requires_complete_spy_and_combines_dimensions(inputs):
    _, _, _, features = inputs
    policy = QuantPolicy()
    assert detect_regime(None, policy).risk_multiplier == 0
    state = detect_regime(features["SPY"], policy)
    assert state.trend in {"TRENDING_UP", "TRENDING_DOWN", "RANGE_BOUND"}
    assert 0 <= state.exposure_ceiling <= 1
    with pytest.raises(ValueError, match="SPY"):
        detect_regime(features["AAPL"], policy)


def test_future_regime_cannot_score_past_features(inputs):
    _, _, when, features = inputs
    policy = QuantPolicy()
    future = detect_regime(features["SPY"], policy).model_copy(update={"as_of": when + timedelta(days=1)})
    with pytest.raises(ValueError, match="REGIME_CUTOFF"):
        QuantFactorEngine().score(list(features.values()), policy, future)
