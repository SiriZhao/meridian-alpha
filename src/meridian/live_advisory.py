"""Current public research and portfolio advice, permanently without order authority.

Reuses the installed market, GPT research, allocation and risk boundaries.
No broker interface or paper fill writer is reachable from this entry point.
"""
from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast
from uuid import uuid4

from pydantic import AwareDatetime, Field, model_validator

from meridian.allocation import DeterministicFallbackAllocator
from meridian.audit import AuditStore
from meridian.config import ResearchBudget, load_policies
from meridian.daily_research import DailyResearchInput, PublicResearchObservation
from meridian.gpt_native_research import (
    CodexResearchModelRuntime,
    ExecutionState,
    GPTNativeResearchOrchestrator,
    ResearchMemory,
)
from meridian.host_account import HostAccountSnapshotEnvelope, normalize_host_snapshot
from meridian.host_readiness import ReadinessStatus, inspect_snapshot
from meridian.live_features import collect_live_features
from meridian.market_identity import canonical_market_reference
from meridian.paper import DEFAULT_ACCOUNT, PaperLedger, PaperSettings
from meridian.quotes import (
    MarketQuoteProvider,
    QuoteObservation,
    QuoteProviderError,
    YahooChartQuoteProvider,
)
from meridian.risk import RiskEngine
from meridian.runtime import RuntimePaths, policy_directory
from meridian.runtime_io import atomic_write, run_lock
from meridian.schemas import AccountSnapshot, AlphaScore, StableModel
from meridian.security_master import DEFAULT_SECURITY_MASTER
from meridian.temporal import ResearchTemporalContext
from meridian.trading_calendar import NEW_YORK, session_context

Freshness = Literal["LIVE", "DELAYED", "STALE", "UNAVAILABLE"]
Action = Literal["BUY", "ADD", "HOLD", "WAIT", "TRIM", "SELL", "AVOID"]


class MarketDataFreshnessGate:
    """LIVE denotes an observed age <=90s, never an execution entitlement."""
    def evaluate(self, quote: QuoteObservation | None, now: datetime, *, cached: bool = False) -> tuple[Freshness, str]:
        if now.tzinfo is None:
            raise ValueError("FRESHNESS_TIMEZONE_REQUIRED")
        if quote is None:
            return "UNAVAILABLE", "NO_OBSERVATION"
        if quote.observed_at > now or quote.retrieved_at > now or quote.observed_at > quote.retrieved_at:
            return "UNAVAILABLE", "FUTURE_TIMESTAMP_REJECTED"
        age = (now - quote.observed_at).total_seconds()
        if cached or age > max(900, (quote.delay_seconds or 0) + 90):
            return "STALE", "CACHE_OR_AGE_EXCEEDED"
        if quote.delay_seconds and quote.delay_seconds > 0:
            return "DELAYED", "PROVIDER_DECLARED_DELAY"
        if age > 90:
            return "STALE", "OBSERVATION_OLDER_THAN_90_SECONDS"
        if session_context(now) != session_context(quote.observed_at):
            return "STALE", "SESSION_MISMATCH"
        return "LIVE", "OBSERVED_WITHIN_90_SECONDS; FEED_ENTITLEMENT_UNCERTIFIED"


class AdvisoryThesis(StableModel):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    action: Action
    confidence: float = Field(ge=0, le=1)
    time_horizon: str = Field(min_length=1)
    thesis: str = Field(min_length=1)
    positive_drivers: tuple[str, ...]
    negative_drivers: tuple[str, ...]
    risk_flags: tuple[str, ...]
    wait_until: str | None = None
    evidence_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def actionable_wait(self):
        if self.action == "WAIT" and not (self.wait_until or "").strip():
            raise ValueError("WAIT_CONDITION_REQUIRED")
        return self


class AdvisoryTheses(StableModel):
    decisions: tuple[AdvisoryThesis, ...] = Field(min_length=1)
    top_action_now: str = Field(min_length=1)
    avoid_now: str = Field(min_length=1)
    doing_nothing_assessment: str = Field(min_length=1)


class AdvisoryDecision(AdvisoryThesis):
    market_context: str
    current_price: Decimal | None
    suggested_entry: Decimal | None
    suggested_limit_zone: tuple[Decimal, Decimal] | None
    invalidation_level: Decimal | None
    position_guidance: str
    portfolio_impact: str
    data_as_of: AwareDatetime
    data_freshness: Freshness
    reasoning_summary: str
    price_guidance_source: Literal["DETERMINISTIC_OBSERVED_RANGE"] = "DETERMINISTIC_OBSERVED_RANGE"
    execution_eligibility: Literal["BLOCKED_PUBLIC_QUOTE_MANUAL_REVIEW_REQUIRED"] = "BLOCKED_PUBLIC_QUOTE_MANUAL_REVIEW_REQUIRED"
    order_authority: Literal["NONE"] = "NONE"
    auto_execution: Literal[False] = False
    manual_confirmation_required: Literal[True] = True


