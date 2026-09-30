from datetime import UTC, datetime, timedelta
from decimal import Decimal

from meridian.market_identity import (
    MarketConsistencyStatus,
    canonical_market_reference,
    compare_market_snapshots,
)
from meridian.schemas import FreshnessState, MarketSnapshot

NOW = datetime(2026, 9, 16, 15, 0, tzinfo=UTC)


def quote(price: str, *, observed_at: datetime = NOW) -> MarketSnapshot:
    return MarketSnapshot(
        ticker="AAPL",
        timestamp=observed_at,
        last=Decimal(price),
        previous_close=Decimal("198"),
        volume=1_000_000,
        daily_return=Decimal("0.01"),
        freshness_state=FreshnessState.VERIFIED,
    )


def test_market_reference_ignores_operational_timestamp_churn() -> None:
    first = {"AAPL": quote("200", observed_at=NOW)}
    second = {"AAPL": quote("200", observed_at=NOW + timedelta(seconds=5))}
    assert canonical_market_reference(first) == canonical_market_reference(second)
    assert compare_market_snapshots(first, second).status is MarketConsistencyStatus.EXACT


def test_small_price_move_is_explicitly_revalidated() -> None:
    result = compare_market_snapshots({"AAPL": quote("200")}, {"AAPL": quote("200.50")})
    assert result.status is MarketConsistencyStatus.REVALIDATED
    assert result.old_reference != result.new_reference
    assert result.max_price_change_fraction == 0.0025


def test_material_price_move_requires_research_refresh() -> None:
    result = compare_market_snapshots({"AAPL": quote("200")}, {"AAPL": quote("204")})
    assert result.status is MarketConsistencyStatus.REFRESH_REQUIRED
    assert result.reason == "PRICE_MOVE_EXCEEDS_REVALIDATION_POLICY"


def test_symbol_universe_change_requires_research_refresh() -> None:
    result = compare_market_snapshots(
        {"AAPL": quote("200")},
        {"AAPL": quote("200"), "MSFT": quote("200")},
    )
    assert result.status is MarketConsistencyStatus.REFRESH_REQUIRED
    assert result.reason == "SYMBOL_UNIVERSE_CHANGED"
