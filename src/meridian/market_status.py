"""NYSE session classification for operator-facing runtime decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum

from meridian.trading_calendar import (
    NEW_YORK,
    is_trading_session,
    session_context,
    us_market_holidays,
)


class MarketStatus(StrEnum):
    OPEN = "OPEN"
    PRE_MARKET = "PRE_MARKET"
    AFTER_HOURS = "AFTER_HOURS"
    CLOSED = "CLOSED"
    HOLIDAY = "HOLIDAY"


@dataclass(frozen=True)
class MarketStatusReport:
    status: MarketStatus
    exchange: str
    observed_at: str
    local_time: str
    trading_date: str
    next_action: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def market_status(as_of: datetime) -> MarketStatusReport:
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("MARKET_STATUS_TIMEZONE_REQUIRED")
    local = as_of.astimezone(NEW_YORK)
    if not is_trading_session(local):
        status = MarketStatus.HOLIDAY if local.weekday() < 5 and local.date() in us_market_holidays(local.year) else MarketStatus.CLOSED
    else:
        context = session_context(as_of)
        status = {
            "REGULAR": MarketStatus.OPEN,
            "PRE_MARKET": MarketStatus.PRE_MARKET,
            "AFTER_HOURS": MarketStatus.AFTER_HOURS,
        }.get(context, MarketStatus.CLOSED)
    action = (
        "Fresh regular-session data may support paper-only execution; all gates still apply."
        if status is MarketStatus.OPEN
        else "Run in safe-analysis mode; do not create paper fills from stale or closed-session prices."
    )
    return MarketStatusReport(
        status=status,
        exchange="NYSE",
        observed_at=as_of.isoformat(),
        local_time=local.isoformat(),
        trading_date=local.date().isoformat(),
        next_action=action,
    )