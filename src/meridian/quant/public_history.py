"""Retrospective public history receipts, never PIT certification or execution.

Historical availability is explicitly unknown. Provider timestamps describe
sessions, not when this application's historical decision could have known data.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, Field, model_validator

from meridian.quant.experiments import isolated_output
from meridian.quant.integration import immutable_record
from meridian.schemas import StableModel

MAX_BYTES = 10000000


class PublicCorporateAction(StableModel):
    kind: Literal['dividends', 'splits', 'capitalGains']
    date: int = Field(gt=0)
    amount: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    numerator: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    denominator: Decimal | None = Field(default=None, gt=0, allow_inf_nan=False)
    splitRatio: str | None = None

    @model_validator(mode='after')
    def consistent(self) -> PublicCorporateAction:
        if self.kind == 'splits':
            if self.numerator is None or self.denominator is None:
                raise ValueError('PUBLIC_SPLIT_RATIO_MISSING')
        elif self.amount is None:
            raise ValueError('PUBLIC_DISTRIBUTION_AMOUNT_MISSING')
        return self


class PublicPriceObservation(StableModel):
    session: date
    provider_timestamp: AwareDatetime
    open: Decimal = Field(gt=0, allow_inf_nan=False)
    high: Decimal = Field(gt=0, allow_inf_nan=False)
    low: Decimal = Field(gt=0, allow_inf_nan=False)
    close: Decimal = Field(gt=0, allow_inf_nan=False)
    adjusted_close: Decimal = Field(gt=0, allow_inf_nan=False)
    volume: Decimal | None = Field(default=None, ge=0, allow_inf_nan=False)
    historical_available_at: None = None

    @model_validator(mode="after")
    def coherent(self) -> PublicPriceObservation:
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close) or self.high < self.low:
            raise ValueError("PUBLIC_OHLC_INCONSISTENT")
        if self.provider_timestamp.astimezone(ZoneInfo('America/New_York')).date() != self.session:
            raise ValueError("PUBLIC_SESSION_TIMESTAMP_MISMATCH")
        return self


class PublicHistoryReceipt(StableModel):
    version: Literal["public-exploratory-history.v1"] = "public-exploratory-history.v1"
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    evidence_level: Literal["PUBLIC_EXPLORATORY"] = "PUBLIC_EXPLORATORY"
    retrieved_at: AwareDatetime
    source_url: str
    response_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    currency: Literal["USD"] = "USD"
    observations: tuple[PublicPriceObservation, ...] = Field(min_length=1, max_length=10000)
    corporate_actions: tuple[PublicCorporateAction, ...] = Field(default=(), max_length=1000)
    missing_rows: tuple[date, ...] = ()
    source_vintage: Literal["LATEST_RETROSPECTIVE_DOWNLOAD"] = "LATEST_RETROSPECTIVE_DOWNLOAD"
    historical_availability: Literal["UNKNOWN_NOT_MANUFACTURED"] = "UNKNOWN_NOT_MANUFACTURED"
    financial_oos_eligible: Literal[False] = False
    execution_certified: Literal[False] = False
    rights: Literal["PUBLIC_ENDPOINT_NO_CREDENTIALS_RIGHTS_NOT_INDEPENDENTLY_VERIFIED"] = "PUBLIC_ENDPOINT_NO_CREDENTIALS_RIGHTS_NOT_INDEPENDENTLY_VERIFIED"

    @model_validator(mode="after")
    def ordered(self) -> PublicHistoryReceipt:
        source = urlparse(self.source_url)
        if source.scheme != 'https' or source.hostname != 'query1.finance.yahoo.com' or source.path != '/v8/finance/chart/' + self.symbol or source.username or source.password:
            raise ValueError('PUBLIC_SOURCE_IDENTITY_INVALID')
        if set(parse_qs(source.query)) - {'period1', 'period2', 'interval', 'events'}:
            raise ValueError('PUBLIC_SOURCE_QUERY_UNREVIEWED')
        sessions = [r.session for r in self.observations]
        if sessions != sorted(set(sessions)):
            raise ValueError("PUBLIC_DUPLICATE_OR_OUT_OF_SEQUENCE")
        if any(r.provider_timestamp > self.retrieved_at for r in self.observations):
            raise ValueError("PUBLIC_FUTURE_OBSERVATION")
        if self.missing_rows != tuple(sorted(set(self.missing_rows))) or set(self.missing_rows) & set(sessions):
            raise ValueError('PUBLIC_MISSING_SESSION_IDENTITY_INVALID')
        if any(datetime.fromtimestamp(e.date, UTC) > self.retrieved_at for e in self.corporate_actions):
            raise ValueError('PUBLIC_FUTURE_CORPORATE_ACTION')
        return self


def parse_yahoo_history(payload: bytes, *, symbol: str, source_url: str, retrieved_at: datetime) -> PublicHistoryReceipt:
    if retrieved_at.tzinfo is None:
        raise ValueError('PUBLIC_RETRIEVAL_TIMEZONE_REQUIRED')
    if len(payload) > MAX_BYTES:
        raise ValueError("PUBLIC_RESPONSE_TOO_LARGE")
    data = json.loads(payload)
    if not isinstance(data, dict) or not isinstance(data.get('chart'), dict):
        raise ValueError('PUBLIC_RESPONSE_SHAPE_INVALID')
    results = data.get('chart', {}).get('result')
    if not isinstance(results, list) or len(results) != 1:
        raise ValueError("PUBLIC_PROVIDER_RESULT_UNAVAILABLE")
    result = results[0]
    if not isinstance(result, dict):
        raise ValueError('PUBLIC_RESPONSE_SHAPE_INVALID')
    meta = result.get('meta', {})
    if not isinstance(meta, dict):
        raise ValueError('PUBLIC_RESPONSE_SHAPE_INVALID')
    if meta.get('symbol') != symbol or meta.get('currency') != 'USD' or meta.get('exchangeTimezoneName') != 'America/New_York':
        raise ValueError("PUBLIC_SYMBOL_CURRENCY_OR_TIMEZONE_MISMATCH")
    stamps = result.get('timestamp', [])
    indicators = result.get('indicators', {})
    if not isinstance(indicators, dict):
        raise ValueError('PUBLIC_RESPONSE_SHAPE_INVALID')
    quotes, adjrows = indicators.get('quote'), indicators.get('adjclose')
    if not isinstance(quotes, list) or len(quotes) != 1 or not isinstance(quotes[0], dict):
        raise ValueError('PUBLIC_QUOTE_SCHEMA_INVALID')
    quote = quotes[0]
    adjusted = adjrows[0].get('adjclose') if isinstance(adjrows, list) and len(adjrows) == 1 and isinstance(adjrows[0], dict) else None
    if not isinstance(adjusted, list) or not isinstance(stamps, list) or not stamps or len(stamps) > 10000:
        raise ValueError("PUBLIC_ADJUSTED_CLOSE_OR_TIMESTAMPS_MISSING")
    fields: dict[str, list[Any]] = {}
    for name in ('open', 'high', 'low', 'close', 'volume'):
        column = quote.get(name)
        if not isinstance(column, list) or len(column) != len(stamps):
            raise ValueError('PUBLIC_FIELD_LENGTH_MISMATCH')
        fields[name] = column
    if len(adjusted) != len(stamps):
        raise ValueError("PUBLIC_FIELD_LENGTH_MISMATCH")
    observations, missing = [], []
    prior_stamp = 0
    for i, stamp in enumerate(stamps):
        if type(stamp) is not int or stamp <= prior_stamp or stamp > int(retrieved_at.timestamp()):
            raise ValueError('PUBLIC_TIMESTAMP_ORDER_OR_TYPE_INVALID')
        prior_stamp = stamp
        observed = datetime.fromtimestamp(stamp, UTC)
        session = observed.astimezone(ZoneInfo('America/New_York')).date()
        if any(fields[n][i] is None for n in ('open', 'high', 'low', 'close')) or adjusted[i] is None:
            missing.append(session)
            continue
        observations.append(PublicPriceObservation(session=session, provider_timestamp=observed,
            open=Decimal(str(fields['open'][i])), high=Decimal(str(fields['high'][i])),
            low=Decimal(str(fields['low'][i])), close=Decimal(str(fields['close'][i])),
            adjusted_close=Decimal(str(adjusted[i])),
            volume=Decimal(str(fields['volume'][i])) if fields['volume'][i] is not None else None))
    actions = []
    events_by_kind = result.get('events', {})
    if not isinstance(events_by_kind, dict):
        raise ValueError('PUBLIC_CORPORATE_ACTION_SCHEMA_UNKNOWN')
    for kind, events in events_by_kind.items():
        if kind not in {'dividends', 'splits', 'capitalGains'} or not isinstance(events, dict):
            raise ValueError("PUBLIC_CORPORATE_ACTION_SCHEMA_UNKNOWN")
        for event in events.values():
            if not isinstance(event, dict) or 'kind' in event:
                raise ValueError('PUBLIC_CORPORATE_ACTION_SCHEMA_UNKNOWN')
            actions.append(PublicCorporateAction.model_validate({'kind': kind, **event}))
    return PublicHistoryReceipt(symbol=symbol, retrieved_at=retrieved_at, source_url=source_url,
        response_hash=hashlib.sha256(payload).hexdigest(), observations=tuple(observations),
        corporate_actions=tuple(sorted(actions, key=lambda e: (e.date, e.kind))), missing_rows=tuple(missing))


def download_public_history(symbol: str, start: date, end: date, output: Path) -> PublicHistoryReceipt:
    # Validate identity before interpolation. No cookies, tokens or login route.
    import re
    if not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,14}', symbol) or end <= start:
        raise ValueError("PUBLIC_REQUEST_IDENTITY_OR_PERIOD_INVALID")
    output = isolated_output(output)
    params = {'period1': int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp()),
              'period2': int(datetime(end.year, end.month, end.day, tzinfo=UTC).timestamp()),
              'interval': '1d', 'events': 'div,splits,capitalGains'}
    url = 'https://query1.finance.yahoo.com/v8/finance/chart/' + symbol + '?' + urlencode(params)
    with urlopen(Request(url, headers={'User-Agent': 'MeridianAlpha-Research/2.3'}), timeout=15) as response:
        content = response.read(MAX_BYTES + 1)
    receipt = parse_yahoo_history(content, symbol=symbol, source_url=url, retrieved_at=datetime.now(UTC))
    receipt_hash = hashlib.sha256(receipt.stable_json().encode()).hexdigest()
    immutable_record(output / (symbol + '-' + receipt_hash + '.receipt.json'), receipt.stable_json() + '\n')
    # Byte-preserving public response, isolated; no secret/private payloads.
    immutable_record(output / (symbol + '-' + receipt.response_hash + '.source.json'), content.decode('utf-8'))
    return receipt
