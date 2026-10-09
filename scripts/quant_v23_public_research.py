"""Bounded public-data audit and retrospective references, never certified OOS."""
import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from meridian.quant.experiments import isolated_output
from meridian.quant.integration import immutable_record
from meridian.quant.public_history import PublicHistoryReceipt, download_public_history
from meridian.quant.public_research import exploratory_reference

SYMBOLS = ('SPY', 'QQQM', 'AAPL', 'MSFT', 'NVDA')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--download-missing', action='store_true')
    args = parser.parse_args()
    cache, output = isolated_output(args.cache), isolated_output(args.output)
    definition = {'version': 'public-exploration-v23', 'symbols': SYMBOLS,
        'download_start': '2019-01-01', 'download_end_exclusive': '2026-01-01',
        'reference_start': '2021-01-01', 'reference_end': '2025-12-31',
        'fixed_one_way_cost_bps': [0, 5, 25, 50], 'financial_oos_eligible': False,
        'universe': 'PRESENT_DAY_CONFIGURED_SURVIVORS_PLUS_REFERENCES_NOT_HISTORICAL_MEMBERSHIP',
        'coefficient_fitting': False, 'selection': 'NONE'}
    immutable_record(output / 'definition.json', json.dumps(definition, indent=2) + '\n')
    sources: dict[str, PublicHistoryReceipt] = {}
    failures: list[dict[str, str]] = []
    for symbol in SYMBOLS:
        paths = sorted(p for p in cache.glob(symbol + '-*.json') if not p.name.endswith('.source.json'))
        receipts = [PublicHistoryReceipt.model_validate_json(p.read_text(encoding='utf-8')) for p in paths]
        if receipts:
            sources[symbol] = max(receipts, key=lambda r: r.retrieved_at)
        elif args.download_missing:
            try:
                sources[symbol] = download_public_history(symbol, date(2019, 1, 1), date(2026, 1, 1), cache)
            except (ValueError, OSError) as error:
                failures.append({'symbol': symbol, 'status': 'PROVIDER_UNAVAILABLE', 'reason': type(error).__name__})
        else:
            failures.append({'symbol': symbol, 'status': 'MISSING_EVIDENCE', 'reason': 'NO_CACHED_RECEIPT'})
    results = []
    benchmark = sources.get('SPY')
    for symbol, receipt in sources.items():
        try:
            if benchmark is None:
                raise ValueError('MISSING_BENCHMARK')
            row = exploratory_reference(receipt, benchmark, date(2021, 1, 1), date(2025, 12, 31))
            results.append(row)
        except ValueError as error:
            failures.append({'symbol': symbol, 'status': 'REFERENCE_BLOCKED', 'reason': str(error)})
    summary = {'version': 'public-research-summary.v23', 'evidence_level': 'PUBLIC_EXPLORATORY',
        'retrieved_at': datetime.now(UTC).isoformat(), 'financial_alpha_demonstrated': False,
        'v23_real_oos_status': 'MISSING_EVIDENCE', 'results': results, 'failures': failures,
        'coverage': {s: {'bars': len(r.observations), 'first': str(r.observations[0].session),
            'last': str(r.observations[-1].session), 'corporate_actions': len(r.corporate_actions),
            'source_url': r.source_url, 'source_hash': r.response_hash, 'retrieved_at': r.retrieved_at.isoformat(),
            'historical_available_at': None, 'execution_certified': False,
            'event_kinds': sorted({e.kind for e in r.corporate_actions})} for s, r in sources.items()}}
    text = json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + '\n'
    path = output / ('summary-' + hashlib.sha256(text.encode()).hexdigest() + '.json')
    immutable_record(path, text)
    print(json.dumps({'summary_path': str(path), 'references': len(results), 'failures': failures}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