def market_row(quote: QuoteObservation, now: datetime) -> dict[str, Any]:
    freshness, reason = MarketDataFreshnessGate().evaluate(quote, now)
    fields = {name: getattr(quote, name) for name in (
        "last", "bid", "ask", "previous_close", "open", "day_high", "day_low", "volume"
    )}
    change = quote.last / quote.previous_close - 1 if quote.last and quote.previous_close else None
    return {
        "symbol": quote.canonical_symbol, "timestamp": quote.observed_at.astimezone(NEW_YORK).isoformat(),
        "timezone": "America/New_York", "session": session_context(now),
        **fields, "daily_change": change, "source": quote.source,
        "received_at": quote.retrieved_at.isoformat(),
        "age_seconds": (now - quote.observed_at).total_seconds(), "freshness": freshness,
        "freshness_reason": reason, "declared_delay_seconds": quote.delay_seconds,
        "missing_reasons": {name: "PROVIDER_FIELD_UNAVAILABLE" for name, value in fields.items() if value is None},
        "delay_disclosure": "UNKNOWN" if quote.delay_seconds is None else "PROVIDER_DECLARED",
        "retrieval": "NETWORK", "execution_quote_grade": False,
    }


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def fetch_current_quotes(provider: MarketQuoteProvider, symbols: list[str]) -> tuple[dict[str, QuoteObservation], dict[str, str], list[dict[str, Any]]]:
    observations: dict[str, QuoteObservation] = {}
    errors: dict[str, str] = {}
    attempts: list[dict[str, Any]] = []
    for symbol in symbols:
        for attempt in range(1, 3):
            try:
                observations[symbol] = provider.get_quote(symbol)
            except (QuoteProviderError, ValueError, OSError) as error:
                # Only public quote validation is involved; never include credentials.
                message = error.code if isinstance(error, QuoteProviderError) else str(error)
                errors[symbol] = type(error).__name__ + ':' + message
                attempts.append({'symbol': symbol, 'attempt': attempt, 'status': 'FAILED', 'error': errors[symbol]})
                if attempt == 1:
                    time.sleep(0.75)
            else:
                errors.pop(symbol, None)
                attempts.append({'symbol': symbol, 'attempt': attempt, 'status': 'PASS'})
                break
    return observations, errors, attempts


def finalize_acceptance(report: dict[str, Any], now: datetime) -> None:
    """Single-run readiness is not a certificate of two-run external acceptance."""
    report['generated_at'] = now.isoformat()
    report['market_session'] = session_context(now)
    for row in report.get('market_snapshot', {}).values():
        age = (now - datetime.fromisoformat(row['timestamp'])).total_seconds()
        row['age_at_report_seconds'] = age
        if age > max(90, (row.get('declared_delay_seconds') or 0) + 90):
            row['freshness_at_ingestion'] = row['freshness']
            row['freshness'] = 'STALE'
            report['freshness'] = report['checks']['freshness'] = 'STALE'
            if 'MARKET_AGED_DURING_RESEARCH_RERUN_REQUIRED' not in report['blockers']:
                report['blockers'].append('MARKET_AGED_DURING_RESEARCH_RERUN_REQUIRED')
    for decision in report.get('decisions', []):
        row = report.get('market_snapshot', {}).get(decision['symbol'])
        if row:
            decision['data_freshness'] = row['freshness']
    if report['market_session'] != 'REGULAR':
        report['blockers'].append('REGULAR_SESSION_ACCEPTANCE_REQUIRED')
    portfolio = report.get('portfolio_summary', {})
    if portfolio.get('source') == 'USER_SUPPLIED_HOST_SNAPSHOT':
        account_as_of = datetime.fromisoformat(portfolio['as_of'])
        account_age = (now-account_as_of).total_seconds()
        portfolio['age_at_report_seconds'] = account_age
        if not 0 <= account_age <= portfolio['max_age_seconds'] or account_as_of.astimezone(NEW_YORK).date() != now.astimezone(NEW_YORK).date():
            report['checks']['portfolio_load'] = 'FAILED'
            report['blockers'].append('FRESH_REAL_ACCOUNT_SNAPSHOT_REQUIRED')
    required = ('filesystem', 'market_clock', 'market_provider', 'data_received', 'portfolio_load',
                'features', 'research', 'llm', 'risk', 'advisory', 'report')
    for key in required:
        if report['checks'].get(key) != 'PASS':
            blocker = 'STAGE_NOT_PASSED:' + key
            if blocker not in report['blockers']:
                report['blockers'].append(blocker)
    if report['checks'].get('freshness') not in {'PASS', 'DELAYED'}:
        report['blockers'].append('FRESHNESS_NOT_ACCEPTABLE')
    if not report.get('decisions'):
        report['blockers'].append('VALIDATED_DECISIONS_REQUIRED')
    report['LIVE_RUN_READY'] = not report['blockers']
    report['acceptance_pending'] = ['TWO_RUN_EXTERNAL_HOST_ACCEPTANCE_REQUIRED']
    if report.get('portfolio_summary', {}).get('source') != 'USER_SUPPLIED_HOST_SNAPSHOT':
        report['acceptance_pending'].append('FRESH_REAL_ACCOUNT_SNAPSHOT_REQUIRED')
    report['MERIDIAN_LIVE_ADVISORY_READY'] = False


