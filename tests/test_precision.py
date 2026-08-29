from datetime import UTC, datetime
from decimal import Decimal

from meridian.config import load_policies
from meridian.orders import LimitPriceEngine
from meridian.schemas import FreshnessState, MarketSnapshot, RunStatus, Side


def test_derived_limit_is_validated_and_quantized_to_money_precision() -> None:
    quote = MarketSnapshot(
        ticker="AAPL",
        timestamp=datetime(2026, 8, 28, tzinfo=UTC),
        last=Decimal("200.1234"),
        bid=Decimal("200.1233"),
        ask=Decimal("200.1234"),
        previous_close=Decimal("200.0000"),
        volume=1,
        atr14=Decimal("1.0000"),
        vwap=Decimal("200.1234"),
        daily_return=Decimal("0"),
        freshness_state=FreshnessState.VERIFIED,
    )
    policy = load_policies(__import__("pathlib").Path(__file__).parents[1] / "policies").execution
    result = LimitPriceEngine().calculate(Side.BUY, quote, policy)
    assert result.status is RunStatus.READY_FOR_MANUAL_ENTRY
    assert result.max_acceptable_buy_price == Decimal("202.1246")
