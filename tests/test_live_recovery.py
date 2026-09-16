from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import ValidationError

from meridian.codex_schema import evidence_bound_schema, strict_output_schema
from meridian.gpt_native_research import (
    CodexResearchModelRuntime,
    FakeResearchModelRuntime,
    GPTNativeResearchOrchestrator,
    InvocationStatus,
    LiveModelPreflight,
    ModelInvocationResult,
    PrimaryAnalystOutput,
)
from meridian.live_advisory import (
    AdvisoryDecision,
    AdvisoryThesis,
    LiveAdvisoryService,
    MarketDataFreshnessGate,
    fetch_current_quotes,
    finalize_acceptance,
    market_row,
    render_report,
)
from meridian.quotes import MarketQuoteProvider, QuoteObservation
from meridian.runtime import RuntimePaths
from meridian.runtime_io import (
    FilesystemFailure,
    atomic_write,
    process_start_time,
    research_temporary_directory,
    run_lock,
    write_probe,
)
from meridian.trading_calendar import session_context


def test_runtime_root_resolution(tmp_path):
    explicit = RuntimePaths.from_environment({'MERIDIAN_HOME':str(tmp_path), 'LOCALAPPDATA':'C:/ignored'}, platform='win32')
    assert explicit.home == tmp_path
    assert RuntimePaths.from_environment({'LOCALAPPDATA':'C:/local'}, platform='win32').home == Path('C:/local/MeridianAlpha')
    with pytest.raises(RuntimeError):
        RuntimePaths.from_environment({'MERIDIAN_HOME':'relative'}, platform='win32')


def test_runtime_write_probe(tmp_path, monkeypatch):
    write_probe(tmp_path)
    assert not list(tmp_path.iterdir())
    def fail(*args):
        raise OSError(18, 'cross device')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(FilesystemFailure) as error:
        write_probe(tmp_path)
    assert error.value.detail['operation'] == 'ATOMIC_RENAME'
    assert error.value.detail['errno'] == 18
    assert error.value.__cause__ is not None
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('pid,start', [(99999999, '0'), (os.getpid(), 'previous-process')])
def test_stale_lock_recovery(tmp_path, pid, start):
    metadata = tmp_path/'production.lock'
    metadata.write_text(json.dumps({'pid':pid,'process_start_time':start,'hostname':socket.gethostname()}))
    with run_lock(tmp_path,'new-run'):
        assert json.loads(metadata.read_text())['run_id'] == 'new-run'
    assert not metadata.exists()


def test_live_lock_rejects_duplicate_process(tmp_path):
    with run_lock(tmp_path,'parent'):
        code = 'from meridian.runtime_io import run_lock; from pathlib import Path; import sys\nwith run_lock(Path(sys.argv[1]),"child"): pass'
        child = subprocess.run([sys.executable,'-c',code,str(tmp_path)],capture_output=True,text=True,check=False)
        assert child.returncode != 0
        assert 'LOCK_ACTIVE_DUPLICATE_PROCESS' in child.stderr
    with run_lock(tmp_path,'again'):
        assert process_start_time(os.getpid())


def test_lock_released_after_exception(tmp_path):
    with pytest.raises(ValueError), run_lock(tmp_path,'failed'):
        raise ValueError('simulated')
    with run_lock(tmp_path,'recovered'):
        pass


def test_process_crash_lock_recovery(tmp_path):
    code = ('from meridian.runtime_io import run_lock; from pathlib import Path; import sys,os\n'
            'with run_lock(Path(sys.argv[1]),"crashed"): os._exit(7)')
    child = subprocess.run([sys.executable,'-c',code,str(tmp_path)],check=False)
    assert child.returncode == 7
    assert (tmp_path/'production.lock').exists()
    with run_lock(tmp_path,'restarted'):
        assert json.loads((tmp_path/'production.lock').read_text())['run_id'] == 'restarted'


def test_atomic_file_write(tmp_path, monkeypatch):
    path = tmp_path/'state.json'
    atomic_write(path,'original')
    def fail(*args):
        raise PermissionError(13, 'locked')
    monkeypatch.setattr(os, 'replace', fail)
    with pytest.raises(FilesystemFailure):
        atomic_write(path,'replacement')
    assert path.read_text() == 'original'
    assert list(tmp_path.iterdir()) == [path]


