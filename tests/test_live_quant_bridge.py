"""Regression contracts using explicit fixtures; none is a real market run."""
from __future__ import annotations

import hashlib
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from meridian.audit import AuditStore
from meridian.config import load_policies
from meridian.daily_research import DailyResearchInput, PublicResearchObservation
from meridian.gpt_native_research import GPTNativeResearchOrchestrator
from meridian.historical import (
    HistoricalAdjustmentStatus,
    HistoricalBarCertification,
    HistoricalQuality,
)
from meridian.live_account import inspect_paper, read_only_ledger
from meridian.live_advisory import MarketDataFreshnessGate, market_row, render_report
from meridian.live_quant_bridge import (
    build_live_quant_snapshot,
    persist_live_quant,
)
from meridian.live_report import quant_research_rows
from meridian.paper import PaperLedger, PaperSettings
from meridian.quant.policy import ChallengerPolicy
from meridian.quotes import QuoteObservation
from tests.quant_helpers import cutoff, histories, synthetic_dataset

ROOT = Path(__file__).parents[1]


def fixture_inputs(*, raw=False, verified=False):
    data = synthetic_dataset()
    when = cutoff(data) + timedelta(seconds=30)
    history = {}
    for symbol, series in histories(data).items():
        bars = tuple(b.model_copy(update={'retrieved_at': when - timedelta(seconds=1),
            **({'adjustment_status': HistoricalAdjustmentStatus.RAW,
                'certification': HistoricalBarCertification.UNVERIFIED, 'quality': HistoricalQuality.UNVERIFIED} if raw else {}),
            **({'certification': HistoricalBarCertification.CERTIFIED_RESEARCH_PIT_ADJUSTED,
                'source': 'ENGINEERING_CERTIFICATION_CONTRACT_FIXTURE_NOT_MARKET'} if verified else {})})
            for b in series.bars if b.session <= data.series[0].bars[279].session)
        history[symbol] = series.model_copy(update={'bars': bars, 'as_of': when})
    quotes = {symbol: QuoteObservation(canonical_asset_id=series.canonical_asset_id,
        canonical_symbol=symbol, provider='FIXTURE_ONLY', provider_symbol=symbol,
        observed_at=when - timedelta(seconds=5), available_at=when - timedelta(seconds=5),
        retrieved_at=when - timedelta(seconds=1), last=series.bars[-1].close,
        previous_close=series.bars[-2].close, currency='USD', source='SYNTHETIC_NOT_TODAY')
        for symbol, series in history.items()}
    policies = load_policies(ROOT / 'policies')
    return data, when, history, quotes, policies


def snapshot(*, raw=False, verified=False, diagnostic=False):
    data, when, history, quotes, policies = fixture_inputs(raw=raw, verified=verified)
    return build_live_quant_snapshot(histories=history, quotes=quotes, cutoff=when,
        policies=policies, policy=ChallengerPolicy(), run_id='FIXTURE_ONLY',
        metadata=data.security_metadata, diagnostic=diagnostic)


def test_actual_v22_factors_and_attribution_reach_research_evidence():
    row = snapshot(diagnostic=True)
    assert row.quant_packet is not None
    assert row.quant_packet.symbols[0].feature.base.value('momentum_6m') is not None
    assert row.quant_packet.symbols[0].score is not None
    assert len(row.quant_packet.symbols[0].score.factor_attribution) == 6
    _, when, _, quotes, _ = fixture_inputs()
    q = quotes['AAPL']
    assert q.last is not None
    request = DailyResearchInput(parent_run_id='FIXTURE_ONLY', analysis_cutoff=when, mode='FIXTURE',
        snapshot_reference='NONE', market_reference='a'*64, policy_reference='b'*64,
        provider='fixture', model='fixture', freshness_status='PASS',
        observations=(PublicResearchObservation(ticker='AAPL', observed_at=q.observed_at,
            price=q.last, reference=hashlib.sha256(q.stable_json().encode()).hexdigest()),),
        market_context={'quant_live': row.model_dump(mode='json'), 'quant_live_hash': row.digest})
    evidence = GPTNativeResearchOrchestrator()._evidence(request)
    quant = next(e for e in evidence if e.source == 'V2.2_SHADOW' and e.symbol == 'AAPL')
    assert quant.structured_value is not None
    assert quant.structured_value['quant']['feature']['base']['factors']
    assert quant.structured_value['quant']['score']['factor_attribution']
    assert not row.financial_oos_evidence_eligible
    assert row.strict_status == 'INSUFFICIENT_VERIFIED_HISTORY'
    assert not any(e.source == 'DAILY_RETURN_ANALYTICS' for e in evidence)
    assert evidence[0].verification_status.value == 'UNVERIFIED'
    with pytest.raises(ValueError, match='CUTOFF_OR_HASH'):
        GPTNativeResearchOrchestrator()._evidence(request.model_copy(update={
            'market_context': {'quant_live': row.model_dump(mode='json'), 'quant_live_hash': '0'*64}}))


