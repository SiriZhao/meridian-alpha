"""Explicitly synthetic engineering data; never market or financial evidence."""

import math
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache

from meridian.config import RiskPolicy
from meridian.historical import (
    HistoricalAdjustmentStatus,
    HistoricalBar,
    HistoricalBarCertification,
    HistoricalBarSeries,
    HistoricalQuality,
)
from meridian.quant.backtest import (
    QuantDataset,
    QuantSecurityMetadata,
    UniverseMembership,
    WalkForwardFold,
)
from meridian.trading_calendar import TradingCalendarName, is_trading_session, session_close

D = Decimal


@lru_cache(maxsize=4)
def synthetic_dataset(count: int = 420) -> QuantDataset:
    sessions = []
    cursor = date(2020, 1, 2)
    while len(sessions) < count:
        if is_trading_session(cursor):
            sessions.append(cursor)
        cursor += timedelta(days=1)
    retrieved = session_close(sessions[-1]) + timedelta(hours=1)
    series = []
    for index, symbol in enumerate(("AAPL", "MSFT", "NVDA", "QQQ", "GLD", "SPY")):
        bars = []
        price = D(70 + 20 * index)
        for i, session in enumerate(sessions):
            shock = -0.018 if 288 <= i < 306 else 0.007 if 310 <= i < 329 else 0.0
            change = D(str(.0004 + index * .00007 + .006 * math.sin(i * .47 + index) + shock))
            opening = price * (1 + D(str(.0015 * math.cos(i * .3 + index))))
            close = price * (1 + change)
            bars.append(HistoricalBar(canonical_asset_id="SYNTHETIC-" + symbol,
                                      canonical_symbol=symbol, provider_symbol=symbol,
                                      session=session, calendar=TradingCalendarName.US_EQUITY,
                                      open=opening, close=close, high=max(opening, close) * D("1.003"),
                                      low=min(opening, close) * D(".997"), volume=D(1000000 + 100000 * index),
                                      currency="USD", adjustment_status=HistoricalAdjustmentStatus.FULLY_ADJUSTED_OHLCV, provider="synthetic-diagnostic",
                                      observed_at=session_close(session), available_at=session_close(session),
                                      retrieved_at=retrieved, source="ENGINEERING_FIXTURE_NOT_REAL_MARKET_DATA",
                                      quality=HistoricalQuality.VERIFIED, certification=HistoricalBarCertification.SYNTHETIC))
            price = close
        series.append(HistoricalBarSeries(canonical_asset_id="SYNTHETIC-" + symbol, canonical_symbol=symbol,
                                          provider="synthetic-diagnostic", bars=tuple(bars), as_of=retrieved,
                                          source_mode="SYNTHETIC_DIAGNOSTIC"))
    memberships = tuple(UniverseMembership(symbol=s.canonical_symbol, start=sessions[0],
                                           known_at=session_close(sessions[0]) - timedelta(days=1),
                                           source="PREDECLARED_SYNTHETIC_TEST_UNIVERSE") for s in series if s.canonical_symbol != "SPY")
    metadata = tuple(QuantSecurityMetadata(symbol=s.canonical_symbol, asset_type="EQUITY" if i < 3 else "DIVERSIFIED_ETF",
                                           sector="SYNTHETIC_SECTOR" if i < 3 else None,
                                           known_at=memberships[0].known_at, source="SYNTHETIC_METADATA_NOT_ACTUAL_SECTORS")
                     for i, s in enumerate(series))
    return QuantDataset(series=tuple(series), memberships=memberships, evidence_status="SYNTHETIC_DIAGNOSTIC", security_metadata=metadata,
                        corporate_actions_covered_until=sessions[-1], corporate_action_source="SYNTHETIC_NO_ACTIONS_BY_CONSTRUCTION",
                        universe_basis="PREDECLARED_STATIC", description="Synthetic deterministic timing/risk diagnostic. No historical investment evidence.")


def folds(dataset: QuantDataset) -> tuple[WalkForwardFold, ...]:
    sessions = [b.session for b in dataset.series[0].bars]
    return tuple(WalkForwardFold(name="fold-" + str(i + 1), train_start=sessions[0], train_end=sessions[a],
                                 validation_start=sessions[a + 2], validation_end=sessions[b],
                                 test_start=sessions[b + 2], test_end=sessions[c])
                 for i, (a, b, c) in enumerate(((252, 279, 329), (329, 349, 409))))


def risk_policy() -> RiskPolicy:
    return RiskPolicy(max_position_weight=D("0.25"), max_sector_weight=D("0.5"), min_cash_weight=D("0.10"),
                      max_number_positions=5, max_daily_turnover=D("0.2"), max_single_order_nav_percent=D("0.05"))


def histories(dataset: QuantDataset) -> dict[str, HistoricalBarSeries]:
    return {s.canonical_symbol: s for s in dataset.series}


def cutoff(dataset: QuantDataset, index: int = 279) -> datetime:
    return session_close(dataset.series[0].bars[index].session)