def test_windows_safe_temp_cleanup(tmp_path, monkeypatch):
    monkeypatch.setenv('MERIDIAN_HOME',str(tmp_path))
    with research_temporary_directory() as one, research_temporary_directory() as two:
        assert one != two
        assert Path(one).parent == tmp_path/'tmp'
        with (Path(one)/'research.json').open('w') as handle:
            handle.write('{}')
    assert not Path(one).exists() and not Path(two).exists()


NOW = datetime(2026,9,14,14,0,tzinfo=UTC)


def quote(age=5, delay=None):
    return QuoteObservation(canonical_asset_id='us:AAPL',canonical_symbol='AAPL',provider='test',provider_symbol='AAPL',
            observed_at=NOW-timedelta(seconds=age),available_at=NOW-timedelta(seconds=age),retrieved_at=NOW,
            last=Decimal(100),currency='USD',source='unit-test-not-live',delay_seconds=delay)


def test_market_data_freshness():
    gate = MarketDataFreshnessGate()
    assert gate.evaluate(quote(),NOW)[0] == 'LIVE'
    assert gate.evaluate(quote(),NOW,cached=True)[0] == 'STALE'
    assert gate.evaluate(quote(age=91),NOW)[0] == 'STALE'
    assert gate.evaluate(quote(age=901,delay=900),NOW)[0] == 'DELAYED'
    assert gate.evaluate(quote(age=1000,delay=900),NOW)[0] == 'STALE'
    assert gate.evaluate(None,NOW)[0] == 'UNAVAILABLE'
    future = quote().model_copy(update={'observed_at':NOW+timedelta(seconds=1)})
    assert gate.evaluate(future,NOW)[0] == 'UNAVAILABLE'
    row = market_row(quote(),NOW)
    assert row['bid'] is None and row['missing_reasons']['bid'] == 'PROVIDER_FIELD_UNAVAILABLE'


@pytest.mark.parametrize('now,expected',[(NOW,'REGULAR'),(datetime(2026,1,5,14,0,tzinfo=UTC),'PRE_MARKET'),
    (datetime(2026,7,6,14,0,tzinfo=UTC),'REGULAR'),(datetime(2026,9,13,14,0,tzinfo=UTC),'CLOSED')])
def test_market_session_timezone(now,expected):
    assert session_context(now) == expected


def thesis():
    return dict(symbol='AAPL',action='WAIT',confidence=.4,time_horizon='intraday',thesis='Insufficient volume evidence',
                positive_drivers=[],negative_drivers=[],risk_flags=[],wait_until='Wait for current volume confirmation',evidence_ids=['e1'])


def test_advisory_schema():
    assert AdvisoryThesis.model_validate(thesis()).action == 'WAIT'
    with pytest.raises(ValidationError):
        AdvisoryThesis.model_validate({**thesis(),'wait_until':None})
    with pytest.raises(ValidationError):
        AdvisoryThesis.model_validate({**thesis(),'confidence':1.1})


def test_advisory_without_execution_authority():
    values = {**thesis(), 'market_context':'NEUTRAL','current_price':100,'suggested_entry':None,'suggested_limit_zone':None,
              'invalidation_level':None,'position_guidance':'Manual review','portfolio_impact':'No order',
              'data_as_of':NOW,'data_freshness':'LIVE','reasoning_summary':'Await volume'}
    assert AdvisoryDecision.model_validate(values).order_authority == 'NONE'
    for override in ({'order_authority':'BROKER'},{'auto_execution':True},{'manual_confirmation_required':False}):
        with pytest.raises(ValidationError):
            AdvisoryDecision.model_validate({**values,**override})


def test_live_report_generation(tmp_path):
    payload = {'run_id':'test','generated_at':NOW.isoformat(),'market_session':'REGULAR',
               'checks':{'llm':'FAILED'},'blockers':['LLM_TIMEOUT']}
    rendered = render_report(payload)
    atomic_write(tmp_path/'report.md',rendered)
    assert 'LLM_TIMEOUT' in rendered and 'ORDER_AUTHORITY = NONE' in rendered
    assert 'No validated LLM advice' in rendered


def test_strict_schema_covers_nested_optional_properties():
    original = PrimaryAnalystOutput.model_json_schema()
    result = strict_output_schema(original)
    def visit(node):
        if isinstance(node,dict):
            if node.get('type') == 'object':
                assert set(node['required']) == set(node['properties'])
                assert node['additionalProperties'] is False
            assert 'default' not in node
            for value in node.values():
                visit(value)
        elif isinstance(node,list):
            for value in node:
                visit(value)
    visit(result)
    assert original != result


