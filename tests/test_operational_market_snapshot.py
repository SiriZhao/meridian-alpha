from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from meridian.historical import HistoricalBar, HistoricalBarSeries
from meridian.operational_data import OperationalCache, OperationalRefreshService
from meridian.operational_market_snapshot import OperationalMarketSnapshotService
from meridian.quotes import QuoteObservation, QuoteProviderTimeout
from meridian.schemas import FreshnessState

NOW = datetime(2026, 9, 2, 20, 30, tzinfo=UTC)


class QuoteProvider:
    def __init__(self, name: str, result: QuoteObservation | Exception) -> None:
        self.provider_name = name
        self.result = result

    def get_quote(self, symbol: str, *, as_of: datetime | None = None) -> QuoteObservation:
        _ = symbol, as_of
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class Bars:
    def get_series(
        self, symbol: str, start: date, end: date, *, as_of: datetime, live: bool = False
    ) -> HistoricalBarSeries:
        _ = start, end
        bars = tuple(
            HistoricalBar.model_construct(
                canonical_asset_id=f"US-EQ-{symbol}",
                canonical_symbol=symbol,
                provider_symbol=symbol,
                session=(date(2026, 8, 11) + timedelta(days=day)),
                calendar="US_EQUITY",
                open=Decimal("99"),
                high=Decimal("102"),
                low=Decimal("98"),
                close=Decimal("100"),
                volume=Decimal("1000000"),
                currency="USD",
                adjustment_status="RAW",
                provider="fixture",
                observed_at=datetime(2026, 8, 11, 20, tzinfo=UTC) + timedelta(days=day),
                available_at=datetime(2026, 8, 11, 20, tzinfo=UTC) + timedelta(days=day),
                retrieved_at=NOW,
                source="fixture",
            )
            for day in range(23)
            if (date(2026, 8, 11) + timedelta(days=day)).weekday() < 5
        )
        return HistoricalBarSeries.model_construct(
            canonical_asset_id=f"US-EQ-{symbol}",
            canonical_symbol=symbol,
            provider="fixture",
            as_of=as_of,
            bars=bars,
        )


def observation(price: str = "101") -> QuoteObservation:
    return QuoteObservation(
        canonical_asset_id="US-EQ-AAPL",
        canonical_symbol="AAPL",
        provider="fixture",
        provider_symbol="AAPL",
        observed_at=NOW,
        available_at=NOW,
        retrieved_at=NOW,
        last=Decimal(price),
        currency="USD",
        source="fixture",
    )


def test_primary_with_secondary_failure_builds_provenance_snapshot(tmp_path) -> None:
    refresh = OperationalRefreshService(
        QuoteProvider("primary", observation()),
        QuoteProvider("secondary", QuoteProviderTimeout()),
        cache=OperationalCache(tmp_path),
    )
    result = OperationalMarketSnapshotService(refresh, Bars()).build(["AAPL"], analysis_time=NOW)
    assert result.status == "DATA_DEGRADED"
    assert result.data_quality_mode == "DATA_DEGRADED"
    assert result.quotes["AAPL"].last == Decimal("101")
    assert result.provider_health["AAPL"]["secondary"] == "UNAVAILABLE"
    assert result.data_status()["certification"] == "OPERATIONAL_DATA_IS_NOT_CERTIFIED_RESEARCH"


def test_conflict_and_both_unavailable_fail_closed(tmp_path) -> None:
    conflict = OperationalMarketSnapshotService(
        OperationalRefreshService(
            QuoteProvider("primary", observation("100")),
            QuoteProvider("secondary", observation("110")),
            cache=OperationalCache(tmp_path),
        ),
        Bars(),
    ).build(["AAPL"], analysis_time=NOW)
    assert conflict.missing_symbols["AAPL"] == "MARKET_DATA_CONFLICT"
    unavailable = OperationalMarketSnapshotService(
        OperationalRefreshService(
            QuoteProvider("primary", QuoteProviderTimeout()),
            QuoteProvider("secondary", QuoteProviderTimeout()),
        ),
        Bars(),
    ).build(["AAPL"], analysis_time=NOW)
    assert unavailable.status == "BLOCKED_MARKET_DATA"
    assert unavailable.missing_symbols["AAPL"] == "NETWORK_TIMEOUT"


def test_future_quote_is_never_converted_to_market_snapshot() -> None:
    future = QuoteObservation(
        canonical_asset_id="US-EQ-AAPL",
        canonical_symbol="AAPL",
        provider="fixture",
        provider_symbol="AAPL",
        observed_at=NOW + timedelta(seconds=1),
        available_at=NOW,
        retrieved_at=NOW + timedelta(seconds=1),
        last=Decimal("101"),
        currency="USD",
        source="fixture",
    )
    result = OperationalMarketSnapshotService(
        OperationalRefreshService(
            QuoteProvider("primary", future), QuoteProvider("secondary", QuoteProviderTimeout())
        ),
        Bars(),
    ).build(["AAPL"], analysis_time=NOW)
    assert result.missing_symbols["AAPL"] == "INVALID_RESPONSE"


def test_provider_precision_is_normalized_at_market_snapshot_boundary(tmp_path) -> None:
    class HighPrecisionBars(Bars):
        def get_series(
            self, symbol: str, start: date, end: date, *, as_of: datetime, live: bool = False
        ) -> HistoricalBarSeries:
            series = super().get_series(symbol, start, end, as_of=as_of, live=live)
            bars = tuple(
                bar.model_copy(
                    update={
                        "high": Decimal("331.19000244140625"),
                        "low": Decimal("320.1499938964844"),
                        "close": Decimal("328.2099914550781"),
                    }
                )
                for bar in series.bars
            )
            return series.model_copy(update={"bars": bars})

    refresh = OperationalRefreshService(
        QuoteProvider("primary", observation("329.123456789")),
        QuoteProvider("secondary", QuoteProviderTimeout()),
        cache=OperationalCache(tmp_path),
    )
    result = OperationalMarketSnapshotService(refresh, HighPrecisionBars()).build(
        ["AAPL"], analysis_time=NOW
    )

    assert result.missing_symbols == {}
    assert result.quotes["AAPL"].last == Decimal("329.1235")
    assert result.quotes["AAPL"].previous_close == Decimal("328.2100")
    assert result.quotes["AAPL"].atr14 == Decimal("11.0400")


def test_last_completed_session_quote_is_research_only(tmp_path) -> None:
    analysis_time = datetime(2026, 9, 2, 23, tzinfo=UTC)
    close = observation().model_copy(
        update={
            "observed_at": datetime(2026, 9, 2, 20, tzinfo=UTC),
            "available_at": datetime(2026, 9, 2, 20, tzinfo=UTC),
            "retrieved_at": datetime(2026, 9, 2, 20, 1, tzinfo=UTC),
        }
    )
    result = OperationalMarketSnapshotService(
        OperationalRefreshService(
            QuoteProvider("primary", close),
            QuoteProvider("secondary", QuoteProviderTimeout()),
            cache=OperationalCache(tmp_path),
        ),
        Bars(),
    ).build(["AAPL"], analysis_time=analysis_time)

    assert result.quotes == {}
    assert result.missing_symbols["AAPL"] == "MARKET_DATA_STALE"
    assert result.research_quotes["AAPL"].freshness_state is FreshnessState.STALE
    assert result.provider_probes["AAPL"]["research_selection"] == (
        "LAST_COMPLETED_SESSION_ONLY"
    )
