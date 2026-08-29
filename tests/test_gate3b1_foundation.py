from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from meridian.quotes import (
    MarketDataCapabilityCertificate,
    QuoteNormalizer,
    QuoteQualityStatus,
    ShadowMarketDataPolicy,
    StooqQuoteProvider,
    compare_quotes,
)
from meridian.security_master import (
    DEFAULT_SECURITY_MASTER,
    SecurityCertificationStatus,
    SecurityIdentityUnavailable,
    SecurityMaster,
)
from meridian.trading_calendar import (
    TradingCalendarName,
    is_trading_session,
    latest_completed_session,
    session_close,
    session_open,
)

T = datetime(2026, 8, 28, 18, 0, tzinfo=UTC)


def _raw(symbol: str = "aapl.us", **extra: object) -> dict[str, object]:
    return {
        "provider_symbol": symbol,
        "observed_at": datetime(2026, 8, 28, 16, 0, tzinfo=UTC),
        "available_at": datetime(2026, 8, 28, 16, 0, tzinfo=UTC),
        "last": "100.00",
        "currency": "USD",
        **extra,
    }


def test_unknown_security_identity_fails_closed() -> None:
    with pytest.raises(SecurityIdentityUnavailable, match="SECURITY_IDENTITY_UNAVAILABLE"):
        DEFAULT_SECURITY_MASTER.resolve("NOT_A_SECURITY")


def test_vix_alias_is_index_with_distinct_calendar() -> None:
    vix = DEFAULT_SECURITY_MASTER.resolve("^VIX")
    assert vix.canonical_symbol == "VIX"
    assert vix.provider_symbols["yahoo"] == "^VIX"
    assert vix.trading_calendar == TradingCalendarName.CBOE_VIX


def test_wrong_provider_symbol_fails_closed() -> None:
    with pytest.raises(SecurityIdentityUnavailable):
        QuoteNormalizer(DEFAULT_SECURITY_MASTER, max_age_seconds=10000).normalize(
            _raw("MSFT"), symbol="AAPL", provider="stooq", retrieved_at=T
        )


def test_quote_last_only_is_explicitly_not_bid_ask_grade() -> None:
    quote = QuoteNormalizer(DEFAULT_SECURITY_MASTER, max_age_seconds=10000).normalize(
        _raw(), symbol="AAPL", provider="stooq", retrieved_at=T
    )
    assert quote.quality_status is QuoteQualityStatus.BID_ASK_UNAVAILABLE
    assert quote.bid is None and quote.ask is None
    assert quote.executable_quote_grade is False
    assert ShadowMarketDataPolicy.allows_executable_authorization(quote) is False


def test_inverted_bid_ask_rejected() -> None:
    with pytest.raises(ValueError, match="bid"):
        QuoteNormalizer(DEFAULT_SECURITY_MASTER, max_age_seconds=10000).normalize(
            _raw(bid="101", ask="100"), symbol="AAPL", provider="stooq", retrieved_at=T
        )


def test_currency_mismatch_rejected() -> None:
    with pytest.raises(ValueError, match="currency"):
        QuoteNormalizer(DEFAULT_SECURITY_MASTER, max_age_seconds=10000).normalize(
            _raw(currency="EUR"), symbol="AAPL", provider="stooq", retrieved_at=T
        )


def test_future_timestamp_rejected() -> None:
    with pytest.raises(ValueError, match="future"):
        QuoteNormalizer(DEFAULT_SECURITY_MASTER, max_age_seconds=10000).normalize(
            _raw(observed_at=datetime(2026, 8, 28, 19, 0, tzinfo=UTC)),
            symbol="AAPL", provider="stooq", retrieved_at=T
        )


def test_stale_quote_is_marked_stale() -> None:
    quote = QuoteNormalizer(DEFAULT_SECURITY_MASTER, max_age_seconds=60).normalize(
        _raw(observed_at=datetime(2026, 8, 28, 15, 0, tzinfo=UTC)),
        symbol="AAPL", provider="stooq", retrieved_at=T,
    )
    assert quote.quality_status is QuoteQualityStatus.STALE


