"""Shadow construction safety and replay identity, not financial performance tests."""
from datetime import timedelta
from decimal import Decimal

import pytest

from meridian.quant.backtest import WalkForwardRunner, pit_correlations
from meridian.quant.features import compute_challenger_features
from meridian.quant.flagship_packet import build_flagship_packet
from meridian.quant.flagship_policy import FlagshipPolicy
from meridian.quant.flagship_portfolio import construct_flagship
from meridian.quant.flagship_replay import FlagshipWalkForwardRunner
from meridian.quant.policy import CostPolicy
from meridian.quant.portfolio import validate_weights, weights
from meridian.quant.regime import detect_regime
from meridian.quant.signals import score_challenger
from meridian.quant.version import ENGINE_SOURCE_HASH
from tests.quant_helpers import cutoff, folds, histories, risk_policy, synthetic_dataset

D = Decimal


@pytest.fixture(scope='module')
def inputs():
    dataset = synthetic_dataset()
    history = histories(dataset)
    at = cutoff(dataset)
    policy = FlagshipPolicy()
    extended = {s: compute_challenger_features(h, at, benchmark=history['SPY'], diagnostic=True) for s, h in history.items()}
    features = {s: f.base for s, f in extended.items()}
    state = detect_regime(features['SPY'], policy.baseline.controls)
    scores = score_challenger([f for s, f in extended.items() if s != 'SPY'], policy.baseline, state)
    return dict(scores=scores, features=features, cutoff=at, risk=risk_policy(), regime=state,
        current={}, correlations=pit_correlations(history, at, 60),
        sector_map={m.symbol: m.sector for m in dataset.security_metadata},
        asset_types={m.symbol: m.asset_type for m in dataset.security_metadata}, extended=extended, diagnostic=True)


@pytest.mark.parametrize('method', ['V22_BASELINE', 'INVERSE_VOLATILITY', 'SHRUNK_RISK_BUDGET', 'COST_CONSTRAINED', 'REGIME_CONDITIONED'])
def test_construction_is_bounded_safe_and_deterministic(inputs, method):
    policy = FlagshipPolicy(construction=method)
    result = construct_flagship(**inputs, policy=policy)
    assert result.stable_json() == construct_flagship(**inputs, policy=policy).stable_json()
    assert validate_weights(weights(result.allocation.feasible_target), inputs['risk'])
    assert result.allocation.feasible_target.cash_weight >= inputs['risk'].min_cash_weight
    assert result.evaluated_candidates <= 2 * len(inputs['scores']) * len(policy.step_sizes) * policy.sweeps_per_step
    if result.objective_after is not None:
        assert result.objective_before is not None
        assert result.objective_after <= result.objective_before + D('.000001')
    assert result.expected_return is None and result.authority == 'SHADOW_ONLY'


@pytest.mark.parametrize('bad', [D('NaN'), D('Infinity'), D('-.01'), D('1.01')])
def test_invalid_current_weights_refused(inputs, bad):
    with pytest.raises(ValueError):
        construct_flagship(**(inputs | {'current': {'AAPL': bad}}), policy=FlagshipPolicy())


def test_nonfinite_factor_cannot_reach_covariance(inputs):
    bad = dict(inputs['features'])
    factor = bad['SPY'].factors[0].model_copy(update={'raw_value': D('NaN')})
    bad['SPY'] = bad['SPY'].model_copy(update={'factors': (factor, *bad['SPY'].factors[1:])})
    with pytest.raises(ValueError, match='NONFINITE_FACTOR'):
        construct_flagship(**(inputs | {'features': bad, 'extended': None}), policy=FlagshipPolicy())


def test_future_and_symbol_mismatch_refused(inputs):
    bad = dict(inputs['features'])
    bad['AAPL'] = bad['AAPL'].model_copy(update={'as_of': inputs['cutoff'] + timedelta(days=1)})
    with pytest.raises(ValueError, match='FUTURE_INFORMATION'):
        construct_flagship(**(inputs | {'features': bad}), policy=FlagshipPolicy())
    with pytest.raises(ValueError, match='DUPLICATE'):
        construct_flagship(**(inputs | {'scores': inputs['scores'] * 2}), policy=FlagshipPolicy())


def test_missing_correlation_is_explicit_fallback(inputs):
    result = construct_flagship(**(inputs | {'correlations': {}}), policy=FlagshipPolicy())
    assert sum(weights(result.allocation.feasible_target).values(), D(0)) <= D('.25')
    assert any('UNKNOWN' in reason for reason in result.reasons)


