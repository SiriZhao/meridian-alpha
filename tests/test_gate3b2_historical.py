from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from meridian.corporate_actions import (
    CorporateActionEvent,
    CorporateActionPITStatus,
    CorporateActionType,
    FirstSeenLedger,
)
from meridian.golden_dataset import GOLDEN_UNIVERSE, synthetic_golden_bars
from meridian.historical import (
    HistoricalAdjustmentStatus,
    HistoricalBarCertification,
    HistoricalDataNormalizer,
    HistoricalQuality,
    compare_historical_series,
    generate_shadow_features,
    inspect_series,
)
from meridian.security_master import DEFAULT_SECURITY_MASTER

RETRIEVED = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
AS_OF = datetime(2026, 8, 28, 23, 0, tzinfo=UTC)


def _row(session: str = "2026-08-28", **updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "provider_symbol": "aapl.us",
        "session": session,
        "observed_at": f"{session}T21:00:00+00:00",
        "available_at": f"{session}T21:00:00+00:00",
        "open": "100",
        "high": "105",
        "low": "99",
        "close": "104",
        "volume": "1000",
        "currency": "USD",
        "source": "fixture",
    }
    value.update(updates)
    return value


def test_historical_bar_normalization_and_raw_execution_boundary() -> None:
    series = HistoricalDataNormalizer(DEFAULT_SECURITY_MASTER, provider="stooq").normalize(
        [_row()], symbol="AAPL", as_of=AS_OF, retrieved_at=RETRIEVED,
        adjustment_status=HistoricalAdjustmentStatus.RAW,
        certification=HistoricalBarCertification.CERTIFIED_MARKET_SESSION,
        quality=HistoricalQuality.VERIFIED,
    )
    assert series.bars[0].execution_price_eligible is False
    assert series.bars[0].session == date(2026, 8, 28)
    assert series.content_hash is not None
    repeat = HistoricalDataNormalizer(DEFAULT_SECURITY_MASTER, provider="stooq").normalize(
        [_row()], symbol="AAPL", as_of=AS_OF, retrieved_at=RETRIEVED,
        adjustment_status=HistoricalAdjustmentStatus.RAW,
        certification=HistoricalBarCertification.CERTIFIED_MARKET_SESSION,
        quality=HistoricalQuality.VERIFIED,
    )
    assert repeat.content_hash == series.content_hash


def test_impossible_ohlc_and_future_session_rejected() -> None:
    normalizer = HistoricalDataNormalizer(DEFAULT_SECURITY_MASTER, provider="stooq")
    with pytest.raises(ValueError, match="high"):
        normalizer.normalize([_row(high="98")], symbol="AAPL", as_of=AS_OF, retrieved_at=RETRIEVED)
    with pytest.raises(ValueError, match="after as_of"):
        normalizer.normalize([_row("2026-08-29")], symbol="AAPL", as_of=AS_OF, retrieved_at=RETRIEVED)


def test_weekend_session_and_wrong_symbol_fail_closed() -> None:
    normalizer = HistoricalDataNormalizer(DEFAULT_SECURITY_MASTER, provider="stooq")
    with pytest.raises(ValueError, match="trading session"):
        normalizer.normalize([_row("2026-08-29")], symbol="AAPL", as_of=datetime(2026, 9, 1, tzinfo=UTC), retrieved_at=datetime(2026, 9, 1, tzinfo=UTC))
    with pytest.raises(Exception, match="SECURITY_IDENTITY_UNAVAILABLE"):
        normalizer.normalize([_row(provider_symbol="msft.us")], symbol="AAPL", as_of=AS_OF, retrieved_at=RETRIEVED)


def test_adjusted_prices_are_explicitly_non_execution() -> None:
    series = HistoricalDataNormalizer(DEFAULT_SECURITY_MASTER, provider="stooq").normalize(
        [_row()], symbol="AAPL", as_of=AS_OF, retrieved_at=RETRIEVED,
        adjustment_status=HistoricalAdjustmentStatus.ADJUSTED_CLOSE,
    )
    assert series.bars[0].adjustment_status is HistoricalAdjustmentStatus.ADJUSTED_CLOSE
    assert series.bars[0].execution_price_eligible is False


def test_quality_missing_sessions_and_provider_conflict() -> None:
    normalizer = HistoricalDataNormalizer(DEFAULT_SECURITY_MASTER, provider="stooq")
    first = normalizer.normalize([_row()], symbol="AAPL", as_of=AS_OF, retrieved_at=RETRIEVED)
    second = normalizer.normalize([_row(close="104", high="107")], symbol="AAPL", as_of=AS_OF, retrieved_at=RETRIEVED)
    diagnostics = inspect_series(first, expected_sessions=(date(2026, 8, 27),))
    assert diagnostics.missing_sessions
    assert diagnostics.coverage_ratio == Decimal("0")
    comparison = compare_historical_series((first, second))
    assert comparison.status == "MARKET_DATA_CONFLICT"
    assert "high" in comparison.differing_fields