def render_report(report: dict[str, Any]) -> str:
    lines = ["# MERIDIAN ALPHA — LIVE SESSION REPORT", "",
             f"Run ID: {report['run_id']}", f"Generated At: {report['generated_at']}",
             f"Market Session: {report['market_session']}",
             f"Market Data As Of: {report.get('market_data_as_of')}",
             f"Provider: {report.get('provider', 'UNAVAILABLE')}",
             f"Freshness: {report.get('freshness', 'UNAVAILABLE')}", "",
             "## Portfolio summary", "", json.dumps(report.get('portfolio_summary', {}), default=str),
             "", "## Market regime and current signals", "",
             json.dumps(report.get('signals', {}), default=str),
             "", "## Completed-session historical features", "",
             json.dumps(report.get('historical_features', {}), default=str),
             "", "## LLM research", "", json.dumps(report.get('research_summary', {}), default=str),
             "", "## Risk review", "", json.dumps(report.get('risk', {}), default=str),
             "", "## Action table", "",
             "| Symbol | Price | Action | Confidence | Entry | Invalidation | Position guidance | Main reason |",
             "|---|---:|---|---:|---:|---:|---|---|"]
    for row in report.get('decisions', []):
        values = [row['symbol'], row['current_price'], row['action'], row['confidence'],
                  row['suggested_entry'], row['invalidation_level'], row['position_guidance'], row['thesis']]
        lines.append('| ' + ' | '.join(str(value).replace('|', '/').replace('\n', ' ') for value in values) + ' |')
        if row.get('wait_until'):
            lines.append(f"\n{row['symbol']} WAIT UNTIL: {row['wait_until']}\n")
    lines.extend(['', '## Top action now', '', str(report.get('top_action_now', 'No validated LLM advice available.')),
                  'Avoid now: ' + str(report.get('avoid_now', 'UNAVAILABLE')),
                  'Doing nothing: ' + str(report.get('doing_nothing_assessment', 'UNAVAILABLE')),
                  '', '## Acceptance', '', json.dumps(report['checks'], indent=2),
                  'Blockers: ' + ', '.join(report['blockers']), '',
                  'Acceptance pending: ' + ', '.join(report.get('acceptance_pending', [])),
                  'AUTO_EXECUTION = DISABLED; MANUAL_CONFIRMATION_REQUIRED = TRUE; ORDER_AUTHORITY = NONE',
                  'Research price zones are deterministic observations, not executable limit-order tickets.', ''])
    return '\n'.join(lines)


