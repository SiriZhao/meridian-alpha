"""Bounded host readiness. Reports do not execute a daily run or confer authority."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import meridian
from meridian.application import MeridianApplicationService
from meridian.config import load_policies
from meridian.gpt_native_research import CodexResearchModelRuntime
from meridian.live_account import inspect_paper
from meridian.live_advisory import MarketDataFreshnessGate, market_row
from meridian.paper import PaperSettings
from meridian.quant.integration import immutable_record
from meridian.quant.policy import load_quant_policy
from meridian.quant.version import ENGINE_SOURCE_HASH
from meridian.quotes import NasdaqApiQuoteProvider, QuoteProviderError, YahooChartQuoteProvider
from meridian.runtime import RuntimePaths, policy_directory
from meridian.runtime_io import run_lock
from meridian.security_master import DEFAULT_SECURITY_MASTER
from meridian.trading_calendar import NEW_YORK, session_context, session_open


def environment_identity() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'],
                            capture_output=True, text=True, timeout=5, check=False)
    status = subprocess.run(['git', '-C', str(root), 'status', '--porcelain'],
                            capture_output=True, text=True, timeout=5, check=False)
    return {'code_sha': result.stdout.strip() if result.returncode == 0 else 'UNKNOWN',
            'working_tree_dirty': bool(status.stdout.strip()) if status.returncode == 0 else None,
            'source_root': str(root), 'python': sys.executable, 'python_version': sys.version.split()[0],
            'package_origin': str(meridian.__file__), 'policy_directory': str(policy_directory()),
            'bridge_source_hash': hashlib.sha256('\n'.join((root / 'src/meridian' / name).read_text(encoding='utf-8')
                for name in ('live_account.py','live_advisory.py','live_features.py','live_quant_bridge.py','live_readiness.py','live_report.py','gpt_native_research.py')).encode()).hexdigest(),
            'quant_engine_hash': ENGINE_SOURCE_HASH}


def readiness_report(paths: RuntimePaths, *, probe_providers: bool = True,
                     observation_class: Literal['REAL_HOST_OBSERVATIONS','FIXTURE_ONLY'] = 'REAL_HOST_OBSERVATIONS') -> dict[str, Any]:
    """Caller must enter approved host context for all canonical write probes."""
    started = datetime.now(UTC)
    policies = load_policies(policy_directory())
    settings = policies.models.research
    account = inspect_paper(paths.db, PaperSettings.from_policy_directory(policy_directory()), started)
    # Doctor's legacy implementation invokes migrate(). Only an already current,
    # existing account may reach it; readiness never creates/upgrades a database.
    doctor = MeridianApplicationService(paths).doctor() if account['ready'] else {
        'status': 'BLOCKED', 'code': 'DOCTOR_NOT_RUN_TO_AVOID_SCHEMA_CREATION_OR_MIGRATION'}
    model = CodexResearchModelRuntime().preflight(
        {k: v.model_dump() for k, v in settings.models.items()} if settings else {})
    providers: dict[str, Any] = {}
    for provider in (YahooChartQuoteProvider(DEFAULT_SECURITY_MASTER, timeout_seconds=4),
                     NasdaqApiQuoteProvider(DEFAULT_SECURITY_MASTER, timeout_seconds=4)) if probe_providers else ():
        try:
            quote = provider.get_quote('SPY')
            cutoff = datetime.now(UTC)
            row = market_row(quote, cutoff)
            providers[provider.provider_name] = {'health': 'RESPONDED', 'reference': row,
                'freshness': MarketDataFreshnessGate().evaluate(quote, cutoff)[0],
                'quote_hash': hashlib.sha256(quote.stable_json().encode()).hexdigest(),
                'execution_certified': False}
        except (QuoteProviderError, OSError, ValueError) as error:
            providers[provider.provider_name] = {'health': 'FAILED',
                'code': error.code if isinstance(error, QuoteProviderError) else type(error).__name__,
                'execution_certified': False}
    now = datetime.now(UTC)
    checks = {'doctor': doctor['status'], 'account': 'PASS' if account['ready'] else 'BLOCKED',
              'model_login': model.status, 'providers': 'PASS' if any(
                  p['health'] == 'RESPONDED' for p in providers.values()) else 'BLOCKED',
              'report_directory': 'PASS', 'regular_session_acceptance': 'NOT_EXECUTED',
              'current_price_freshness': 'PASS' if any(p.get('freshness') in {'LIVE','DELAYED'} for p in providers.values()) else 'BLOCKED'}
    blockers = []
    for key, value in checks.items():
        if value not in {'PASS', 'READY', 'NOT_EXECUTED'}:
            blockers.append({'code': key.upper() + ':' + value,
                             'recovery': 'Resolve this diagnostic, preserve state, rerun readiness.'})
    blockers.extend([
        {'code': 'INSUFFICIENT_VERIFIED_HISTORY', 'recovery': 'Supply genuine PIT-adjusted historical contracts; public prices remain provisional.'},
        {'code': 'EXECUTION_QUOTES_UNCERTIFIED', 'recovery': 'Independent certified execution data and manual review required; do not promote public quotes.'},
        {'code': 'REGULAR_SESSION_ACCEPTANCE_NOT_EXECUTED', 'recovery': 'After regular open, run live-advisory twice with qualifying fresh inputs.'},
    ])
    lock_status = 'AVAILABLE'
    try:
        with run_lock(paths.locks, 'readiness-' + uuid4().hex):
            pass
    except (ValueError, OSError, RuntimeError):
        lock_status = 'BLOCKED'
        blockers.append({'code': 'LOCK_PROBE_BLOCKED', 'recovery': 'Inspect owner and process; do not delete an active lock.'})
    quant = load_quant_policy(policy_directory() / 'quant.yaml')
    return {'schema_version': 'meridian-live-readiness.v1', 'generated_at': now.isoformat(),
        'input_class': observation_class, 'environment': environment_identity(),
        'assessment_phase': 'FIXTURE_REGRESSION' if observation_class == 'FIXTURE_ONLY' else 'PREOPEN' if now < session_open(now) else 'POSTOPEN_READINESS',
        'paths': {'home': str(paths.home), 'cache': str(paths.cache), 'paper_ledger': str(paths.db)},
        'quant_mode': quant.mode, 'challenger_mode': 'V2.2_SHADOW',
        'research_policy': {'provider': settings.provider, 'model': settings.model,
                            'reasoning_effort': settings.reasoning_effort} if settings else None,
        'model_preflight': model.model_dump(mode='json'), 'model_inference': 'NOT_PROBED_LOGIN_ONLY',
        'market_clock': {'utc': now.isoformat(), 'new_york': now.astimezone(NEW_YORK).isoformat(),
                         'session': session_context(now), 'scheduled_open_utc': session_open(now).isoformat(),
                         'unscheduled_halts': 'UNKNOWN'},
        'doctor': doctor, 'account_readiness': account, 'provider_health': providers,
        'checks': checks, 'locking': lock_status, 'quant_availability': 'INSUFFICIENT_VERIFIED_HISTORY',
        'research_availability': 'PROVISIONAL_PUBLIC_RESEARCH_ONLY',
        'paper_eligibility': 'BLOCKED_UNCERTIFIED_EXECUTION_QUOTES', 'blockers': blockers,
        'conclusion': 'NO_GO' if doctor['status'] != 'PASS' or not account['ready'] or lock_status != 'AVAILABLE'
                      else 'PREOPEN_DEGRADED',
        'regular_session_live_acceptance_complete': False, 'trade_authorized': False,
        'broker_submission': 'DISABLED', 'ledger_written': False, 'account_initialized': False}


def run_readiness(paths: RuntimePaths) -> dict[str, Any]:
    report = readiness_report(paths)
    day = datetime.fromisoformat(report['generated_at']).astimezone(NEW_YORK).date().isoformat()
    directory = paths.reports / 'live-readiness' / day
    # Seal unique observations. A second invocation cannot rewrite the first preopen result.
    run_directory = directory / ('check-' + uuid4().hex)
    json_path = run_directory / 'preopen-readiness.json'
    markdown_path = run_directory / 'preopen-readiness.md'
    report['output_files'] = {'json': str(json_path), 'markdown': str(markdown_path)}
    text = json.dumps(report, ensure_ascii=False, indent=2, default=str) + '\n'
    immutable_record(json_path, text)
    immutable_record(markdown_path, '# Meridian 开盘研究准备检查\n\n'
                     + report['conclusion'] + '\n\n```json\n' + text + '```\n')
    # The requested stable path is the first immutable preopen observation, not a live pointer.
    if not (directory / 'preopen-readiness.json').exists():
        immutable_record(directory / 'preopen-readiness.json', text)
        immutable_record(directory / 'preopen-readiness.md', markdown_path.read_text(encoding='utf-8'))
    return report
