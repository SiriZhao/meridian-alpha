"""Isolated fixture acceptance; no real data, model acceptance, account or fills."""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from meridian import mcp_server
from meridian.daily_research import DailyResearchInput, PublicResearchObservation
from meridian.decision_brief import generate_decision_brief, render_decision_brief
from meridian.gpt_native_research import (
    FakeResearchModelRuntime,
    InvocationStatus,
    ModelInvocationResult,
)
from meridian.historical import HistoricalBarCertification
from meridian.research_order_review import PaperReviewRequest, plan_paper_review
from meridian.research_recommendations import build_recommendations
from meridian.research_terminal import (
    HypotheticalWeight,
    PortfolioWhatIfRequest,
    QuantTerminalRequest,
)
from meridian.schemas import AccountSnapshot, FreshnessState, Holding, MarketSnapshot
from meridian.terminal_service import TerminalPlanner, review_terminal, terminal_model_context
from tests.quant_helpers import cutoff, synthetic_dataset
from tests.test_gate6f_manual_authority import _quote
from tests.test_gpt_native_research import outputs, settings

D = Decimal
ROOT = Path(__file__).parents[1]


def quant_request(*, verified=False, regular=False):
    data = synthetic_dataset()
    when = cutoff(data) + (timedelta(hours=19) if regular else timedelta())
    series = tuple(s for s in data.series if s.canonical_symbol in {'AAPL', 'MSFT', 'NVDA', 'SPY'})
    # Seal decimal input precision before hashing. libm sin/cos used by the
    # shared synthetic generator has platform-specific binary float tail bits.
    # This fixture contract is independent of the frozen experiment generator.
    series = tuple(s.model_copy(update={'bars': tuple(b.model_copy(update={
        name: getattr(b, name).quantize(D('.00000001'))
        for name in ('open', 'high', 'low', 'close')}) for b in s.bars)}) for s in series)
    if verified:
        series = tuple(s.model_copy(update={'bars': tuple(b.model_copy(update={
            'certification': HistoricalBarCertification.CERTIFIED_RESEARCH_PIT_ADJUSTED,
            'source': 'QUALIFIED_CONTRACT_FIXTURE_NOT_FINANCIAL_EVIDENCE'}) for b in s.bars)}) for s in series)
    return QuantTerminalRequest(engine='V2.3_SHADOW', analysis_cutoff=when, symbols=('AAPL', 'MSFT', 'NVDA'),
        histories=series, metadata=tuple(m for m in data.security_metadata if m.symbol in {'AAPL', 'MSFT', 'NVDA', 'SPY'}), diagnostic=not verified)


def research_input(request, *, stale=False):
    observations = []
    for i, s in enumerate(request.symbols):
        history = next(h for h in request.histories if h.canonical_symbol == s)
        last = [b for b in history.bars if b.available_at <= request.analysis_cutoff][-1]
        observations.append(PublicResearchObservation(ticker=s, price=last.close,
            observed_at=request.analysis_cutoff - timedelta(seconds=3600 if stale else 5), reference=f'{i+1:064x}'))
    return DailyResearchInput(parent_run_id='FIXTURE_ONLY', analysis_cutoff=request.analysis_cutoff,
        mode='FIXTURE', snapshot_reference='NO_ACCOUNT', market_reference='a'*64, policy_reference='b'*64,
        provider='FIXTURE_ONLY', model='FIXTURE_ONLY', observations=tuple(observations),
        provider_provenance={s:'ENGINEERING_FIXTURE_NOT_REAL_PRICE' for s in request.symbols}, freshness_status='PASS')


def paper_account(when, *, cash: Decimal | int = 100000, holdings=()):
    return AccountSnapshot(snapshot_id='ISOLATED_FIXTURE', account_alias='Schwab-Paper', provider='FIXTURE_ONLY',
        as_of=when, cash=cash, total_equity=cash + sum((h.market_value for h in holdings), D(0)), holdings=holdings,
        freshness_state='VERIFIED', sync_state='SYNCED')


