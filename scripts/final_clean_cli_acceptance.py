"""Run under the clean wheel interpreter, from an outside-checkout directory."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

import meridian
from meridian.astra_research import MeridianResearchResult, ResearchIntent, persist_research_result
from meridian.config import load_policies
from meridian.runtime import RuntimePaths, policy_directory


def main() -> None:
    root = Path.cwd()
    paths = RuntimePaths.from_environment()
    assert root.is_absolute() and Path(meridian.__file__).is_relative_to(Path(sys.prefix))
    assert 'site-packages' in str(meridian.__file__)
    results = {'python': sys.version, 'interpreter': sys.executable, 'import_path': meridian.__file__,
               'cwd': str(root), 'runtime_paths': paths.as_dict(), 'commands': {}}

    def cli(name: str, *args: str) -> dict:
        process = subprocess.run([sys.executable, '-m', 'meridian', *args], cwd=root,
            env={**os.environ, 'PYTHONUTF8': '1'}, capture_output=True, encoding='utf-8', timeout=60)
        payload = json.loads(process.stdout)
        results['commands'][name] = {'exit_code': process.returncode, 'payload': payload}
        assert process.returncode == 0, (name, process.returncode, payload)
        return payload

    cli('initialize', 'init', '--json')
    cli('initialize_again', 'init', '--json')
    doctor = cli('doctor', 'doctor', '--json')
    assert doctor['status'] == 'PASS'
    assert doctor['skill']['hash_match']
    load_policies(policy_directory())
    results['policy_directory'] = str(policy_directory())
    now = datetime.now(UTC).isoformat()
    account = root / 'synthetic-account.json'
    account.write_text(json.dumps({'snapshot_id': 'clean-room-synthetic', 'source_kind': 'fixture',
        'source_name': 'synthetic-smoke', 'as_of': now, 'retrieved_at': now,
        'coverage_status': 'COMPLETE', 'cash': '10000', 'total_equity': '10000'}), encoding='utf-8')
    market = root / 'synthetic-market.json'
    market.write_text(json.dumps({'quotes': [{'ticker': 'AAPL', 'timestamp': now, 'last': '100',
        'bid': '99.9', 'ask': '100.1', 'previous_close': '99', 'volume': 1000000,
        'atr14': '2', 'vwap': '100', 'daily_return': '0.05', 'gap_percent': '0.01',
        'freshness_state': 'VERIFIED'}]}), encoding='utf-8')
    daily = cli('synthetic_daily', 'daily', '--snapshot', str(account), '--market-fixture', str(market), '--json')
    assert daily['data_mode'] == 'FIXTURE' and daily['research_status'] == 'NOT_RUN'
    assert all(Path(p).is_file() and Path(p).is_relative_to(paths.home) for p in daily['output_files'].values())
    research = MeridianResearchResult(subject='SYNTHETIC_ACCEPTANCE', research_question='Persistence smoke only',
        intent=ResearchIntent.COMPANY_RESEARCH, analysis_cutoff=datetime.now(UTC), unknowns=('No live research performed by this fixture.',))
    audit_file = persist_research_result(research, paths)
    assert audit_file == persist_research_result(research, paths)
    with closing(sqlite3.connect(paths.db)) as database:
        results['database_integrity'] = database.execute('PRAGMA integrity_check').fetchone()[0]
        results['run_count'] = database.execute('SELECT COUNT(*) FROM runs').fetchone()[0]
    cli('restart_doctor', 'doctor', '--json')
    results['status'] = 'PASS'
    results['live_research_proved'] = False
    results['audit_file'] = str(audit_file)
    (root / 'clean-cli-evidence.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Clean wheel CLI, configuration, database, reports, audit and process restart: PASS')


if __name__ == '__main__':
    main()
