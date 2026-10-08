"""Generate a fixture-only Chinese report without network, model or ledger calls."""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

from meridian.config import load_policies
from meridian.live_advisory import market_row, render_report
from meridian.live_quant_bridge import build_live_quant_snapshot
from meridian.live_report import quant_research_rows
from meridian.quant.backtest import QuantDataset
from meridian.quant.integration import immutable_record
from meridian.quant.policy import ChallengerPolicy
from meridian.quotes import QuoteObservation
from meridian.trading_calendar import session_close


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with zipfile.ZipFile(root / 'docs/quant-v2/experiments-v22-resumed/synthetic-full-registry.zip') as archive:
        data = QuantDataset.model_validate_json(archive.read('synthetic-dataset.json'))
    when = session_close(data.series[0].bars[279].session)
    history = {s.canonical_symbol: s for s in data.series}
    quotes = {s.canonical_symbol: QuoteObservation(canonical_asset_id=s.canonical_asset_id,
        canonical_symbol=s.canonical_symbol,provider='FIXTURE_ONLY',provider_symbol=s.canonical_symbol,
        observed_at=when,available_at=when,retrieved_at=when,last=s.bars[279].close,
        previous_close=s.bars[278].close,currency='USD',source='SYNTHETIC_NOT_TODAYS_MARKET') for s in data.series}
    snapshot = build_live_quant_snapshot(histories=history,quotes=quotes,cutoff=when,
        policies=load_policies(root/'policies'),policy=ChallengerPolicy(),
        run_id='FIXTURE_ONLY_NOT_LIVE',metadata=data.security_metadata,diagnostic=True)
    report = {'run_id':'FIXTURE_ONLY_NOT_LIVE','generated_at':when.isoformat(),
        'input_class':'SYNTHETIC_DIAGNOSTIC_FIXTURE_ONLY','market_session':'FIXTURE_NOT_CURRENT_SESSION',
        'checks':{'quant':'FIXTURE_COMPUTED','llm':'NOT_RUN','report':'PASS'},
        'blockers':['FIXTURE_ONLY_NOT_LIVE_ACCEPTANCE','INSUFFICIENT_VERIFIED_HISTORY'],
        'quant_live':snapshot.model_dump(mode='json'),'quant_live_hash':snapshot.digest,
        'market_snapshot':{s:market_row(q,when) for s,q in quotes.items()},
        'LIVE_RUN_READY':False,'MERIDIAN_LIVE_ADVISORY_READY':False,'ORDER_AUTHORITY':'NONE',
        'regular_session_acceptance_complete':False,'broker_submission':'DISABLED',
        'decisions':[],'network_accessed':False,'ledger_written':False,'model_invoked':False}
    report['quant_research_rows'] = quant_research_rows(report)
    immutable_record(args.output/'fixture-report.json',json.dumps(report,ensure_ascii=False,indent=2,default=str)+'\n')
    immutable_record(args.output/'fixture-report.md','# FIXTURE ONLY — 合成回归示例，非今日行情\n\n'+render_report(report))
    print(json.dumps({'status':'FIXTURE_ONLY_REPORT_CREATED','output':str(args.output),'network_accessed':False}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