def planner_quotes(request):
    base, certificate = _quote()
    cert = certificate.model_copy(update={'certified_at':request.analysis_cutoff - timedelta(days=1),
        'valid_from':request.analysis_cutoff - timedelta(days=1), 'valid_to':request.analysis_cutoff + timedelta(days=1),
        'symbol_scope':request.symbols, 'capability_hash':None})
    cert = cert.model_copy(update={'capability_hash':cert.computed_capability_hash})
    result = []
    market = {}
    for s in request.symbols:
        last = next(h for h in request.histories if h.canonical_symbol == s).bars[279].close.quantize(D('.0001'))
        q = base.model_copy(update={'symbol':s, 'provider_symbol':s, 'last':last, 'bid':last-D('.01'), 'ask':last+D('.01'),
            'timestamp':request.analysis_cutoff, 'retrieved_at':request.analysis_cutoff, 'available_at':request.analysis_cutoff})
        result.append(q)
        market[s] = MarketSnapshot(ticker=s, timestamp=q.timestamp, last=q.last, bid=q.bid, ask=q.ask,
            previous_close=q.last, volume=1000000, atr14=D('.5'), vwap=q.last, daily_return=D(0), freshness_state=FreshnessState.VERIFIED)
    return tuple(result), (cert,), market


def test_v23_actual_packet_candidates_prices_and_no_account():
    req = quant_request(verified=True)
    terminal = TerminalPlanner().build(req)
    decision = generate_decision_brief(terminal, request=research_input(req))
    assert terminal.quant.flagship and terminal.quant.flagship.engine_hash == terminal.quant.engine_hash
    assert any(r.category == 'ACCUMULATE_CONDITIONALLY' for r in decision.recommendations)
    for r in decision.recommendations:
        assert r.current_weight is None and r.actual_eligible_change is None and not r.order_authorized
        assert r.factor_attribution and r.price_plan
        assert r.company_name is None and r.company_name_source is None  # Existing master has no verified names.
        p = r.price_plan
        assert (p.lower, p.upper) == (p.measurement['sma20']-p.measurement['atr14']/2, p.measurement['sma20']+p.measurement['atr14']/2)
        assert p.executable_limit is None and p.quote_evidence_id in r.evidence_ids
        assert r.cost_assumptions['monetary_cost'] is None
    text = render_decision_brief(decision)
    assert '下一步' in text and 'ATR14' in text and '当前没有账户' in text


def test_stale_price_with_account_preserves_quant_not_price_claim():
    req = quant_request(verified=True)
    portfolio = PortfolioWhatIfRequest(analysis_cutoff=req.analysis_cutoff, account=paper_account(req.analysis_cutoff), desired=(), metadata=req.metadata)
    terminal = TerminalPlanner().build(req, portfolio=portfolio)
    decision = generate_decision_brief(terminal, request=research_input(req, stale=True))
    assert not decision.observed_facts
    assert any(r.score is not None for r in decision.recommendations)
    assert all(r.price_plan is None and r.observed_reference is None and r.current_weight == 0 for r in decision.recommendations)
    assert decision.execution_authority == 'NONE'


@pytest.mark.parametrize('gap', ['benchmark', 'all', 'short_history'])
def test_concrete_evidence_gap_diagnostics(gap):
    req = quant_request(verified=True)
    histories = () if gap == 'all' else tuple(h for h in req.histories if h.canonical_symbol != 'SPY') if gap == 'benchmark' else tuple(
        h.model_copy(update={'bars': h.bars[:10]}) for h in req.histories)
    brief = TerminalPlanner().build(req.model_copy(update={'histories':histories}))
    decision = generate_decision_brief(brief)
    assert decision.recommendations and all(r.rank is None for r in decision.recommendations)
    assert all(r.category == 'WAIT_FOR_EVIDENCE' and r.next_inputs and r.reasons for r in decision.recommendations)
    assert 'SPY' in render_decision_brief(decision)