def test_schema_error_is_not_misclassified_from_sandbox_banner():
    diagnostic = CodexResearchModelRuntime._diagnostic(exit_code=1,
        stderr="sandbox: read-only\nERROR: Invalid schema for response_format: Missing required properties")
    assert diagnostic['stderr_class'] == 'INVALID_OUTPUT_SCHEMA'
    assert diagnostic['sandbox_indicator'] is False


def test_evidence_schema_requires_catalog_ids_without_relaxing_validation():
    original = PrimaryAnalystOutput.model_json_schema()
    bound = evidence_bound_schema(original, {'one', 'two'})
    assert bound['properties']['evidence_used']['items']['enum'] == ['one', 'two']
    assert bound['$defs']['ResearchClaim']['properties']['supporting_evidence_ids']['items']['enum'] == ['one', 'two']
    assert 'enum' not in original['properties']['evidence_used']['items']


def test_parse_diagnostics_preserve_failure_and_exclude_private_inputs():
    from test_gpt_native_research import outputs
    output = outputs()['PRIMARY_ANALYST']
    result = ModelInvocationResult(status=InvocationStatus.SUCCESS, output=output)
    checked, parsed = GPTNativeResearchOrchestrator._parse(result, PrimaryAnalystOutput, {'unknown'})
    assert parsed is None and checked.error_type == 'UNSUPPORTED_EVIDENCE_ID'
    assert checked.diagnostic['unsupported_reference_count'] == 1
    output['confidence'] = 'private-account-marker'
    result = ModelInvocationResult(status=InvocationStatus.SUCCESS, output=output)
    checked, parsed = GPTNativeResearchOrchestrator._parse(result, PrimaryAnalystOutput, {'unknown'})
    assert parsed is None and checked.error_type == 'OUTPUT_VALIDATION_ERROR'
    assert 'private-account-marker' not in json.dumps(checked.diagnostic)
    assert checked.output is None


def test_acceptance_does_not_infer_pass_from_empty_blockers():
    report = {'checks': {}, 'blockers': [], 'decisions': []}
    finalize_acceptance(report, NOW)
    assert not report['LIVE_RUN_READY']
    assert not report['MERIDIAN_LIVE_ADVISORY_READY']
    assert 'STAGE_NOT_PASSED:llm' in report['blockers']


def test_publication_updates_each_row_and_decision_freshness():
    row = market_row(quote(), NOW)
    report = {'checks': {}, 'blockers': [], 'market_snapshot': {'AAPL': row},
              'decisions': [{'symbol': 'AAPL', 'data_freshness': 'LIVE'}]}
    finalize_acceptance(report, NOW + timedelta(seconds=100))
    assert report['market_snapshot']['AAPL']['freshness'] == 'STALE'
    assert report['decisions'][0]['data_freshness'] == 'STALE'
    assert not report['LIVE_RUN_READY']


def test_quote_retry_records_failed_attempt_without_accepting_future_data(monkeypatch):
    class Provider:
        calls = 0
        def get_quote(self, symbol):
            self.calls += 1
            if self.calls == 1:
                raise ValueError('quote observed_at cannot be in the future')
            return quote()
    monkeypatch.setattr('meridian.live_advisory.time.sleep', lambda _: None)
    observations, errors, attempts = fetch_current_quotes(cast(MarketQuoteProvider, Provider()), ['AAPL'])
    assert observations['AAPL'] == quote() and not errors
    assert [a['status'] for a in attempts] == ['FAILED', 'PASS']


