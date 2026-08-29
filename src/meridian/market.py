"""Provider-neutral market data contracts and point-in-time features."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from meridian.schemas import MarketSnapshot


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("bar timestamp must be timezone-aware")
        if self.open < 0 or self.high < 0 or self.low < 0 or self.close < 0 or self.volume < 0:
            raise ValueError("bar values must be non-negative")


class MarketDataProvider(Protocol):
    provider_name: str

    def get_quote(self, ticker: str) -> MarketSnapshot: ...
    def get_history(
        self, ticker: str, start: datetime, end: datetime, interval: str
    ) -> tuple[Bar, ...]: ...
    def get_market_snapshot(self, ticker: str, as_of: datetime) -> MarketSnapshot: ...
    def get_benchmark_snapshot(self) -> MarketSnapshot: ...
    def get_volatility_context(self) -> dict[str, Decimal]: ...


def point_in_time_bars(bars: tuple[Bar, ...], as_of: datetime) -> tuple[Bar, ...]:
    """The sole feature input gate: never return a bar later than `as_of`."""
    return tuple(bar for bar in bars if bar.timestamp <= as_of)


def simple_moving_average(bars: tuple[Bar, ...], window: int) -> Decimal | None:
    if len(bars) < window:
        return None
    return sum((bar.close for bar in bars[-window:]), Decimal("0")) / Decimal(window)


def rsi14(bars: tuple[Bar, ...]) -> Decimal | None:
    if len(bars) < 15:
        return None
    changes = [bars[index].close - bars[index - 1].close for index in range(1, len(bars))]
    gains = sum((max(change, Decimal("0")) for change in changes[-14:]), Decimal("0")) / Decimal(14)
    losses = sum((max(-change, Decimal("0")) for change in changes[-14:]), Decimal("0")) / Decimal(
        14
    )
    if losses == 0:
        return Decimal("100")
    return Decimal("100") - (Decimal("100") / (Decimal("1") + gains / losses))


def atr14(bars: tuple[Bar, ...]) -> Decimal | None:
    if len(bars) < 15:
        return None
    ranges = [
        max(
            bar.high - bar.low,
            abs(bar.high - bars[index - 1].close),
            abs(bar.low - bars[index - 1].close),
        )
        for index, bar in enumerate(bars[1:], start=1)
    ]
    return sum(ranges[-14:], Decimal("0")) / Decimal(14)


def feature_set(bars: tuple[Bar, ...], as_of: datetime) -> dict[str, Decimal | None]:
    eligible = point_in_time_bars(bars, as_of)
    if len(eligible) < 2:
        return {
            "sma20": None,
            "sma50": None,
            "rsi14": None,
            "atr14": None,
            "daily_return": None,
            "realized_volatility": None,
            "volume_ratio": None,
            "gap_percent": None,
            "vwap": None,
        }
    returns = [
        (bar.close / eligible[index - 1].close) - 1
        for index, bar in enumerate(eligible[1:], start=1)
    ]
    realized = None
    if len(returns) >= 2:
        mean = sum(returns, Decimal("0")) / Decimal(len(returns))
        realized = (
            sum(((value - mean) ** 2 for value in returns), Decimal("0")) / Decimal(len(returns))
        ) ** Decimal("0.5")
    recent = eligible[-20:]
    average_volume = sum((bar.volume for bar in recent), 0) / len(recent)
    last = eligible[-1]
    previous = eligible[-2]
    vwap_numerator = sum((bar.close * Decimal(bar.volume) for bar in recent), Decimal("0"))
    vwap_denominator = sum((bar.volume for bar in recent), 0)
    return {
        "sma20": simple_moving_average(eligible, 20),
        "sma50": simple_moving_average(eligible, 50),
        "rsi14": rsi14(eligible),
        "atr14": atr14(eligible),
        "daily_return": (last.close / previous.close) - 1,
        "realized_volatility": realized,
        "volume_ratio": Decimal(last.volume) / Decimal(str(average_volume))
        if average_volume
        else None,
        "gap_percent": (last.open / previous.close) - 1,
        "vwap": vwap_numerator / Decimal(vwap_denominator) if vwap_denominator else None,
    }


class FakeMarketDataProvider:
    provider_name = "fake"

    def __init__(
        self,
        snapshots: dict[str, MarketSnapshot],
        histories: dict[str, tuple[Bar, ...]] | None = None,
    ) -> None:
        self.snapshots = snapshots
        self.histories = histories or {}

    def get_quote(self, ticker: str) -> MarketSnapshot:
        return self.snapshots[ticker]

    def get_history(
        self, ticker: str, start: datetime, end: datetime, interval: str
    ) -> tuple[Bar, ...]:
        return tuple(bar for bar in self.histories.get(ticker, ()) if start <= bar.timestamp <= end)

    def get_market_snapshot(self, ticker: str, as_of: datetime) -> MarketSnapshot:
        quote = self.get_quote(ticker)
        if quote.timestamp > as_of:
            raise ValueError("quote is after analysis time")
        return quote

    def get_benchmark_snapshot(self) -> MarketSnapshot:
        return self.get_quote("SPY")

    def get_volatility_context(self) -> dict[str, Decimal]:
        return {"regime_volatility": Decimal("0.15")}


class HistoricalCache:
    """Cache keys include all required identity dimensions."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def key(
        self, *, ticker: str, interval: str, start: datetime, end: datetime, provider: str
    ) -> str:
        raw = json.dumps(
            {
                "ticker": ticker,
                "interval": interval,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "provider": provider,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()


class YFinanceProvider:
    """Development-only provider. It is never a guaranteed real-time source."""

    provider_name = "yfinance-development"

    def get_quote(self, ticker: str) -> MarketSnapshot:
        raise NotImplementedError("YFinanceProvider is intentionally not enabled in the safe MVP")

    def get_history(
        self, ticker: str, start: datetime, end: datetime, interval: str
    ) -> tuple[Bar, ...]:
        raise NotImplementedError("YFinanceProvider is intentionally not enabled in the safe MVP")

    def get_market_snapshot(self, ticker: str, as_of: datetime) -> MarketSnapshot:
        return self.get_quote(ticker)

    def get_benchmark_snapshot(self) -> MarketSnapshot:
        return self.get_quote("SPY")

    def get_volatility_context(self) -> dict[str, Decimal]:
        return {}
