"""Public observations cannot be relabeled as PIT or lose missingness/provenance."""
import json
from datetime import UTC, datetime

import pytest

from meridian.quant.public_history import parse_yahoo_history

URL = 'https://query1.finance.yahoo.com/v8/finance/chart/SPY'
NOW = datetime(2026, 10, 9, tzinfo=UTC)


def payload():
    return {'chart': {'result': [{'meta': {'symbol': 'SPY', 'currency': 'USD', 'exchangeTimezoneName': 'America/New_York'},
        'timestamp': [1609767000, 1609853400], 'indicators': {'quote': [{'open': [100, 101], 'high': [102, 103],
            'low': [99, 100], 'close': [101, 102], 'volume': [None, 2000000]}], 'adjclose': [{'adjclose': [99, 100]}]},
        'events': {'dividends': {'1': {'date': 1609767000, 'amount': .5}}}}]}}


def parse(data):
    return parse_yahoo_history(json.dumps(data, allow_nan=False).encode(), symbol='SPY', source_url=URL, retrieved_at=NOW)


def test_public_identity_missing_volume_and_availability_preserved():
    result = parse(payload())
    assert result.observations[0].volume is None
    assert all(r.historical_available_at is None for r in result.observations)
    assert result.evidence_level == 'PUBLIC_EXPLORATORY' and not result.financial_oos_eligible
    assert not result.execution_certified and result.corporate_actions[0].amount is not None
    with pytest.raises(ValueError):
        type(result).model_validate(result.model_dump() | {'evidence_level': 'CERTIFIED_PIT'})


@pytest.mark.parametrize('mutation', ['symbol', 'currency', 'timestamp', 'future', 'price', 'adjustment', 'length', 'split', 'missing', 'source'])
def test_malformed_or_ambiguous_history_rejected(mutation):
    data = payload()
    row = data['chart']['result'][0]
    if mutation in {'symbol', 'currency'}:
        row['meta'][mutation] = 'INVALID'
    elif mutation == 'timestamp':
        row['timestamp'][1] = row['timestamp'][0]
    elif mutation == 'future':
        row['timestamp'][1] = int(datetime(2027, 1, 1, tzinfo=UTC).timestamp())
    elif mutation == 'price':
        row['indicators']['quote'][0]['high'][0] = 90
    elif mutation == 'adjustment':
        row['indicators'].pop('adjclose')
    elif mutation == 'length':
        row['indicators']['quote'][0]['volume'].pop()
    elif mutation == 'split':
        row['events'] = {'splits': {'1': {'date': 1609767000, 'numerator': 4}}}
    elif mutation == 'missing':
        row['indicators']['adjclose'][0]['adjclose'] = [None, None]
    elif mutation == 'source':
        with pytest.raises(ValueError, match='SOURCE'):
            parse_yahoo_history(json.dumps(data).encode(), symbol='SPY', source_url='https://evil.example/SPY', retrieved_at=NOW)
        return
    with pytest.raises(ValueError):
        parse(data)


def test_missing_price_row_is_explicit_never_forward_filled():
    data = payload()
    data['chart']['result'][0]['indicators']['quote'][0]['close'][0] = None
    result = parse(data)
    assert len(result.observations) == 1 and len(result.missing_rows) == 1


@pytest.mark.parametrize('data', [[], {'chart': None}, {'chart': {'result': [None]}}])
def test_malformed_top_level_fails_with_stable_error(data):
    with pytest.raises(ValueError):
        parse(data)