def test_shadow_features_are_lineaged_and_cutoff_bounded() -> None:
    normalizer = HistoricalDataNormalizer(DEFAULT_SECURITY_MASTER, provider="stooq")
    series = normalizer.normalize(
        [_row("2026-08-27"), _row("2026-08-28")], symbol="AAPL", as_of=AS_OF, retrieved_at=RETRIEVED
    )
    features, lineage = generate_shadow_features(series, AS_OF)
    assert lineage.source_mode == "REPLAY"
    assert len(lineage.sessions_used) == 2
    assert features["daily_return"] is not None


def test_corporate_action_requires_known_at_for_historical_pit() -> None:
    with pytest.raises(ValueError, match="announcement_at"):
        CorporateActionEvent(
            canonical_asset_id="US-EQ-AAPL", canonical_symbol="AAPL",
            action_type=CorporateActionType.SPLIT, event_date=date(2020, 8, 31),
            provider="fixture", source="fixture", first_seen_at=RETRIEVED,
            pit_status=CorporateActionPITStatus.CERTIFIED_HISTORICAL_PIT,
        )
    event = CorporateActionEvent(
        canonical_asset_id="US-EQ-AAPL", canonical_symbol="AAPL",
        action_type=CorporateActionType.CASH_DIVIDEND, event_date=date(2026, 8, 28),
        announcement_at=datetime(2026, 8, 1, tzinfo=UTC), value=Decimal("0.25"), currency="USD",
        provider="fixture", source="fixture", first_seen_at=RETRIEVED,
        pit_status=CorporateActionPITStatus.CERTIFIED_HISTORICAL_PIT,
    )
    assert event.available_for(AS_OF) is True


def test_first_seen_ledger_never_backdates() -> None:
    clock_now = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
    event = CorporateActionEvent(
        canonical_asset_id="US-EQ-AAPL", canonical_symbol="AAPL",
        action_type=CorporateActionType.SPLIT, event_date=date(2020, 8, 31),
        announcement_at=datetime(2020, 8, 1, tzinfo=UTC), ratio=Decimal("4"),
        provider="fixture", source="fixture", first_seen_at=datetime(2020, 8, 1, tzinfo=UTC),
        pit_status=CorporateActionPITStatus.LIVE_FORWARD_FIRST_SEEN,
    )
    row = FirstSeenLedger(clock=lambda: clock_now).record(event)
    assert row.first_seen_at == clock_now
    assert row.first_seen_at > event.first_seen_at





def test_future_available_at_and_late_announcement_cannot_enter_cutoff() -> None:
    normalizer = HistoricalDataNormalizer(DEFAULT_SECURITY_MASTER, provider="stooq")
    with pytest.raises(ValueError, match="after as_of"):
        normalizer.normalize(
            [_row(available_at="2026-08-29T00:00:00+00:00")],
            symbol="AAPL", as_of=AS_OF, retrieved_at=RETRIEVED,
        )
    event = CorporateActionEvent(
        canonical_asset_id="US-EQ-AAPL", canonical_symbol="AAPL",
        action_type=CorporateActionType.CASH_DIVIDEND, event_date=date(2026, 8, 28),
        announcement_at=datetime(2026, 8, 29, tzinfo=UTC), value=Decimal("0.25"), currency="USD",
        provider="fixture", source="fixture", first_seen_at=RETRIEVED,
        pit_status=CorporateActionPITStatus.CERTIFIED_HISTORICAL_PIT,
    )
    assert event.available_for(AS_OF) is False


def test_incomplete_current_session_excluded_from_shadow_features() -> None:
    normalizer = HistoricalDataNormalizer(DEFAULT_SECURITY_MASTER, provider="stooq")
    series = normalizer.normalize(
        [_row("2026-08-27"), _row("2026-08-28", available_at="2026-08-28T17:00:00+00:00")],
        symbol="AAPL", as_of=AS_OF, retrieved_at=RETRIEVED,
    )
    _, lineage = generate_shadow_features(series, datetime(2026, 8, 28, 18, 0, tzinfo=UTC))
    assert lineage.sessions_used == (date(2026, 8, 27),)


def test_certified_market_bar_requires_verified_quality() -> None:
    with pytest.raises(ValueError, match="VERIFIED quality"):
        HistoricalDataNormalizer(DEFAULT_SECURITY_MASTER, provider="stooq").normalize(
            [_row()], symbol="AAPL", as_of=AS_OF, retrieved_at=RETRIEVED,
            certification=HistoricalBarCertification.CERTIFIED_MARKET_SESSION,
            quality=HistoricalQuality.UNVERIFIED,
        )


def test_golden_universe_is_bounded_and_identity_complete() -> None:
    assert len(GOLDEN_UNIVERSE) == 8
    fixtures = synthetic_golden_bars()
    assert tuple(fixtures) == GOLDEN_UNIVERSE
    assert all(DEFAULT_SECURITY_MASTER.lookup(ticker) is not None for ticker in GOLDEN_UNIVERSE)