class LiveAdvisoryService:
    def __init__(self, paths: RuntimePaths | None = None):
        self.paths = paths or RuntimePaths.from_environment()

    def run(self, *, account_name: str = DEFAULT_ACCOUNT, snapshot_path: Path | None = None,
            role_timeout: int = 90, reasoning_effort: str | None = None) -> dict[str, Any]:
        self.paths.preflight()
        run_id = "live-" + uuid4().hex
        with run_lock(self.paths.locks, run_id):
            directory = self.paths.reports / datetime.now(UTC).date().isoformat() / run_id
            directory.mkdir(parents=True, exist_ok=False)
            logger = logging.getLogger(run_id)
            logger.setLevel(logging.INFO)
            handler = logging.FileHandler(self.paths.logs / (run_id + '.log'), encoding='utf-8')
            handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
            logger.addHandler(handler)
            try:
                report = self._run(run_id, account_name, snapshot_path, role_timeout, logger, reasoning_effort)
                report['report_json'] = str(directory / 'live-report.json')
                report['report_markdown'] = str(directory / 'live-report.md')
                report['log'] = str(self.paths.logs / (run_id + '.log'))
                # A report becomes accepted only when both outputs exist durably.
                report['checks']['report'] = 'PASS'
                finalize_acceptance(report, datetime.now(UTC))
                atomic_write(directory / 'live-report.md', render_report(report))
                atomic_write(directory / 'live-report.json', json.dumps(report, indent=2, default=str))
                logger.info('[REPORT] %s', report['report_json'])
                return report
            finally:
                logger.removeHandler(handler)
                handler.close()

    def _run(self, run_id: str, account_name: str, snapshot_path: Path | None,
             role_timeout: int, logger: logging.Logger, reasoning_effort: str | None = None) -> dict[str, Any]:
        now = datetime.now(UTC)
        checks = {key: 'NOT_RUN' for key in ('filesystem', 'market_clock', 'market_provider', 'data_received',
                  'freshness', 'portfolio_load', 'research', 'llm', 'risk', 'advisory', 'report')}
        checks.update(filesystem='PASS', market_clock='PASS')
        report: dict[str, Any] = {
            'run_id': run_id, 'generated_at': now.isoformat(), 'market_session': session_context(now),
            'checks': checks, 'blockers': [], 'decisions': [], 'AUTO_EXECUTION': 'DISABLED',
            'MANUAL_CONFIRMATION_REQUIRED': True, 'ORDER_AUTHORITY': 'NONE',
            'MERIDIAN_LIVE_ADVISORY_READY': False,
        }
        logger.info('[BOOT] run_id=%s', run_id)
        logger.info('[RUNTIME] MERIDIAN_HOME=%s RUNTIME_WRITABLE=TRUE', self.paths.home)
        logger.info('[FILESYSTEM] PASS [LOCK] ACQUIRED')
        policies = load_policies(policy_directory())
        logger.info('[CONFIG] PASS [MARKET_CLOCK] %s', session_context(now))
        if not 15 <= role_timeout <= 120:
            raise ValueError('LIVE_ROLE_TIMEOUT_OUT_OF_RANGE')
        settings = policies.models.research
        if settings is None:
            raise ValueError('RESEARCH_NOT_CONFIGURED')
        if reasoning_effort is not None:
            if reasoning_effort not in {'low', 'medium', 'high'}:
                raise ValueError('LIVE_REASONING_EFFORT_INVALID')
            settings = settings.model_copy(update={'reasoning_effort': reasoning_effort,
                'models': {key: value.model_copy(update={'reasoning_effort': reasoning_effort})
                           for key, value in settings.models.items()}})
        report['model_runtime'] = {'reasoning_effort': settings.reasoning_effort,
                                   'role_timeout_seconds': role_timeout, 'model': settings.model}
        # Dedicated production budget is explicit in launcher/log, not a gate override.
        # ``role_timeout`` is the complete chain deadline.  The native runtime
        # uses one shared Codex process for the four logical roles; multiplying
        # this value by four silently defeated the live-advisory bound and let a
        # single call run until the global 180s settings timeout.
        primary_budget = max(1, int(role_timeout * 0.40))
        skeptic_budget = max(1, int(role_timeout * 0.25))
        scenario_budget = max(1, int(role_timeout * 0.20))
        synthesis_budget = max(1, role_timeout - primary_budget - skeptic_budget - scenario_budget)
        settings = settings.model_copy(update={
            'live_enabled': True,
            'timeout_seconds': role_timeout,
            'models': {key: value.model_copy(update={'timeout_seconds': role_timeout}) for key, value in settings.models.items()},
            'native_budget': ResearchBudget(total_seconds=role_timeout, primary_seconds=primary_budget,
                skeptic_seconds=skeptic_budget, scenario_seconds=scenario_budget, synthesis_seconds=synthesis_budget),
        })
        envelope: HostAccountSnapshotEnvelope | None = None
        account: AccountSnapshot | None = None
        if snapshot_path:
            diagnostic, account = inspect_snapshot(snapshot_path, max_age_seconds=policies.data.account_snapshot_max_age_seconds)
            if diagnostic.status is ReadinessStatus.PASS and account is not None:
                checks['portfolio_load'] = 'PASS'
                report['portfolio_summary'] = {'source': 'USER_SUPPLIED_HOST_SNAPSHOT', 'as_of': account.as_of.isoformat(),
                    'max_age_seconds': policies.data.account_snapshot_max_age_seconds, 'raw_account_persisted': False}
            else:
                report['blockers'].append(diagnostic.code)
        else:
            ledger = PaperLedger(AuditStore(self.paths.db), PaperSettings.from_policy_directory(policy_directory()))
            paper = ledger.state(account_name)
            if paper is not None:
                envelope = ledger.export_snapshot(account_name)
                account = normalize_host_snapshot(envelope)
                checks['portfolio_load'] = 'PASS'
                report['portfolio_summary'] = {'source': 'PAPER_LEDGER', 'account': account_name,
                    'as_of': envelope.as_of.isoformat(), 'ledger_version': paper.ledger_version,
                    'as_of_semantics': 'LEDGER_READ_TIME_NOT_BROKER_CONFIRMATION',
                    'account_created_at': paper.created_at.isoformat(),
                    'position_count': len(paper.positions), 'real_schwab_account': False,
                    'valuation': 'COST_BASIS_BEFORE_CURRENT_MARKS', 'raw_account_persisted': False}
            else:
                report['blockers'].append('PORTFOLIO_NOT_FOUND')
        logger.info('[PORTFOLIO] %s', checks['portfolio_load'])
        benchmark = PaperSettings.from_policy_directory(policy_directory()).benchmark_symbol
        symbols = sorted(set(policies.universe.tickers) | {benchmark} | ({h.ticker for h in account.holdings} if account else set()))
        report['historical_features'] = collect_live_features(symbols, benchmark,
            evidence_directory=self.paths.home / 'snapshots' / run_id / 'history')
        checks['features'] = report['historical_features']['status']
        if checks['features'] != 'PASS':
            report['blockers'].append('HISTORICAL_FEATURES_INCOMPLETE')
        logger.info('[RESEARCH] completed-session features=%s', checks['features'])
        provider = YahooChartQuoteProvider(DEFAULT_SECURITY_MASTER)
        observations, errors, attempts = fetch_current_quotes(provider, symbols)
        report['market_fetch_attempts'] = attempts
        cutoff = datetime.now(UTC)
        rows = {symbol: market_row(quote, cutoff) for symbol, quote in observations.items()}
        report.update(market_snapshot=rows, provider='yahoo-chart-public', provider_errors=errors,
                      market_data_as_of=min((q.observed_at.isoformat() for q in observations.values()), default=None))
        checks['market_provider'] = checks['data_received'] = 'PASS' if len(rows) == len(symbols) else 'FAILED'
        fresh = bool(rows) and len(rows) == len(symbols) and all(row['freshness'] in {'LIVE', 'DELAYED'} for row in rows.values())
        freshness = 'DELAYED' if fresh and any(row['freshness'] == 'DELAYED' for row in rows.values()) else 'LIVE' if fresh else 'STALE' if rows else 'UNAVAILABLE'
        report['freshness'] = freshness
        checks['freshness'] = 'PASS' if freshness == 'LIVE' else freshness
        logger.info('[MARKET_DATA] provider=yahoo received=%s freshness=%s', len(rows), freshness)
        if not fresh:
            report['blockers'].append('CURRENT_MARKET_DATA_INCOMPLETE_OR_STALE')
        valid_rows = {symbol: row for symbol, row in rows.items() if row['daily_change'] is not None and row['freshness'] in {'LIVE', 'DELAYED'}}
        signals = {symbol: {'daily_return': row['daily_change'], 'source': row['source'], 'as_of': row['timestamp']} for symbol, row in valid_rows.items()}
        benchmark_return = valid_rows.get(benchmark, {}).get('daily_change')
        regime = 'UP_SESSION' if benchmark_return is not None and benchmark_return > 0 else 'DOWN_SESSION' if benchmark_return is not None and benchmark_return < 0 else 'NEUTRAL_OR_UNAVAILABLE'
        report['signals'] = {'regime': regime, 'method': 'OBSERVED_DAILY_RETURN_WITH_COMPLETED_SESSION_FEATURES', 'factors': signals,
                             'finrlx': 'NOT_INVOKED_NO_MODEL_OUTPUT', 'probabilities': 'LLM_SCENARIOS_NOT_CALIBRATED'}
        if len(valid_rows) != len(symbols):
            report['blockers'].append('DAILY_RETURN_INPUTS_INCOMPLETE')
        # Complete independent evidence gathering even when account input is missing.
        context: dict[str, Any] | None = None
        target_weights: dict[str, Decimal] = {}
        if account is not None and all(h.ticker in observations and observations[h.ticker].last for h in account.holdings):
            holdings = tuple(h.model_copy(update={'market_value': (h.quantity * cast(Decimal, observations[h.ticker].last)).quantize(Decimal('.0001'))}) for h in account.holdings)
            nav = account.cash + sum((h.market_value for h in holdings), Decimal(0))
            marked = account.model_copy(update={'holdings': holdings, 'total_equity': nav})
            context = {'as_of': account.as_of.isoformat(), 'source': report['portfolio_summary']['source'],
                       'current_exposure': str((nav-account.cash)/nav if nav else 0),
                       'positions': [{'symbol': h.ticker, 'quantity': str(h.quantity),
                                      'average_cost': str(h.average_cost) if h.average_cost else str(h.cost_basis/h.quantity) if h.cost_basis and h.quantity else None,
                                      'weight': str(h.market_value/nav if nav else 0)} for h in holdings]}
            scores = [AlphaScore(ticker=symbol, score=max(Decimal(0), row['daily_change']), confidence=Decimal(1),
                       expected_direction='BULLISH' if row['daily_change'] > 0 else 'NEUTRAL', risk_penalty=Decimal(0),
                       evidence_quality=Decimal(1), model_source='OBSERVED_DAILY_RETURN') for symbol,row in valid_rows.items()]
            target = DeterministicFallbackAllocator().allocate(scores, {}, marked, policies.risk)
            risk = RiskEngine().approve(target, marked, 'NORMAL', policies.risk,
                       sectors={symbol:'OPERATIONAL_UNCLASSIFIED' for symbol in valid_rows})
            target_weights = {p.ticker:p.target_weight for p in risk.approved.positions}
            checks['risk'] = 'PASS'
            report['risk'] = {'violations': list(risk.violations), 'modifications': list(risk.modifications),
                              'target_weights': target_weights, 'min_cash_weight': str(policies.risk.min_cash_weight),
                              'warnings': ['PUBLIC_QUOTES_UNCERTIFIED', 'SECTORS_NOT_CERTIFIED', 'LONG_ONLY'],
                              'execution_eligibility':'BLOCKED_PUBLIC_QUOTE_MANUAL_REVIEW_REQUIRED'}
        else:
            report['blockers'].append('PORTFOLIO_RISK_CONTEXT_UNAVAILABLE')
        logger.info('[RISK] %s', checks['risk'])
        if not valid_rows:
            return report
        references = {symbol:digest(row) for symbol,row in valid_rows.items()}
        request = DailyResearchInput(parent_run_id=run_id, analysis_cutoff=cutoff, mode='LIVE',
                    snapshot_reference='IN_MEMORY_ONLY', market_reference=canonical_market_reference(rows), policy_reference=digest(policies.risk.model_dump()),
                    provider='codex_cli', model=settings.model,
                    temporal_context=ResearchTemporalContext(run_id=run_id, trading_date=cutoff.astimezone(NEW_YORK).date(),
                        as_of=cutoff, information_cutoff=cutoff, market_session=session_context(cutoff),
                        timezone='America/New_York'),
                    observations=tuple(PublicResearchObservation(ticker=symbol, observed_at=observations[symbol].observed_at,
                        price=cast(Decimal, observations[symbol].last), daily_return=row['daily_change'], reference=references[symbol]) for symbol,row in valid_rows.items()),
                    freshness_status='PASS' if fresh else 'BLOCKED', portfolio_context=context,
                    market_context={'current_time':cutoff.isoformat(),'market_session':session_context(cutoff),
                                    'snapshot':rows,'signals':report['signals'],'risk':report.get('risk'),
                                    'historical_features':report['historical_features']})
        runtime = CodexResearchModelRuntime()
        preflight = runtime.preflight({key: value.model_dump() for key,value in settings.models.items()})
        report['llm_preflight'] = preflight.model_dump(mode='json')
        logger.info('[LLM] provider preflight=%s', preflight.status)
        if preflight.status != 'READY':
            report['blockers'].append('LLM_PREFLIGHT_' + preflight.status)
            return report
        logger.info(
            '[RESEARCH] starting GPT native chain; bounded process budget=%s',
            min(settings.native_budget.total_seconds, settings.timeout_seconds),
        )
        native = GPTNativeResearchOrchestrator(runtime, memory=ResearchMemory(self.paths.data/'research'/'memory')).run(
                    request, research_data_status='PASS' if fresh else 'BLOCKED', execution_data_status='BLOCKED_PUBLIC_QUOTE',
                    execution_state=ExecutionState.BLOCKED_STALE_EXECUTION_QUOTE, settings=settings, run_id=run_id)
        checks['research'] = checks['llm'] = 'PASS' if not native.missing_stages else 'FAILED'
        report['research_summary'] = {'state':native.research_state.value,'missing_stages':list(native.missing_stages),
            'stages':{name:{'status':stage.status.value,'error':stage.error_type,'duration_ms':stage.duration_ms,
                'model':stage.model,'reasoning_effort':stage.reasoning_effort,'diagnostic':stage.diagnostic} for name,stage in native.stages.items()},
            'synthesis':native.synthesis.model_dump(mode='json') if native.synthesis else None,
            'primary':native.primary.model_dump(mode='json') if native.primary else None,
            'skeptic':native.skeptic.model_dump(mode='json') if native.skeptic else None,
            'scenarios':native.scenarios.model_dump(mode='json') if native.scenarios else None,
            'confidence_composition':native.confidence.model_dump(mode='json'),
            'market_input_hash':request.market_reference, 'input_evidence_ids':list(references.values())}
        logger.info('[LLM] %s', checks['llm'])
        if native.missing_stages:
            report['blockers'].append('LLM_RESEARCH_INCOMPLETE')
            return report
        # The model chain can take minutes. Refresh independently and let the final
        # advisory model see the new snapshot, with the earlier thesis dated explicitly.
        report['research_market_snapshot'] = rows
        refreshed, refresh_errors, refresh_attempts = fetch_current_quotes(provider, symbols)
        report['market_refresh_attempts'] = refresh_attempts
        report['blockers'].extend('FINAL_MARKET_REFRESH_FAILED:' + symbol for symbol in refresh_errors)
        refresh_cutoff = datetime.now(UTC)
        if len(refreshed) != len(symbols):
            checks['freshness'] = 'UNAVAILABLE'
            return report
        observations = refreshed
        rows = {symbol: market_row(quote, refresh_cutoff) for symbol,quote in observations.items()}
        if any(row['freshness'] not in {'LIVE','DELAYED'} or row['daily_change'] is None for row in rows.values()):
            checks['freshness'] = 'STALE'
            report['blockers'].append('FINAL_MARKET_REFRESH_INVALID')
            return report
        report['market_snapshot'] = rows
        report['market_data_as_of'] = min(q.observed_at.isoformat() for q in observations.values())
        report['freshness'] = 'DELAYED' if any(row['freshness']=='DELAYED' for row in rows.values()) else 'LIVE'
        checks['freshness'] = 'DELAYED' if report['freshness'] == 'DELAYED' else 'PASS'
        report['research_signals'] = report['signals']
        benchmark_return = rows[benchmark]['daily_change']
        regime = 'UP_SESSION' if benchmark_return > 0 else 'DOWN_SESSION' if benchmark_return < 0 else 'NEUTRAL_OR_UNAVAILABLE'
        report['signals'] = {**report['signals'], 'regime': regime,
            'factors': {symbol: {'daily_return': row['daily_change'], 'source': row['source'],
                       'as_of': row['timestamp']} for symbol, row in rows.items()}}
        references = {symbol:digest(row) for symbol,row in rows.items()}
        report['advisory_input_hash'] = digest(rows)
        report['advisory_input_evidence_ids'] = references
        if account is not None:
            holdings = tuple(h.model_copy(update={'market_value': (h.quantity * cast(Decimal,observations[h.ticker].last)).quantize(Decimal('.0001'))}) for h in account.holdings)
            nav = account.cash + sum((h.market_value for h in holdings), Decimal(0))
            marked = account.model_copy(update={'holdings':holdings,'total_equity':nav})
            scores = [AlphaScore(ticker=symbol,score=max(Decimal(0),row['daily_change']),confidence=Decimal(1),
                      expected_direction='BULLISH' if row['daily_change']>0 else 'NEUTRAL',risk_penalty=Decimal(0),
                      evidence_quality=Decimal(1),model_source='OBSERVED_DAILY_RETURN') for symbol,row in rows.items()]
            target = DeterministicFallbackAllocator().allocate(scores,{},marked,policies.risk)
            risk = RiskEngine().approve(target,marked,'NORMAL',policies.risk,sectors={symbol:'OPERATIONAL_UNCLASSIFIED' for symbol in rows})
            target_weights = {p.ticker:p.target_weight for p in risk.approved.positions}
            report['risk'].update(target_weights=target_weights,violations=list(risk.violations),modifications=list(risk.modifications),as_of=refresh_cutoff.isoformat())
            if context is not None:
                context['current_exposure'] = str((nav-account.cash)/nav if nav else 0)
                context['positions'] = [{'symbol':h.ticker,'quantity':str(h.quantity),
                    'average_cost':str(h.average_cost) if h.average_cost is not None else str(h.cost_basis/h.quantity) if h.cost_basis and h.quantity else None,
                    'weight':str(h.market_value/nav if nav else 0)} for h in holdings]
        logger.info('[MARKET_DATA] Refreshed after research; final advisory receives current snapshot')
        result = runtime.invoke('SYMBOL_ADVISORY', {
            'instruction':'Return one explicit decision for every supplied symbol. BUY/ADD/HOLD/WAIT/TRIM/SELL/AVOID are research opinions only. WAIT needs a concrete observable condition. Use only supplied market facts; no invented prices/news. Do not include private account amounts in prose. Cite each symbol evidence ID. No numeric sizing or price advice; deterministic code owns those.',
            'market':rows,'evidence_ids':references,'portfolio':context,
            'research':native.synthesis.model_dump(mode='json') if native.synthesis else None,
            'risk':report.get('risk'), 'signals':report['signals'],
            'historical_features':report['historical_features'],
            'current_time':refresh_cutoff.isoformat(), 'market_session':session_context(refresh_cutoff),
            'execution_authority':'NONE',
        }, AdvisoryTheses.model_json_schema(), role_timeout, model=settings.synthesis_model or settings.model, reasoning_effort=settings.reasoning_effort)
        report['advisory_invocation'] = {'status':result.status.value,'error':result.error_type,
            'model':result.model,'reasoning_effort':result.reasoning_effort,'diagnostic':result.diagnostic,'duration_ms':result.duration_ms}
        if result.status.value != 'SUCCESS' or result.output is None:
            checks['advisory'] = 'FAILED'
            report['blockers'].append('LLM_ADVISORY_' + result.status.value)
            return report
        try:
            theses = AdvisoryTheses.model_validate(result.output)
            if len(theses.decisions) != len(symbols) or {t.symbol for t in theses.decisions} != set(symbols):
                raise ValueError('ADVISORY_COVERAGE_INVALID')
            for thesis in theses.decisions:
                if references[thesis.symbol] not in thesis.evidence_ids or not set(thesis.evidence_ids) <= set(references.values()):
                    raise ValueError('ADVISORY_EVIDENCE_INVALID')
        except ValueError:
            checks['advisory'] = 'FAILED'
            report['blockers'].append('ADVISORY_SCHEMA_OR_EVIDENCE_INVALID')
            return report
        decisions = []
        for thesis in theses.decisions:
            quote = observations[thesis.symbol]
            row = rows[thesis.symbol]
            # These are observational research levels, never an executable order price.
            entry = min(quote.last, quote.open) if thesis.action in {'BUY','ADD','WAIT'} and quote.last and quote.open else None
            zone = (min(entry,quote.last), max(entry,quote.last)) if entry and quote.last else None
            weight = target_weights.get(thesis.symbol, Decimal(0))
            decision = AdvisoryDecision(**thesis.model_dump(), market_context=regime, current_price=quote.last,
                suggested_entry=entry, suggested_limit_zone=zone,
                invalidation_level=quote.day_low if thesis.action in {'BUY','ADD','HOLD'} else None,
                position_guidance=f'Deterministic risk-capped reference target {weight:.2%}; manual review required.',
                portfolio_impact='Research opinion and deterministic allocation may disagree; no order generated.',
                data_as_of=quote.observed_at, data_freshness=row['freshness'], reasoning_summary=thesis.thesis)
            decisions.append(decision.model_dump(mode='json'))
        report.update(decisions=decisions,top_action_now=theses.top_action_now,avoid_now=theses.avoid_now,
                      doing_nothing_assessment=theses.doing_nothing_assessment)
        checks['advisory'] = 'PASS'
        # Recheck at publication: a long model call must not turn old data into live data.
        finished = datetime.now(UTC)
        if any(MarketDataFreshnessGate().evaluate(q,finished)[0] not in {'LIVE','DELAYED'} for q in observations.values()):
            checks['freshness'] = 'STALE'
            report['freshness'] = 'STALE'
            report['blockers'].append('MARKET_AGED_DURING_RESEARCH_RERUN_REQUIRED')
        report['generated_at'] = finished.isoformat()
        logger.info('[ADVISORY] %s', checks['advisory'])
        return report