def test_us_calendar_weekend_holiday_and_dst() -> None:
    assert not is_trading_session(date(2026, 8, 29))
    assert not is_trading_session(date(2026, 7, 3))  # observed Independence Day
    before_dst = session_open(date(2026, 3, 6))
    after_dst = session_open(date(2026, 3, 9))
    assert before_dst.hour == 14 and after_dst.hour == 13
    assert latest_completed_session(datetime(2026, 8, 28, 21, 0, tzinfo=UTC)) == date(2026, 8, 28)
    assert latest_completed_session(datetime(2026, 8, 28, 15, 0, tzinfo=UTC)) == date(2026, 8, 27)
    assert session_close(date(2026, 8, 28), TradingCalendarName.CBOE_VIX).hour == 20


def test_provider_capabilities_default_conservatively() -> None:
    capability = MarketDataCapabilityCertificate(provider_name="unknown")
    assert capability.supports_bid is False
    assert capability.supports_point_in_time is False
    assert capability.execution_quote_grade is False


def test_provider_disagreement_is_explicit_not_averaged() -> None:
    normalizer = QuoteNormalizer(DEFAULT_SECURITY_MASTER)
    a = normalizer.normalize(_raw(last="100"), symbol="AAPL", provider="stooq", retrieved_at=T)
    b = normalizer.normalize(_raw(last="101"), symbol="AAPL", provider="stooq", retrieved_at=T).model_copy(update={"provider": "other"})
    comparison = compare_quotes((a, b), last_tolerance=Decimal("0.10"))
    assert comparison.status is QuoteQualityStatus.MARKET_DATA_CONFLICT
    assert "last" in comparison.differing_fields


def test_security_conflict_downgrades_identity() -> None:
    master = SecurityMaster()
    conflict = master.conflicts
    assert conflict == []
    record = master.resolve("AAPL")
    master.register_conflict(
        __import__("meridian.security_master", fromlist=["SecurityMasterConflict"]).SecurityMasterConflict(
            canonical_symbol="AAPL", conflicting_fields=("currency",), source_a="a", source_b="b",
            observed_at_a=T, observed_at_b=T,
        )
    )
    assert master.lookup("AAPL") is None
    assert record.certification_status is SecurityCertificationStatus.DEVELOPMENT_VERIFIED


def test_shadow_policy_cannot_authorize() -> None:
    quote = QuoteNormalizer(DEFAULT_SECURITY_MASTER, max_age_seconds=10000).normalize(
        _raw(), symbol="AAPL", provider="stooq", retrieved_at=T
    )
    with pytest.raises(ValueError, match="cannot authorize"):
        ShadowMarketDataPolicy.require_non_executable(quote)






def test_quote_during_session_is_incomplete() -> None:
    quote = QuoteNormalizer(DEFAULT_SECURITY_MASTER, max_age_seconds=10000).normalize(
        _raw(observed_at=datetime(2026, 8, 28, 15, 0, tzinfo=UTC)),
        symbol="AAPL", provider="stooq", retrieved_at=T,
    )
    assert quote.market_status.value == "INCOMPLETE"


def test_malformed_public_provider_response_is_explicit() -> None:
    class Response:
        def read(self) -> bytes:
            return b"Symbol,Date,Time,Open,High,Low,Close,Volume\naapl.us,N/D,N/D,N/D,N/D,N/D,N/D,N/D"

    def opener(*args: object, **kwargs: object) -> Response:
        _ = args, kwargs
        return Response()

    with pytest.raises(Exception, match="malformed"):
        StooqQuoteProvider(DEFAULT_SECURITY_MASTER, opener=opener).get_quote("AAPL")



def test_public_provider_timeout_is_explicit() -> None:
    def opener(*args: object, **kwargs: object) -> object:
        _ = args, kwargs
        raise TimeoutError("timeout")

    with pytest.raises(Exception, match="timed out"):
        StooqQuoteProvider(DEFAULT_SECURITY_MASTER, opener=opener).get_quote("AAPL")


def test_development_fixture_is_not_authoritative() -> None:
    with pytest.raises(SecurityIdentityUnavailable, match="authoritative-provenance-required"):
        DEFAULT_SECURITY_MASTER.resolve_authoritative("AAPL")