def test_qualified_no_signal_has_auditable_no_action():
    req = quant_request(verified=True)
    changed = []
    for history in req.histories:
        bars = tuple(b.model_copy(update={'open':D(100)-D(i)/10, 'close':D(100)-D(i)/10,
            'high':D(101)-D(i)/10, 'low':D(99)-D(i)/10}) for i,b in enumerate(history.bars))
        changed.append(history.model_copy(update={'bars':bars}))
    result = generate_decision_brief(TerminalPlanner().build(req.model_copy(update={'histories':tuple(changed)})))
    assert all(r.category == 'NO_ACTION' and r.reasons for r in result.recommendations)
    assert result.possible_manual_action is None


@pytest.mark.parametrize('failure', [None, InvocationStatus.TIMEOUT, InvocationStatus.RATE_LIMITED])
def test_native_four_roles_conflict_failure_and_trace(failure):
    req = quant_request()
    terminal = TerminalPlanner().build(req)
    original = terminal.quant.stable_json()
    identity = terminal.quant.rows[0].evidence_id
    values = json.loads(json.dumps(outputs()).replace('a'*64, identity))
    values['PRIMARY_ANALYST']['direction'] = 'BEARISH'
    chain = dict(primary=values['PRIMARY_ANALYST'], skeptic=values['SKEPTIC'], scenarios=values['SCENARIO_ANALYSIS'], synthesis=values['DECISION_SYNTHESIS'])

    class Runtime(FakeResearchModelRuntime):
        def invoke_chain(self, input_data, budget_seconds, *, model, reasoning_effort):
            self.calls.append(('RESEARCH_CHAIN', budget_seconds))
            evidence = next(e for e in input_data['evidence'] if e['source'] == 'V2.3_SHADOW_TERMINAL')
            assert evidence['structured_value']['portfolio_assumption'] == 'NO_ACCOUNT_NORMALIZED_RESEARCH'
            assert 'feasible_weight' in evidence['structured_value']
            return ModelInvocationResult(status=failure or InvocationStatus.SUCCESS, output=None if failure else chain,
                model='FIXTURE_ONLY', diagnostic={'shared_invocation_id':'FIXTURE_SHARED_CALL'}, duration_ms=20)

    runtime = Runtime({})
    research = research_input(req)
    native = review_terminal(terminal, research, settings(), runtime)
    result = generate_decision_brief(terminal, request=research, model_result=native)
    assert terminal.quant.stable_json() == original and len(runtime.calls) == 1
    assert result.model_trace and result.model_trace['actual_model_call_verified'] is False
    assert result.model_trace['input_view_hash'] == terminal_model_context(terminal.quant)['quant_terminal_view_hash']
    assert any(r.score is not None for r in result.recommendations)
    assert not any(r.order_authorized for r in result.recommendations)
    if failure:
        assert result.gpt_interpretation is not None
        assert native.missing_stages and result.gpt_interpretation['primary'] is None
        assert any('GPT_INCOMPLETE_QUANT_PRESERVED' in r.reasons for r in result.recommendations)
    else:
        assert result.conditional_forecast is not None
        assert any(r.quant_gpt_conflict for r in result.recommendations)
        assert result.conditional_forecast['probabilities'] is None
    forged = native.model_copy(update={'evidence': ()})
    with pytest.raises(ValueError, match='EVIDENCE'):
        build_recommendations(terminal.quant, model_result=forged)