def test_public_raw_lane_has_partial_observations_never_scores_or_entry_prices():
    row = snapshot(raw=True)
    public = row.provisional_diagnostics['AAPL']
    assert public['status'] == 'PARTIAL_DIAGNOSTICS'
    assert public['completed_session_open_to_close'] is not None
    assert public['momentum'] is public['volatility'] is public['quant_rank'] is None
    assert public['historical_known_at'] is None
    assert row.quant_packet is not None
    assert row.quant_packet.data_certification_class == 'UNVERIFIED'
    assert row.price_conditions['AAPL']['quantitative_entry_zone'] is None
    assert not row.trade_authorized and not public['financial_oos_evidence_eligible']


@pytest.mark.parametrize('fault', ['missing_benchmark','future_quote','symbol_quote','stale_quote','order','future_retrieval','mixed_basis'])
def test_data_gaps_never_create_optimistic_ranking(fault):
    data, when, history, quotes, policies = fixture_inputs(raw=True)
    if fault == 'missing_benchmark':
        history.pop('SPY')
    elif fault in {'future_quote','symbol_quote','stale_quote'}:
        updates = {'available_at': when + timedelta(seconds=1)} if fault == 'future_quote' else {
            'canonical_symbol': 'MSFT'} if fault == 'symbol_quote' else {
            'observed_at': when - timedelta(hours=1), 'available_at': when - timedelta(hours=1)}
        quotes['AAPL'] = quotes['AAPL'].model_copy(update=updates)
    elif fault == 'order':
        history['AAPL'] = history['AAPL'].model_copy(update={'bars': tuple(reversed(history['AAPL'].bars))})
    else:
        first, *rest = history['AAPL'].bars
        updates = {'retrieved_at': when + timedelta(seconds=1)} if fault == 'future_retrieval' else {
            'adjustment_status': HistoricalAdjustmentStatus.ADJUSTED_CLOSE}
        history['AAPL'] = history['AAPL'].model_copy(update={'bars': (first.model_copy(update=updates), *rest)})
    row = build_live_quant_snapshot(histories=history, quotes=quotes, cutoff=when, policies=policies,
        policy=ChallengerPolicy(), run_id='FIXTURE_ONLY', metadata=data.security_metadata)
    assert row.strict_status == 'INSUFFICIENT_VERIFIED_HISTORY'
    assert row.price_conditions['AAPL']['quantitative_entry_zone'] is None
    if fault in {'future_quote','symbol_quote','stale_quote'}:
        assert 'AAPL' not in row.quote_hashes
        assert row.price_conditions['AAPL']['observed_price'] is None
    if fault in {'order','future_retrieval','mixed_basis'}:
        assert row.provisional_diagnostics['AAPL']['status'] == 'BLOCKED'


def test_verified_contract_fixture_reuses_engine_and_price_condition_math():
    row = snapshot(verified=True)
    assert row.strict_status == 'VERIFIED_RESEARCH_AVAILABLE'
    assert row.quant_packet is not None
    assert row.shadow_comparison is not None
    for symbol in row.quant_packet.symbols:
        assert symbol.score is not None
        assert len(symbol.score.factor_attribution) == 6
        if row.price_conditions[symbol.symbol]['quantitative_entry_zone']:
            low, high = map(Decimal, row.price_conditions[symbol.symbol]['quantitative_entry_zone'])
            assert 0 < low <= high
    assert not row.trade_authorized and not row.financial_oos_evidence_eligible


def test_immutable_comparison_is_sanitized_and_rejects_rewrites(tmp_path):
    row = snapshot(raw=True)
    path = persist_live_quant(row, tmp_path)
    assert persist_live_quant(row, tmp_path) == path
    assert 'AccountSnapshot' not in path.read_text(encoding='utf-8')
    from meridian.quant.integration import immutable_record
    with pytest.raises(ValueError, match='IMMUTABLE'):
        immutable_record(path, '{}')


def test_paper_read_does_not_migrate_reset_or_create_missing_account(tmp_path):
    db = tmp_path / 'state.sqlite'
    settings = PaperSettings()
    _, when, _, _, _ = fixture_inputs()
    assert not inspect_paper(db, settings, when)['ready']
    assert not db.exists()
    ledger = PaperLedger(AuditStore(db), settings)
    ledger.initialize()
    before = db.read_bytes()
    result = inspect_paper(db, settings, when)
    assert result['ready'] and result['ledger_version'] == 0
    assert result['recent_ownership'] == []
    assert db.read_bytes() == before
    with pytest.raises(Exception, match='readonly'):
        read_only_ledger(db, settings).reset('Schwab-Paper', confirmation='Schwab-Paper')
    assert db.read_bytes() == before


