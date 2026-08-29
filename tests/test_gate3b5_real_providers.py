import json
from datetime import UTC, date, datetime

import pytest

from meridian.historical import (
    HistoricalBarCertification,
    HistoricalProviderMalformed,
    YahooChartHistoricalProvider,
)
from meridian.quotes import QuoteProviderMalformed, YahooChartQuoteProvider
from meridian.real_shadow import YahooMarketEvidenceProvider
from meridian.security_master import DEFAULT_SECURITY_MASTER

AS_OF = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


class _Response:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode()
        self.status = 200

    def read(self) -> bytes:
        return self.payload


def _chart_payload(*, malformed: bool = False) -> dict[str, object]:
    if malformed:
        return {"chart": {"result": []}}
    return {
        "chart": {
            "result": [
                {
                    "meta": {"currency": "USD", "symbol": "AAPL", "regularMarketPrice": 101.0, "regularMarketTime": 1787947200},
                    "timestamp": [1787860800, 1787947200],
                    "indicators": {
                        "quote": [{"open": [None, 100.0], "high": [None, 102.0], "low": [None, 99.0], "close": [None, 101.0], "volume": [None, 1000]}],
                    },
                }
            ]
        }
    }


def test_yahoo_quote_normalizes_last_only_and_shadow_capabilities() -> None:
    provider = YahooChartQuoteProvider(
        DEFAULT_SECURITY_MASTER,
        opener=lambda *args, **kwargs: _Response(_chart_payload()),
        clock=lambda: AS_OF,
    )
    quote = provider.get_quote("AAPL", as_of=AS_OF)
    assert quote.provider_symbol == "AAPL"
    assert quote.last == 101
    assert quote.bid is None and quote.ask is None
    assert quote.executable_quote_grade is False
    assert provider.capabilities.supports_last is True
    assert provider.capabilities.supports_bid is False


def test_yahoo_quote_malformed_response_is_explicit() -> None:
    provider = YahooChartQuoteProvider(
        DEFAULT_SECURITY_MASTER,
        opener=lambda *args, **kwargs: _Response(_chart_payload(malformed=True)),
        clock=lambda: AS_OF,
    )
    with pytest.raises(QuoteProviderMalformed):
        provider.get_quote("AAPL", as_of=AS_OF)


def test_yahoo_historical_skips_missing_rows_without_imputation() -> None:
    provider = YahooChartHistoricalProvider(
        DEFAULT_SECURITY_MASTER,
        opener=lambda *args, **kwargs: _Response(_chart_payload()),
        clock=lambda: AS_OF,
    )
    series = provider.get_series("AAPL", date(2026, 8, 27), date(2026, 8, 29), as_of=AS_OF)
    assert len(series.bars) == 1
    assert series.source_mode == "LIVE_SHADOW"
    assert series.bars[0].certification is HistoricalBarCertification.UNVERIFIED
    assert series.bars[0].adjustment_status.value == "RAW"


def test_yahoo_historical_malformed_response_is_explicit() -> None:
    provider = YahooChartHistoricalProvider(
        DEFAULT_SECURITY_MASTER,
        opener=lambda *args, **kwargs: _Response(_chart_payload(malformed=True)),
        clock=lambda: AS_OF,
    )
    with pytest.raises(HistoricalProviderMalformed):
        provider.get_series("AAPL", date(2026, 8, 27), date(2026, 8, 29), as_of=AS_OF)


def test_real_market_evidence_is_unverified_and_not_executable() -> None:
    quote_provider = YahooChartQuoteProvider(
        DEFAULT_SECURITY_MASTER,
        opener=lambda *args, **kwargs: _Response(_chart_payload()),
        clock=lambda: AS_OF,
    )
    item = YahooMarketEvidenceProvider(quote_provider).get_evidence("AAPL", AS_OF)[0]
    assert item.provider == "yahoo-market"
    assert item.point_in_time_status.value == "UNVERIFIED"
    assert item.available_at is not None and item.available_at <= AS_OF
