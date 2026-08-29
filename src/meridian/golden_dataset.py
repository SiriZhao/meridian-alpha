"""Small deterministic validation universe for historical shadow tests.

These rows are synthetic fixtures and are intentionally not presented as
market facts.  They exercise identity, calendar and adjustment plumbing for
the representative instruments without freezing a large data set.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TypedDict

GOLDEN_UNIVERSE = ("AAPL", "MSFT", "NVDA", "SPY", "QQQ", "GLD", "SGOV", "VIX")


class GoldenBar(TypedDict):
    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    adjustment_status: str


def synthetic_golden_bars() -> dict[str, tuple[GoldenBar, ...]]:
    """Return one bounded synthetic session per representative identity."""
    result: dict[str, tuple[GoldenBar, ...]] = {}
    for index, ticker in enumerate(GOLDEN_UNIVERSE, start=1):
        close = Decimal("100") + Decimal(index)
        result[ticker] = (
            {
                "session": date(2026, 8, 28),
                "open": close - Decimal("1"),
                "high": close + Decimal("1"),
                "low": close - Decimal("2"),
                "close": close,
                "volume": Decimal("1000"),
                "adjustment_status": "RAW",
            },
        )
    return result


KNOWN_ACTION_EXAMPLES = {
    "AAPL_SPLIT": {"ticker": "AAPL", "action": "SPLIT", "event_date": date(2020, 8, 31)},
    "AAPL_DIVIDEND": {"ticker": "AAPL", "action": "CASH_DIVIDEND", "event_date": date(2026, 8, 28)},
}