def test_failed_model_report_keeps_quant_and_chinese_gaps():
    row = snapshot(raw=True)
    _, when, _, quotes, _ = fixture_inputs(raw=True)
    report = {'run_id':'FIXTURE_ONLY', 'generated_at':when.isoformat(), 'market_session':'REGULAR',
        'checks': {'llm':'FAILED'}, 'blockers':['MODEL_TIMEOUT'], 'input_class':'FIXTURE_ONLY',
        'quant_live':row.model_dump(mode='json'), 'quant_live_hash':row.digest,
        'market_snapshot':{s:market_row(q,when) for s,q in quotes.items()}}
    rows = quant_research_rows(report)
    assert rows and all(r['decision_category'] == 'WAIT_FOR_EVIDENCE' for r in rows)
    assert all(r['quant_score'] is None and not r['trade_authorized'] for r in rows)
    text = render_report(report)
    assert 'MODEL_TIMEOUT' in text and 'V2.2_SHADOW' in text and 'UNKNOWN' in text
    assert '模型未完成' in text and row.digest in text


def test_stale_quote_has_only_dated_reference_and_future_availability_is_rejected():
    _, when, _, quotes, _ = fixture_inputs(raw=True)
    quote = quotes['AAPL'].model_copy(update={'observed_at':when-timedelta(days=1),
                                            'available_at':when-timedelta(days=1)})
    row = market_row(quote,when)
    assert row['current_price'] is None and row['reference_price'] is not None
    future = quotes['AAPL'].model_copy(update={'available_at':when+timedelta(seconds=1)})
    assert MarketDataFreshnessGate().evaluate(future,when)[0] == 'UNAVAILABLE'