def test_history_filters_future_and_incomplete_sessions():
    from meridian.historical import HistoricalAdjustmentStatus, HistoricalBar, HistoricalBarSeries
    from meridian.live_features import completed_session_features
    from meridian.trading_calendar import TradingCalendarName, is_trading_session, session_close

    sessions = [NOW.date() - timedelta(days=offset) for offset in range(110, -1, -1)]
    sessions = [day for day in sessions if is_trading_session(day)]
    bars = tuple(HistoricalBar(canonical_asset_id='us:AAPL', canonical_symbol='AAPL',
        provider_symbol='AAPL', session=day, calendar=TradingCalendarName.US_EQUITY,
        open=Decimal(100), high=Decimal(102), low=Decimal(99), close=Decimal(101),
        volume=Decimal(1000), currency='USD', adjustment_status=HistoricalAdjustmentStatus.RAW,
        provider='synthetic', observed_at=session_close(day), available_at=session_close(day),
        retrieved_at=NOW + timedelta(days=1), source='SYNTHETIC_NOT_LIVE') for day in sessions)
    series = HistoricalBarSeries(canonical_asset_id='us:AAPL', canonical_symbol='AAPL',
        provider='synthetic', as_of=NOW + timedelta(days=1), bars=bars)
    result = completed_session_features({'AAPL': series}, 'AAPL', NOW)['AAPL']
    assert result['status'] == 'PASS'
    assert result['market_as_of'] == '2026-09-11T20:00:00+00:00'
    assert result['bar_count'] == len(bars) - 1
    stale = series.model_copy(update={'bars': bars[:-2]})
    assert completed_session_features({'AAPL': stale}, 'AAPL', NOW)['AAPL']['status'] == 'INSUFFICIENT_OR_STALE_HISTORY'
    assert completed_session_features({'AAPL': series.model_copy(update={'bars': ()})}, 'AAPL', NOW)['AAPL']['bar_count'] == 0
    with pytest.raises(ValueError, match='TIMEZONE'):
        completed_session_features({}, 'AAPL', NOW.replace(tzinfo=None))


@pytest.mark.parametrize('kind', ['quote', 'history'])
def test_provider_response_closed_on_http_failure(kind):
    from meridian.historical import HistoricalProviderError, YahooChartHistoricalProvider
    from meridian.quotes import QuoteProviderError, YahooChartQuoteProvider
    from meridian.security_master import DEFAULT_SECURITY_MASTER

    class Response:
        status = 503
        closed = False
        def close(self):
            self.closed = True
        def read(self):
            raise AssertionError('HTTP failure must not read body')
    response = Response()
    if kind == 'quote':
        with pytest.raises(QuoteProviderError):
            YahooChartQuoteProvider(DEFAULT_SECURITY_MASTER, opener=lambda *a, **kw: response).get_quote('AAPL')
    else:
        with pytest.raises(HistoricalProviderError):
            YahooChartHistoricalProvider(DEFAULT_SECURITY_MASTER, opener=lambda *a, **kw: response).get_series(
                'AAPL', (NOW-timedelta(days=10)).date(), NOW.date(), as_of=NOW, live=True)
    assert response.closed


def test_model_process_deadline_and_pipes(tmp_path):
    from meridian.gpt_native_research import run_bounded_model_process
    environment = dict(os.environ)
    result = run_bounded_model_process([sys.executable, '-c', 'import sys; print(sys.stdin.read())'],
        'public synthetic input', cwd=tmp_path, environment=environment, budget_seconds=5)
    assert result.returncode == 0 and result.stdout.strip() == 'public synthetic input'
    with pytest.raises(subprocess.TimeoutExpired):
        run_bounded_model_process([sys.executable, '-c', 'import time; time.sleep(20)'],
            '', cwd=tmp_path, environment=environment, budget_seconds=0.2)


def test_model_deadline_rejects_result_after_host_suspend(tmp_path, monkeypatch):
    from time import time as real_time

    import meridian.gpt_native_research as native

    start = real_time()
    ticks = iter([start, start, start+600])
    monkeypatch.setattr(native.time, 'time', lambda: next(ticks))
    with pytest.raises(subprocess.TimeoutExpired):
        native.run_bounded_model_process([sys.executable, '-c', 'print("synthetic")'],
            '', cwd=tmp_path, environment=dict(os.environ), budget_seconds=5)


@pytest.mark.skipif(os.name != 'nt', reason='Windows inherited pipe regression')
def test_model_timeout_terminates_windows_child_tree(tmp_path):
    from time import monotonic

    from meridian.gpt_native_research import run_bounded_model_process

    # Child inherits stdout/stderr, reproducing the npm .cmd launcher behavior.
    command = [sys.executable, '-c',
        'import subprocess,sys,time; p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
        'print(p.pid, flush=True); time.sleep(60)']
    started = monotonic()
    with pytest.raises(subprocess.TimeoutExpired) as error:
        run_bounded_model_process(command, '', cwd=tmp_path,
                                  environment=dict(os.environ), budget_seconds=1)
    assert monotonic() - started < 10
    assert error.value.stdout is not None
    child_pid = int(error.value.stdout.strip())
    assert process_start_time(child_pid) is None