@pytest.mark.parametrize('field,value', [('target_volatility', '.20'), ('max_turnover', '.3'), ('max_volume_participation', '.02')])
def test_policy_cannot_weaken_v22_safety(field, value):
    baseline = FlagshipPolicy().baseline
    controls = baseline.controls.model_copy(update={field: D(value)})
    with pytest.raises(ValueError, match='CEILING'):
        FlagshipPolicy(baseline=baseline.model_copy(update={'controls': controls}))


def test_real_public_evidence_cannot_enter_strict_replay():
    dataset = synthetic_dataset().model_copy(update={'evidence_status': 'UNVERIFIED'})
    with pytest.raises(ValueError, match='UNVERIFIED'):
        FlagshipWalkForwardRunner(dataset, FlagshipPolicy(), diagnostic=True).run_flagship(CostPolicy(), risk_policy(), folds(dataset)[0])


def test_v22_replay_baseline_identical_and_v23_next_open():
    dataset = synthetic_dataset()
    fold = folds(dataset)[0]
    policy = FlagshipPolicy(construction='V22_BASELINE')
    old = WalkForwardRunner(dataset, diagnostic=True).run(policy.baseline.controls, CostPolicy(), risk_policy(), fold, strategy='V22', challenger=policy.baseline)
    new = FlagshipWalkForwardRunner(dataset, policy, diagnostic=True).run_flagship(CostPolicy(), risk_policy(), fold)
    assert new.days == old.days and new.trades == old.trades
    assert new.engine_hash != old.engine_hash and old.engine_hash == ENGINE_SOURCE_HASH
    challenger = FlagshipWalkForwardRunner(dataset, FlagshipPolicy(), diagnostic=True).run_flagship(CostPolicy(), risk_policy(), fold)
    assert all(t.signal_at < t.execution_at for t in challenger.trades)
    assert all(d.cash >= 0 and d.exposure <= 1 for d in challenger.days)
    assert challenger.evidence_status == 'SYNTHETIC_DIAGNOSTIC'


@pytest.mark.parametrize('bad', [D('NaN'), D('Infinity'), D('-1.01'), D('1.01')])
def test_invalid_correlation_refused(inputs, bad):
    with pytest.raises(ValueError, match='CORRELATION'):
        construct_flagship(**(inputs | {'correlations': {('AAPL', 'MSFT'): bad}}), policy=FlagshipPolicy())


@pytest.mark.parametrize('nav', [D('NaN'), D('Infinity'), D('0'), D('-1')])
def test_invalid_capital_refused(inputs, nav):
    with pytest.raises(ValueError):
        construct_flagship(**inputs, policy=FlagshipPolicy(), nav=nav)


def test_perfect_growth_correlation_preserves_cluster_cap(inputs):
    symbols = sorted(inputs['features'])
    correlations = {(a, b): D(1) for i, a in enumerate(symbols) for b in symbols[i + 1:]}
    result = construct_flagship(**(inputs | {'correlations': correlations}), policy=FlagshipPolicy())
    assert sum(weights(result.allocation.feasible_target).values(), D(0)) <= D('.4')


def test_unknown_instability_proposes_cash_but_not_trade(inputs):
    result = construct_flagship(**(inputs | {'extended': None}), policy=FlagshipPolicy(construction='REGIME_CONDITIONED'))
    assert result.allocation.feasible_target.cash_weight == 1
    assert result.allocation.risk.conservative_volatility_bound == 0
    assert any('UNKNOWN' in r for r in result.reasons)


def test_packet_exposes_actual_engine_and_never_authorizes_orders():
    dataset = synthetic_dataset()
    packet = build_flagship_packet(histories(dataset), cutoff(dataset), symbols=('AAPL', 'MSFT', 'NVDA', 'QQQ', 'GLD'),
        current={}, nav=D('100000'), risk=risk_policy(), policy=FlagshipPolicy(), costs=CostPolicy(),
        sector_map={m.symbol: m.sector for m in dataset.security_metadata},
        asset_types={m.symbol: m.asset_type for m in dataset.security_metadata}, diagnostic=True)
    assert packet.scores and packet.features and packet.cost_adjusted_proposal
    assert packet.evidence_level == 'SYNTHETIC_DIAGNOSTIC' and not packet.authorized_trade
    assert packet.predictive_confidence is None and packet.expected_return is None