def test_readiness_missing_ledger_never_calls_migrating_doctor(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import meridian.live_readiness as readiness
    from meridian.gpt_native_research import LiveModelPreflight
    from meridian.runtime import RuntimePaths

    monkeypatch.setattr(readiness,'MeridianApplicationService',lambda _:pytest.fail('Doctor must not create a database'))
    monkeypatch.setattr(readiness,'CodexResearchModelRuntime',lambda:SimpleNamespace(
        preflight=lambda _:LiveModelPreflight(status='READY',auth_usable=True,route_valid=True)))
    report = readiness.readiness_report(RuntimePaths(tmp_path),probe_providers=False,observation_class='FIXTURE_ONLY')
    assert report['conclusion'] == 'NO_GO'
    assert report['assessment_phase'] == 'FIXTURE_REGRESSION'
    assert report['model_inference'] == 'NOT_PROBED_LOGIN_ONLY'
    assert not report['regular_session_live_acceptance_complete']
    assert not (tmp_path/'db/meridian.sqlite3').exists()


def test_future_history_changes_do_not_change_earlier_quant_signal():
    data, when, history, quotes, policies = fixture_inputs(verified=True)
    args: dict[str, Any] = dict(quotes=quotes,cutoff=when,policies=policies,policy=ChallengerPolicy(),run_id='FIXTURE_ONLY')
    before = build_live_quant_snapshot(histories=history,**args)
    future = data.series[0].bars[280].model_copy(update={'certification':HistoricalBarCertification.CERTIFIED_RESEARCH_PIT_ADJUSTED})
    history['AAPL'] = history['AAPL'].model_copy(update={'bars':(*history['AAPL'].bars,future)})
    after = build_live_quant_snapshot(histories=history,**args)
    assert before.quant_packet is not None and after.quant_packet is not None
    assert [r.score for r in before.quant_packet.symbols] == [r.score for r in after.quant_packet.symbols]


@pytest.mark.parametrize('fault', [None, 'timeout', 'score_overwrite'])
def test_full_fixture_pipeline_passes_quant_to_both_gpt_stages_and_preserves_scores(tmp_path, monkeypatch, fault):
    from datetime import datetime
    from types import SimpleNamespace

    from test_gpt_native_research import outputs

    import meridian.live_advisory as live
    from meridian.gpt_native_research import (
        FakeResearchModelRuntime,
        InvocationStatus,
        LiveModelPreflight,
        ModelInvocationResult,
    )
    from meridian.host_readiness import ReadinessStatus
    from meridian.runtime import RuntimePaths
    from meridian.schemas import AccountSnapshot
    from meridian.trading_calendar import is_trading_session

    _, initial, history, quotes, _ = fixture_inputs(verified=True)
    when = initial + timedelta(days=1, hours=-5)
    while not is_trading_session(when):
        when += timedelta(days=1)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return when.astimezone(tz) if tz else when.replace(tzinfo=None)

    class Provider:
        def get_quote(self, symbol):
            return quotes[symbol].model_copy(update={'observed_at':when-timedelta(seconds=5),
                'available_at':when-timedelta(seconds=5), 'retrieved_at':when-timedelta(seconds=1)})

    calls = []

    class Runtime(FakeResearchModelRuntime):
        def __init__(self):
            super().__init__({})
        def preflight(self, routes):
            return LiveModelPreflight(status='READY', auth_usable=True, route_valid=True)
        def invoke(self, role, input_data, schema, budget_seconds, *, model, reasoning_effort):
            calls.append(role)
            if role == 'PRIMARY_ANALYST':
                supplied = input_data['market_context']['quant_live']
                assert supplied['quant_packet']['symbols'][0]['score']['factor_attribution']
                assert any(e['source'] == 'V2.2_SHADOW' for e in input_data['evidence'])
                if fault == 'timeout':
                    return ModelInvocationResult(status=InvocationStatus.TIMEOUT, error_type='FIXTURE_TIMEOUT')
            if role == 'SYMBOL_ADVISORY':
                assert input_data['quant_live']['strict_status'] == 'VERIFIED_RESEARCH_AVAILABLE'
                decisions = [{'symbol':s,'action':'WAIT','confidence':0.5,'time_horizon':'FIXTURE_ONLY',
                    'thesis':'根据提供的定量字段等待验证，不推断新闻。','positive_drivers':[],
                    'negative_drivers':['证据不足'],'risk_flags':['FIXTURE_ONLY'],'wait_until':'等待新的可信数据',
                    'evidence_ids':[ref,input_data['quant_evidence_ids'][s]]}
                    for s,ref in input_data['evidence_ids'].items()]
                value: dict[str, Any] = {'decisions':decisions, 'top_action_now':'等待', 'avoid_now':'未验证的入场',
                         'doing_nothing_assessment':'等待证据'}
                if fault == 'score_overwrite':
                    value['decisions'][0]['quant_score'] = 1
                # A model-side mutation cannot alter the saved deterministic report.
                input_data['quant_live']['quant_packet']['symbols'][0]['score']['signal_strength'] = '999'
            else:
                value = outputs()[role]
                evidence = input_data['evidence'][0]['evidence_id']
                if role == 'PRIMARY_ANALYST':
                    value['evidence_used'] = [evidence]
                    value['supporting_claims'][0]['supporting_evidence_ids'] = [evidence]
                elif role == 'DECISION_SYNTHESIS':
                    value['key_support'] = [evidence]
            return ModelInvocationResult(status=InvocationStatus.SUCCESS, output=value)

    account = AccountSnapshot(snapshot_id='FIXTURE_ONLY',account_alias='Schwab-Paper',provider='FIXTURE_ONLY',
        as_of=when,total_equity=100000,cash=100000,sync_state='SYNCED',freshness_state='VERIFIED')
    monkeypatch.setattr(live,'datetime',Clock)
    monkeypatch.setattr(live,'YahooChartQuoteProvider',lambda *a,**kw:Provider())
    monkeypatch.setattr(live,'collect_live_features',lambda *a,**kw:{'status':'PASS','features':{},'_series':history})
    monkeypatch.setattr(live,'CodexResearchModelRuntime',Runtime)
    monkeypatch.setattr(live,'inspect_snapshot',lambda *a,**kw:(SimpleNamespace(status=ReadinessStatus.PASS),account))
    report = live.LiveAdvisoryService(RuntimePaths(tmp_path)).run(snapshot_path=tmp_path/'FIXTURE_ONLY.json')
    from meridian.live_quant_bridge import LiveQuantSnapshot
    sealed = LiveQuantSnapshot.model_validate(report['quant_live'])
    assert sealed.digest == report['quant_live_hash']
    assert sealed.quant_packet is not None
    assert all(r.score and r.score.signal_strength <= 1 for r in sealed.quant_packet.symbols)
    assert Path(report['quant_evidence_path']).is_file()
    assert report['decision_provenance']['operational']['canonical_orders_changed'] is False
    assert not (tmp_path/'db/meridian.sqlite3').exists()
    if fault is None:
        assert report['checks']['advisory'] == 'PASS' and 'SYMBOL_ADVISORY' in calls
        assert report['quant_research_rows'][0]['factor_attribution']
    else:
        assert not report['LIVE_RUN_READY'] and report['blockers']
    assert report['ORDER_AUTHORITY'] == 'NONE'
