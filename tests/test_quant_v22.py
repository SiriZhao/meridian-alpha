"""Challenger mathematics and safety; all observations are engineering fixtures."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from meridian.config import load_policies
from meridian.historical import HistoricalBarCertification, HistoricalBarSeries
from meridian.quant.backtest import WalkForwardRunner, pit_correlations
from meridian.quant.contracts import (
    DisabledFundamentalAdapter,
    ExpectedReturnEstimate,
    FundamentalObservation,
)
from meridian.quant.features import compute_challenger_features
from meridian.quant.packet import QuantResearchPacketV22, build_research_packet
from meridian.quant.policy import ChallengerPolicy, CostPolicy, QuantPolicy
from meridian.quant.portfolio import (
    allocate_challenger,
    challenger_rebalance,
    estimate_portfolio_risk,
    weights,
)
from meridian.quant.regime import detect_regime
from meridian.quant.signals import ChallengerScore, score_challenger
from tests.quant_helpers import cutoff, folds, histories, risk_policy, synthetic_dataset

D = Decimal
ROOT = Path(__file__).parents[1]


def inputs(policy: ChallengerPolicy | None = None, index: int = 279):
    dataset = synthetic_dataset()
    history = histories(dataset)
    when = cutoff(dataset, index)
    policy = policy or ChallengerPolicy()
    features = {s: compute_challenger_features(h, when, benchmark=history["SPY"], diagnostic=True) for s, h in history.items()}
    regime = detect_regime(features["SPY"].base, policy.controls)
    scores = score_challenger([f for s, f in features.items() if s != "SPY"], policy, regime)
    return dataset, history, when, policy, features, regime, scores


@pytest.mark.parametrize("index", [252, 279, 349])
def test_exact_windows_and_future_invariance(index: int):
    data, h, when, _, fs, _, _ = inputs(index=index)
    prices = [b.close for b in h["AAPL"].bars]
    f = fs["AAPL"]
    assert f.base.last_session is not None
    assert f.base.value("momentum_12_1") == prices[index - 21] / prices[index - 252] - 1
    assert f.momentum_acceleration == prices[index] / prices[index - 63] - prices[index - 63] / prices[index - 126]
    assert f.medium_distance == prices[index] / (sum(prices[index - 59:index + 1], D(0)) / 60) - 1
    bars = tuple(b.model_copy(update={k: getattr(b, k) * 10 for k in ("open", "high", "low", "close")}) if b.session > f.base.last_session else b for b in h["AAPL"].bars)
    changed = HistoricalBarSeries.model_validate({**h["AAPL"].model_dump(), "bars": bars})
    assert compute_challenger_features(changed, when, benchmark=h["SPY"], diagnostic=True) == f
    assert data.evidence_status == "SYNTHETIC_DIAGNOSTIC"


def test_out_of_sequence_and_duplicate_series_rejected():
    _, h, when, _, _, _, _ = inputs()
    reverse = h["AAPL"].model_copy(update={"bars": tuple(reversed(h["AAPL"].bars))})
    with pytest.raises(ValueError, match="OUT_OF_SEQUENCE"):
        compute_challenger_features(reverse, when, benchmark=h["SPY"], diagnostic=True)
    with pytest.raises(ValueError, match="duplicate sessions"):
        HistoricalBarSeries.model_validate({**h["AAPL"].model_dump(), "bars": (*h["AAPL"].bars, h["AAPL"].bars[-1])})


def test_golden_attribution_rank_separation_and_context():
    _, _, _, p, fs, regime, rows = inputs()
    row = next(r for r in rows if r.bridge.symbol == "AAPL")
    assert row.signal_strength == D("0.4973526592241052279604352853")
    assert row.bridge.quant_score == row.signal_strength
    assert row.bridge.predictive_confidence is None
    assert row.risk_adjusted_score == row.bridge.quant_score * row.bridge.risk_multiplier
    assert sum((c.weight for c in row.factor_attribution), D(0)) == 1
    with localcontext() as context:
        context.prec = 6
        assert score_challenger([fs[s] for s in reversed(list(fs)) if s != "SPY"], p, regime) == rows
        assert context.prec == 6
    with pytest.raises(ValueError, match="PREDICTIVE_CONFIDENCE"):
        ChallengerScore.model_validate({**row.model_dump(), "bridge": row.bridge.model_copy(update={"predictive_confidence": D(".99")})})


def test_missing_relative_is_penalized_not_reweighted():
    _, h, when, p, fs, regime, _ = inputs()
    missing = compute_challenger_features(h["AAPL"], when, diagnostic=True)
    row = score_challenger([missing, fs["MSFT"]], p, regime)[0]
    row = next(r for r in score_challenger([missing, fs["MSFT"]], p, regime) if r.bridge.symbol == "AAPL")
    factor = next(c for c in row.factor_attribution if c.group == "relative")
    assert factor.weight == D(".25") and factor.contribution == 0 and factor.normalized is None
    assert row.bridge.completeness == D(".75")


def test_smooth_small_universe_and_ties_have_bounded_rank_discontinuity():
    _, _, _, p, fs, state, _ = inputs()
    tied = []
    original = fs["AAPL"]
    for symbol in ("AAA", "BBB", "CCC", "DDD", "EEE"):
        base = original.base.model_copy(update={"symbol": symbol,
            "factors": tuple(f.model_copy(update={"symbol": symbol}) for f in original.base.factors)})
        tied.append(original.model_copy(update={"base": base}))
    before = score_challenger(tied, p, state)
    changed_base = tied[0].base.model_copy(update={"factors": tuple(f.model_copy(update={"raw_value": f.raw_value + D("1e-12")})
        if f.name == "momentum_6m" and f.raw_value is not None else f for f in tied[0].base.factors)})
    after = score_challenger([tied[0].model_copy(update={"base": changed_base}), *tied[1:]], p, state)
    assert max(abs(r.signal_strength - before[0].signal_strength) for r in after) < D(".01")
    four = score_challenger(tied[:4], p, state)
    assert abs(four[0].signal_strength - before[0].signal_strength) < D(".01")
    assert [r.bridge.symbol for r in before] == ["AAA", "BBB", "CCC", "DDD", "EEE"]


def test_score_change_and_observed_session_persistence():
    _, _, _, p, fs, state, previous = inputs(index=278)
    _, _, _, _, now, next_state, current = inputs(index=279)
    rows = score_challenger([f for s, f in now.items() if s != "SPY"], p, next_state,
        prior={r.bridge.symbol: r for r in previous})
    for row in rows:
        assert row.bridge.score_change is not None
        assert abs(sum(row.score_change_attribution.values(), D(0)) - row.bridge.score_change) < D("1e-26")
        assert row.positive_observations == 2
    with pytest.raises(ValueError, match="PRIOR_IDENTITY"):
        score_challenger([fs["AAPL"]], p, state, prior={r.bridge.symbol: r for r in current})


@pytest.mark.parametrize("kind", ["perfect", "negative", "missing", "non_psd"])
def test_correlation_and_conservative_volatility(kind: str):
    _, _, _, p, fs, _, _ = inputs()
    names = ["AAPL", "MSFT", "NVDA"]
    correlation = {(a, b): D(1) if kind == "perfect" else D("-.5") for i, a in enumerate(names) for b in names[i + 1:]}
    if kind == "missing":
        correlation = {}
    if kind == "non_psd":
        correlation = {("AAPL", "MSFT"): D(".9"), ("AAPL", "NVDA"): D(".9"), ("MSFT", "NVDA"): D("-.9")}
    result = estimate_portfolio_risk(dict.fromkeys(names, D(".2")), {s: f.base for s, f in fs.items()}, correlation, p)
    if kind in {"missing", "non_psd"}:
        assert result.shrunk_volatility_estimate is None and result.covariance_status.startswith("UNKNOWN")
    else:
        assert result.shrunk_volatility_estimate is not None and result.shrunk_volatility_estimate <= result.conservative_volatility_bound
    if kind == "perfect":
        assert result.correlated_components == (tuple(names),)


@pytest.mark.parametrize("group", [None, "absolute", "relative", "trend"])
def test_matched_nominal_exposure_ablation_and_feasible_caps(group: str | None):
    p = ChallengerPolicy.model_validate({"diagnostic_exposure": ".25", "neutral_groups": [group] if group else []})
    _, h, when, p, fs, state, scores = inputs(p)
    allocation = allocate_challenger(scores, {s: f.base for s, f in fs.items()}, when, risk_policy(), p, state,
        correlations=pit_correlations(h, when, 60), sector_map={s: "TEST" for s in h}, diagnostic=True)
    values = weights(allocation.feasible_target)
    assert D(".24999") <= sum(values.values(), D(0)) <= D(".25")
    assert all(v <= risk_policy().max_position_weight for v in values.values())
    assert allocation.risk.conservative_volatility_bound <= p.controls.target_volatility
    with pytest.raises(ValueError, match="DIAGNOSTIC_ONLY"):
        allocate_challenger(scores, {s: f.base for s, f in fs.items()}, when, risk_policy(), p, state,
            correlations={}, sector_map={s: "TEST" for s in h})


def test_cluster_cap_and_unknown_correlation_budget():
    _, h, when, p, fs, state, scores = inputs()
    base = {s: f.base for s, f in fs.items()}
    names = sorted(s.bridge.symbol for s in scores)
    correlations = {(a, b): D(1) for i, a in enumerate(names) for b in names[i + 1:]}
    result = allocate_challenger(scores, base, when, risk_policy(), p, state,
        correlations=correlations, sector_map={s: None for s in h})
    assert sum(weights(result.feasible_target).values(), D(0)) <= p.cluster_weight_cap
    unknown = allocate_challenger(scores, base, when, risk_policy(), p, state,
        correlations={}, sector_map={s: None for s in h})
    assert sum(weights(unknown.feasible_target).values(), D(0)) <= p.unknown_correlation_exposure


def test_no_action_has_zero_friction_and_uncalibrated_reason():
    _, h, when, p, fs, state, scores = inputs()
    allocation = allocate_challenger(scores, {s: f.base for s, f in fs.items()}, when, risk_policy(), p, state,
        correlations=pit_correlations(h, when, 60), sector_map={s: None for s in h})
    result = challenger_rebalance(allocation, weights(allocation.feasible_target), nav=D(100000),
        risk=risk_policy(), policy=p, costs=CostPolicy(), dollar_volumes={s: f.base.value("dollar_volume_20") for s, f in fs.items()})
    assert result.action == "NO_ACTION" and result.estimated_cost == 0 and result.expected_turnover == 0
    assert "EXPECTED_RETURN_UNCALIBRATED" in result.reasons and "SPREAD_UNKNOWN" in result.reasons


def test_expected_return_contract_rejects_future_training_and_identity():
    when = cutoff(synthetic_dataset())
    value = dict(horizon_sessions=20, prediction_target="PORTFOLIO_RETURN_IMPROVEMENT_OVER_HOLD", feature_cutoff=when,
        prediction_at=when, training_start=when - timedelta(days=300), training_end=when - timedelta(days=1),
        model_hash="a" * 64, data_hash="b" * 64, feature_hash="c" * 64, decision_hash="d" * 64)
    estimate = ExpectedReturnEstimate.model_validate(value)
    assert estimate.conservative_improvement(decision_at=when, feature_hash="c" * 64, decision_hash="d" * 64, horizon_sessions=20) is None
    with pytest.raises(ValueError, match="TIMING"):
        ExpectedReturnEstimate.model_validate({**value, "training_end": when})
    with pytest.raises(ValueError, match="UNCALIBRATED"):
        ExpectedReturnEstimate.model_validate({**value, "expected_improvement": ".1"})
    with pytest.raises(ValueError, match="MISMATCH"):
        estimate.conservative_improvement(decision_at=when, feature_hash="e" * 64, decision_hash="d" * 64, horizon_sessions=20)


def test_fundamentals_are_disabled_and_revisions_respect_availability():
    when = cutoff(synthetic_dataset())
    data = dict(symbol="AAPL", metric="QUALITY", fiscal_start=when.date() - timedelta(days=200), fiscal_end=when.date() - timedelta(days=100),
        release_at=when - timedelta(days=2), available_at=when - timedelta(days=2), ingested_at=when - timedelta(days=1),
        revision_id="original", value=".1", unit="ratio", source="ENGINEERING_FIXTURE", source_hash="a" * 64, certification="REVIEWED_PIT")
    original = FundamentalObservation.model_validate(data)
    revision = FundamentalObservation.model_validate({**data, "release_at": when + timedelta(days=1),
        "available_at": when + timedelta(days=1), "ingested_at": when + timedelta(days=1), "revision_id": "revision", "supersedes_revision": "original", "value": ".9"})
    adapter = DisabledFundamentalAdapter()
    assert adapter.select((original, revision), cutoff=when).status == "FUNDAMENTALS_DISABLED"
    assert adapter.select((original, revision), cutoff=when, enabled=True).observations == (original,)
    assert adapter.select((original, revision), cutoff=when + timedelta(days=2), enabled=True).observations == (revision,)
    with pytest.raises(ValueError, match="DUPLICATE"):
        adapter.select((original, original), cutoff=when, enabled=True)


def test_packet_unknown_account_is_unknown_and_has_no_authority():
    d, h, when, p, _, _, _ = inputs()
    policies = replace(load_policies(ROOT / "policies"), risk=risk_policy())
    packet = build_research_packet(h, tuple(m.symbol for m in d.memberships), cutoff=when,
        policies=policies, policy=p, metadata=d.security_metadata, diagnostic=True)
    assert packet.rebalance is None and not packet.eligible_hypothetical_drafts
    assert all(s.current_exposure is None and s.eligible_change is None for s in packet.symbols)
    assert packet.data_certification_class == "SYNTHETIC_DIAGNOSTIC"
    assert not packet.trade_authorized and packet.broker_submission == "DISABLED"
    assert QuantResearchPacketV22.model_validate_json(packet.stable_json()) == packet
    assert "仅供研究" in packet.symbols[0].chinese_explanation


def test_challenger_replay_deterministic_whole_shares_costs_and_action_gates():
    d = synthetic_dataset()
    p = ChallengerPolicy()
    runner = WalkForwardRunner(d, diagnostic=True)
    result = runner.run(p.controls, CostPolicy(), risk_policy(), folds(d)[0], strategy="V22", challenger=p)
    assert result == runner.run(p.controls, CostPolicy(), risk_policy(), folds(d)[0], strategy="V22", challenger=p)
    assert result.policy_hash == p.digest and result.evidence_status == "SYNTHETIC_DIAGNOSTIC"
    assert all(t.execution_at > t.signal_at and t.quantity == int(t.quantity) for t in result.trades)
    assert all(day.cash >= 0 and day.exposure <= 1 and (day.costs == 0 if day.turnover == 0 else day.costs > 0) for day in result.days)
    with pytest.raises(ValueError, match="CORPORATE_ACTION"):
        WalkForwardRunner(d.model_copy(update={"corporate_action_source": None}), diagnostic=True).run(
            p.controls, CostPolicy(), risk_policy(), folds(d)[0], strategy="V22", challenger=p)
    with pytest.raises(ValueError, match="CHALLENGER_POLICY_MISMATCH"):
        runner.run(QuantPolicy(), CostPolicy(), risk_policy(), folds(d)[0], strategy="V22")


def test_unverified_adjustment_never_becomes_challenger_feature():
    _, h, when, _, _, _, _ = inputs()
    unverified = h["AAPL"].model_copy(update={"bars": tuple(b.model_copy(update={"certification": HistoricalBarCertification.UNVERIFIED}) for b in h["AAPL"].bars)})
    result = compute_challenger_features(unverified, when, benchmark=h["SPY"], diagnostic=True)
    assert result.base.quality_status == "REJECTED" and result.residual_momentum_63 is None


def test_only_future_source_disorder_does_not_change_past_features():
    _, h, when, _, fs, _, _ = inputs()
    past = tuple(b for b in h["AAPL"].bars if b.available_at <= when)
    future = tuple(b for b in h["AAPL"].bars if b.available_at > when)
    series = h["AAPL"].model_copy(update={"bars": past + tuple(reversed(future))})
    assert compute_challenger_features(series, when, benchmark=h["SPY"], diagnostic=True) == fs["AAPL"]


def test_calibrated_cost_estimate_binds_post_turnover_proposal():
    from meridian.quant.portfolio import rebalance_decision_hash
    _, h, when, p, fs, state, scores = inputs()
    risk = risk_policy()
    costs = CostPolicy()
    allocation = allocate_challenger(scores, {s: f.base for s, f in fs.items()}, when, risk, p, state,
        correlations=pit_correlations(h, when, 60), sector_map={s: None for s in h})
    volumes = {s: f.base.value("dollar_volume_20") for s, f in fs.items()}
    first = challenger_rebalance(allocation, {}, nav=D(100000), risk=risk, policy=p, costs=costs, dollar_volumes=volumes)
    assert first.expected_turnover <= p.controls.max_turnover
    fingerprint = rebalance_decision_hash(first.target, {}, nav=D(100000), risk=risk, policy=p, costs=costs)
    value = dict(horizon_sessions=20, prediction_target="PORTFOLIO_RETURN_IMPROVEMENT_OVER_HOLD", feature_cutoff=when,
        prediction_at=when, training_start=when - timedelta(days=300), training_end=when - timedelta(days=1),
        model_hash="a" * 64, data_hash="b" * 64, feature_hash="c" * 64, decision_hash=fingerprint,
        calibration_status="INDEPENDENTLY_REVIEWED", review_reference="ENGINEERING_CONTRACT_FIXTURE_NOT_FINANCIAL_EVIDENCE",
        training_labels_available_at=when - timedelta(hours=12),
        expected_improvement=".00001", lower_bound=".000001", upper_bound=".00002")
    estimate = ExpectedReturnEstimate.model_validate(value)
    decision = challenger_rebalance(allocation, {}, nav=D(100000), risk=risk, policy=p, costs=costs, dollar_volumes=volumes,
        estimate=estimate, feature_hash="c" * 64)
    assert decision.action == "NO_ACTION" and decision.estimated_cost == 0
    assert "EXPECTED_BENEFIT_BELOW_COST" in decision.reasons
    wrong = estimate.model_copy(update={"decision_hash": "d" * 64})
    with pytest.raises(ValueError, match="MISMATCH"):
        challenger_rebalance(allocation, {}, nav=D(100000), risk=risk, policy=p, costs=costs,
            dollar_volumes=volumes, estimate=wrong, feature_hash="c" * 64)


def test_regime_is_a_risk_transformation_not_a_changed_predictive_signal():
    _, _, _, p, fs, state, before = inputs()
    down = state.model_copy(update={"trend": "TRENDING_DOWN", "risk_multiplier": D(".25"), "exposure_ceiling": D(".25")})
    after = score_challenger([f for s, f in fs.items() if s != "SPY"], p, down)
    assert [r.signal_strength for r in before] == [r.signal_strength for r in after]
    assert [r.bridge.quant_score for r in before] == [r.bridge.quant_score for r in after]
    assert all(r.risk_adjusted_score <= next(x.risk_adjusted_score for x in before if x.bridge.symbol == r.bridge.symbol) for r in after)


def test_future_membership_cannot_enter_v22_replay():
    d = synthetic_dataset()
    membership = tuple(m.model_copy(update={"known_at": cutoff(d, 410)}) if m.symbol == "NVDA" else m for m in d.memberships)
    p = ChallengerPolicy()
    changed = d.model_copy(update={"memberships": membership})
    result = WalkForwardRunner(changed, diagnostic=True).run(p.controls, CostPolicy(), risk_policy(), folds(d)[0], strategy="V22", challenger=p)
    assert all(t.symbol != "NVDA" for t in result.trades)


@pytest.mark.parametrize("missing_sell_bid", [False, True])
def test_packet_rejects_sector_buys_that_depend_on_sell_fills(monkeypatch, missing_sell_bid: bool):
    import meridian.quant.packet as packet_module
    from meridian.quant.backtest import QuantSecurityMetadata
    from meridian.schemas import (
        AccountSnapshot,
        AccountSyncState,
        FreshnessState,
        Holding,
        MarketSnapshot,
    )
    d, h, when, p, _, _, _ = inputs()
    # Explicit domain-contract stubs, never relabeled financial research evidence.
    h = {s: HistoricalBarSeries.model_validate({**v.model_dump(), "bars": tuple(b.model_copy(update={
        "certification": HistoricalBarCertification.CERTIFIED_RESEARCH_PIT_ADJUSTED}) for b in v.bars)}) for s, v in h.items()}
    policies = replace(load_policies(ROOT / "policies"), risk=risk_policy().model_copy(update={"max_position_weight": D(".2"), "max_sector_weight": D(".15")}))
    snapshot = AccountSnapshot(snapshot_id="HYPOTHETICAL_CONTRACT_TEST", account_alias="Schwab-Paper", provider="TEST_STUB",
        as_of=when, total_equity=D(100000), cash=D(85000), holdings=(Holding(ticker="SPY", quantity=D(150), market_value=D(15000)),),
        sync_state=AccountSyncState.SYNCED, freshness_state=FreshnessState.VERIFIED)
    quotes = {s: MarketSnapshot(ticker=s, timestamp=when, last=D(100), previous_close=D(99),
        bid=None if missing_sell_bid and s == "SPY" else D("99.9"), ask=D("100.1"), volume=1000000,
        atr14=D(2), vwap=D(100), daily_return=D(".01"), freshness_state=FreshnessState.VERIFIED) for s in policies.universe.tickers}
    meta = tuple(QuantSecurityMetadata(symbol=s, asset_type="EQUITY", sector="SHARED_TEST" if s in {"AAPL", "SPY"} else s,
        known_at=when, source="ENGINEERING_METADATA_STUB") for s in policies.universe.tickers)
    original = packet_module.allocate_challenger
    def small_target(*args, **kwargs):
        from meridian.quant.portfolio import target_from_weights
        value = original(*args, **kwargs)
        return value.model_copy(update={"feasible_target": target_from_weights({"AAPL": D(".05"), "SPY": D(".05"), "MSFT": D(".1"), "NVDA": D(".1")}, when, p.version)})
    monkeypatch.setattr(packet_module, "allocate_challenger", small_target)
    result = build_research_packet(h, tuple(policies.universe.tickers), cutoff=when, policies=policies, policy=p,
        metadata=meta, account=snapshot, quotes=quotes)
    assert not result.eligible_hypothetical_drafts
    assert any("sector constraint violation" in r for r in result.constraint_modifications)
    assert all(row.eligible_change == 0 for row in result.symbols)


def test_cli_packet_never_constructs_canonical_application(tmp_path: Path, monkeypatch, capsys):
    import sys

    from meridian.application_cli import main
    d = synthetic_dataset()
    path = tmp_path / "dataset.json"
    path.write_text(d.stable_json(), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["meridian", "quant", "packet", "--dataset", str(path), "--cutoff", cutoff(d).isoformat(), "--diagnostic"])
    monkeypatch.setattr("meridian.application_cli.MeridianApplicationService", lambda *a, **k: pytest.fail("canonical service initialized"))
    assert main() == 0
    assert '"trade_authorized": false' in capsys.readouterr().out