@pytest.mark.parametrize('fault', ['account_missing', 'stale_price', 'cash_insufficient', 'market_closed', 'risk_failure', 'unverified_history'])
def test_isolated_paper_planning_gates_no_ledger(tmp_path, monkeypatch, fault):
    monkeypatch.setenv('MERIDIAN_HOME', str(tmp_path/'not-created'))
    req = quant_request(verified=fault != 'unverified_history', regular=fault != 'market_closed')
    account = None if fault == 'account_missing' else paper_account(req.analysis_cutoff)
    quotes, certificates, market = planner_quotes(req)
    if fault == 'stale_price':
        quotes = tuple(q.model_copy(update={'timestamp':q.timestamp-timedelta(hours=1)}) for q in quotes)
    elif fault == 'cash_insufficient':
        account = paper_account(req.analysis_cutoff, cash=D('.01'))
    elif fault == 'risk_failure':
        req = req.model_copy(update={'metadata':()})
    result = plan_paper_review(req, account=account, quotes=market, execution_quotes=quotes, certificates=certificates)
    assert result.state in {'BLOCKED','PAPER_ONLY'} and not result.paper_drafts
    assert result.blockers and result.manual_blockers and result.execution_authority == 'NONE'
    assert result.fills == () and not (tmp_path/'not-created').exists()


def test_existing_risk_reconciliation_order_planner_produce_paper_only():
    req = quant_request(verified=True, regular=True)
    quotes, certificates, market = planner_quotes(req)
    result = plan_paper_review(req, account=paper_account(req.analysis_cutoff), quotes=market,
        execution_quotes=quotes, certificates=certificates)
    assert result.state == 'PAPER_ONLY' and result.planning_status == 'DRAFTS_AVAILABLE'
    assert result.paper_drafts and all(d.quantity == d.quantity.to_integral() for d in result.paper_drafts)
    assert result.limit_source == 'EXISTING_ORDER_PLANNER_NOT_RESEARCH_ZONE'
    assert result.manual_blockers and not result.fills