@pytest.mark.parametrize('fault', [None, 'llm', 'refresh'])
def test_live_pipeline_integration_with_explicit_synthetic_adapters(tmp_path, monkeypatch, fault):
    from test_gpt_native_research import outputs

    import meridian.live_advisory as live
    from meridian.host_readiness import ReadinessStatus
    from meridian.schemas import AccountSnapshot

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    class SyntheticProvider:
        def __init__(self):
            self.calls = {}
        def get_quote(self, symbol):
            self.calls[symbol] = self.calls.get(symbol, 0) + 1
            observed = NOW - timedelta(seconds=100 if fault == 'refresh' and self.calls[symbol] > 1 else 5)
            return quote().model_copy(update={'canonical_symbol': symbol, 'observed_at': observed,
                'available_at': observed, 'previous_close': Decimal('99'), 'open': Decimal('99.5'),
                'day_low': Decimal('99'), 'day_high': Decimal('101'), 'volume': Decimal(1000)})

    class SyntheticRuntime(FakeResearchModelRuntime):
        def __init__(self):
            super().__init__({})
        def preflight(self, routes):
            return LiveModelPreflight(status='READY', auth_usable=True, route_valid=True)
        def invoke(self, role, input_data, schema, budget_seconds, *, model, reasoning_effort):
            if fault == 'llm' and role == 'PRIMARY_ANALYST':
                return ModelInvocationResult(status=InvocationStatus.TIMEOUT, error_type='SYNTHETIC_TIMEOUT')
            if role == 'SYMBOL_ADVISORY':
                decisions = [{**thesis(), 'symbol': symbol, 'evidence_ids': [reference]}
                    for symbol, reference in input_data['evidence_ids'].items()]
                value: Any = {'decisions': decisions, 'top_action_now': 'Synthetic WAIT',
                         'avoid_now': 'Synthetic unverified entries', 'doing_nothing_assessment': 'Synthetic wait condition'}
                assert input_data['market_session'] == 'REGULAR'
                assert input_data['portfolio']['source'] == 'USER_SUPPLIED_HOST_SNAPSHOT'
            else:
                value = outputs()[role]
                if role == 'PRIMARY_ANALYST':
                    reference = input_data['evidence'][0]['evidence_id']
                    value['evidence_used'] = [reference]
                    value['supporting_claims'][0]['supporting_evidence_ids'] = [reference]
            return ModelInvocationResult(status=InvocationStatus.SUCCESS, output=value)

    account = AccountSnapshot(snapshot_id='synthetic', account_alias='synthetic', provider='synthetic',
        as_of=NOW, total_equity=100000, cash=100000, sync_state='SYNCED', freshness_state='VERIFIED')
    monkeypatch.setenv('MERIDIAN_HOME', str(tmp_path))
    monkeypatch.setattr(live, 'datetime', FrozenDateTime)
    monkeypatch.setattr(live, 'YahooChartQuoteProvider', lambda _: SyntheticProvider())
    monkeypatch.setattr(live, 'collect_live_features', lambda *a, **kw: {
        'status': 'PASS', 'features': {}, 'source': 'EXPLICIT_SYNTHETIC_TEST_NOT_LIVE'})
    monkeypatch.setattr(live, 'CodexResearchModelRuntime', SyntheticRuntime)
    monkeypatch.setattr(live, 'inspect_snapshot', lambda *a, **kw: (SimpleNamespace(status=ReadinessStatus.PASS), account))
    service = LiveAdvisoryService(RuntimePaths(tmp_path))
    report = service.run(snapshot_path=tmp_path/'synthetic-not-a-real-account.json')
    assert report['LIVE_RUN_READY'] is (fault is None)
    assert report['MERIDIAN_LIVE_ADVISORY_READY'] is False
    assert report['ORDER_AUTHORITY'] == 'NONE'
    assert Path(report['report_json']).is_file()
    assert not list((tmp_path/'locks').glob('*.lock'))
    if fault is None:
        second = service.run(snapshot_path=tmp_path/'synthetic-not-a-real-account.json')
        assert second['LIVE_RUN_READY'] and second['run_id'] != report['run_id']
        assert second['MERIDIAN_LIVE_ADVISORY_READY'] is False
        assert all(row['action'] == 'WAIT' for row in second['decisions'])