def test_paper_contract_reaches_mcp_decision_and_cli_without_account_echo(tmp_path, capsys):
    req = quant_request(verified=True, regular=True)
    quotes, certificates, market = planner_quotes(req)
    account = paper_account(req.analysis_cutoff)
    review = PaperReviewRequest(quant=req, account=account, planner_quotes=tuple(market.values()), execution_quotes=quotes, certificates=certificates)
    assert 'account' not in review.model_dump() and 'account' not in repr(review)
    ticket = mcp_server.research_paper_plan(review)
    brief = generate_decision_brief(TerminalPlanner().build(req), paper_review=ticket)
    assert brief.manual_ticket and brief.manual_ticket.paper_drafts
    assert brief.execution_authority == 'NONE' and brief.possible_manual_action is None
    stale_identity = ticket.model_copy(update={'request_hash':'0'*64})
    with pytest.raises(ValueError, match='INPUT_MISMATCH'):
        generate_decision_brief(TerminalPlanner().build(req), paper_review=stale_identity)
    from meridian.terminal_cli import main
    quant_file, review_file = tmp_path/'quant.json', tmp_path/'review.json'
    quant_file.write_text(req.model_dump_json(), encoding='utf-8')
    review_file.write_text(json.dumps({**review.model_dump(mode='json'), 'account':account.model_dump(mode='json')}), encoding='utf-8')
    assert main([str(quant_file),'--paper-review',str(review_file),'--json']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['manual_ticket']['state'] == 'PAPER_ONLY' and result['manual_ticket']['paper_drafts']
    assert 'cash' not in result['risk_constraints'] and result['execution_authority'] == 'NONE'


def test_raw_public_partial_diagnostics_never_become_v23_signal():
    from tests.test_live_quant_bridge import fixture_inputs
    data, when, history, _, _ = fixture_inputs(raw=True)
    req = QuantTerminalRequest(engine='V2.3_SHADOW', analysis_cutoff=when, symbols=('AAPL','MSFT','NVDA'),
        histories=tuple(h for s,h in history.items() if s in {'AAPL','MSFT','NVDA','SPY'}), metadata=data.security_metadata)
    result = generate_decision_brief(TerminalPlanner().build(req))
    assert all(r.score is None and r.rank is None and r.state == 'BLOCKED' for r in result.recommendations)
    assert all(r.public_diagnostics['status'] == 'PARTIAL_DIAGNOSTICS' for r in result.recommendations)
    assert all(r.public_diagnostics['historical_known_at'] is None and not r.public_diagnostics['financial_oos_evidence_eligible'] for r in result.recommendations)


def test_unqualified_history_still_supplies_public_observation_to_four_roles():
    req = quant_request().model_copy(update={'histories':()})
    base = research_input(quant_request())
    terminal = TerminalPlanner().build(req)
    result = review_terminal(terminal, base, settings(), FakeResearchModelRuntime({}))
    assert result.missing_stages
    decision = generate_decision_brief(terminal, request=base, model_result=result)
    assert decision.recommendations[0].observed_reference
    assert all(r.category == 'WAIT_FOR_EVIDENCE' and not r.order_authorized for r in decision.recommendations)


def test_holdings_vs_shadow_target_trim_not_model_sell():
    req = quant_request(verified=True)
    holding = Holding(ticker='AAPL', quantity=D(400), market_value=D(40000))
    account = paper_account(req.analysis_cutoff, cash=D(60000), holdings=(holding,))
    portfolio = PortfolioWhatIfRequest(analysis_cutoff=req.analysis_cutoff, account=account,
        desired=(HypotheticalWeight(symbol='AAPL', weight=D('.1')),), metadata=req.metadata)
    result = generate_decision_brief(TerminalPlanner().build(req, portfolio=portfolio))
    row = next(r for r in result.recommendations if r.symbol == 'AAPL')
    assert row.category == 'TRIM_CANDIDATE' and row.current_weight == D('.4')
    assert 'CURRENT_EXPOSURE_ABOVE_SHADOW_TARGET' in row.reasons and not row.order_authorized


def test_mcp_and_cli_actual_v23_decision_no_runtime(tmp_path, monkeypatch, capsys):
    req = quant_request()
    research = research_input(req)
    result = mcp_server.decision_research_brief(req, research)
    assert result.recommendations[0].engine == 'V2.3_SHADOW'
    tools = {t.name:t for t in asyncio.run(mcp_server.mcp.list_tools())}
    tool = tools['decision_research_brief']
    assert tool.outputSchema and tool.annotations and tool.annotations.readOnlyHint
    from meridian.terminal_cli import main
    source, evidence = tmp_path/'quant.json', tmp_path/'research.json'
    source.write_text(req.model_dump_json(), encoding='utf-8')
    evidence.write_text(research.model_dump_json(), encoding='utf-8')
    monkeypatch.setenv('MERIDIAN_HOME', str(tmp_path/'not-created'))
    assert main([str(source), '--research-input', str(evidence), '--json']) == 0
    output = json.loads(capsys.readouterr().out)
    assert output['recommendations'][0]['engine'] == 'V2.3_SHADOW'
    assert output['model_trace'] is None and not (tmp_path/'not-created').exists()


def test_golden_report_quant_repeatability():
    req = quant_request()
    first = generate_decision_brief(TerminalPlanner().build(req), request=research_input(req))
    second = generate_decision_brief(TerminalPlanner().build(req), request=research_input(req))
    assert first.stable_json() == second.stable_json()
    expected = json.loads((ROOT/'docs/decision-integration/golden-decision.json').read_text(encoding='utf-8'))
    assert first.model_dump(mode='json') == expected


@pytest.mark.parametrize('fault', [None, 'quota', 'forged_price'])
def test_actual_v23_live_service_report_and_model_grounding(tmp_path, monkeypatch, fault):
    from datetime import datetime
    from types import SimpleNamespace

    import meridian.live_advisory as live
    from meridian.gpt_native_research import LiveModelPreflight
    from meridian.host_readiness import ReadinessStatus
    from meridian.runtime import RuntimePaths
    from tests.test_live_quant_bridge import fixture_inputs

    _, initial, history, quotes, _ = fixture_inputs(verified=True)
    when = initial + timedelta(hours=19)

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
                assert input_data['market_context']['quant_live']['flagship']['engine_hash']
                assert any(e['source'] == 'V2.3_SHADOW' for e in input_data['evidence'])
                authoritative = {s['bridge']['symbol']:s for s in input_data['market_context']['quant_live']['flagship']['scores']}
                for evidence in input_data['evidence']:
                    if evidence['source'] == 'V2.3_SHADOW':
                        assert evidence['structured_value']['quant']['score'] == authoritative.get(evidence['symbol'])
                if fault == 'quota':
                    return ModelInvocationResult(status=InvocationStatus.RATE_LIMITED, error_type='FIXTURE_QUOTA_EXHAUSTED')
            if role == 'SYMBOL_ADVISORY':
                assert input_data['quant_live']['flagship']['allocation']['version'] == 'quant-allocation-v2.3'
                value = {'decisions':[{'symbol':s,'action':'BUY','confidence':.5,'time_horizon':'FIXTURE_ONLY',
                    'thesis':'模型看多，但仍须依据确定性证据独立判断。' if fault != 'forged_price' else '确定公允价值为 999999。',
                    'positive_drivers':[],'negative_drivers':['新闻和估值尚未知'],'risk_flags':['FIXTURE_ONLY'],
                    'evidence_ids':[ref,input_data['quant_evidence_ids'][s]]} for s,ref in input_data['evidence_ids'].items()],
                    'top_action_now':'复核证据', 'avoid_now':'未验证的下单', 'doing_nothing_assessment':'等待是可用选择'}
            else:
                value = json.loads(json.dumps(outputs()[role]))
                identity = input_data['evidence'][0]['evidence_id']
                if role == 'PRIMARY_ANALYST':
                    value['evidence_used'] = [identity]
                    value['supporting_claims'][0]['supporting_evidence_ids'] = [identity]
                elif role == 'DECISION_SYNTHESIS':
                    value['key_support'] = [identity]
            return ModelInvocationResult(status=InvocationStatus.SUCCESS, output=value, model='FIXTURE_ONLY')

    monkeypatch.setattr(live,'datetime',Clock)
    monkeypatch.setattr(live,'YahooChartQuoteProvider',lambda *a,**k:Provider())
    monkeypatch.setattr(live,'collect_live_features',lambda *a,**k:{'status':'PASS','features':{},'_series':history})
    monkeypatch.setattr(live,'CodexResearchModelRuntime',Runtime)
    monkeypatch.setattr(live,'inspect_snapshot',lambda *a,**k:(SimpleNamespace(status=ReadinessStatus.PASS),paper_account(when)))
    report = live.LiveAdvisoryService(RuntimePaths(tmp_path),quant_engine='V2.3_SHADOW').run(snapshot_path=tmp_path/'FIXTURE_ONLY.json')
    assert report['quant_live']['flagship'] and report['research_recommendations']
    assert all(r['engine'] == 'V2.3_SHADOW' for r in report['research_recommendations'])
    assert not (tmp_path/'db/meridian.sqlite3').exists() and report['ORDER_AUTHORITY'] == 'NONE'
    assert report['quant_live']['shadow_comparison']['engine_hash'] == report['quant_live']['flagship']['engine_hash']
    authoritative = {s['bridge']['symbol']:s['bridge']['quant_score'] for s in report['quant_live']['flagship']['scores']}
    assert all(r['new_quant_score'] == authoritative.get(r['symbol']) for r in report['quant_live']['shadow_comparison']['symbols'])
    assert all(r['quant_score'] == authoritative.get(r['symbol']) for r in report['quant_research_rows'] if r['quant_rank'] is not None)
    assert Path(report['report_markdown']).is_file()
    if fault:
        assert report['blockers'] and report['decision_provenance']['gpt']['status'] != 'COMPLETE'
    else:
        assert report['checks']['advisory'] == 'PASS'
        assert all(d['decision_category'] == d['deterministic_recommendation']['category'] for d in report['decisions'])
        assert all('V2.3_SHADOW' in d['position_guidance'] for d in report['decisions'])
        assert next(r for r in report['research_recommendations'] if r['symbol'] == 'SPY')['rank'] is None
