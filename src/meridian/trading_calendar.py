"""Deterministic US equity and CBOE VIX session calendar semantics."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo


class TradingCalendarName(StrEnum):
    US_EQUITY = "US_EQUITY"
    CBOE_VIX = "CBOE_VIX"


NEW_YORK = ZoneInfo("America/New_York")


def _observed_fixed_holiday(year: int, month: int, day: int) -> date:
    value = date(year, month, day)
    if value.weekday() == 5:
        return value - timedelta(days=1)
    if value.weekday() == 6:
        return value + timedelta(days=1)
    return value


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    next_month = date(year + (month == 12), month % 12 + 1, 1)
    candidate = next_month - timedelta(days=1)
    return candidate - timedelta(days=(candidate.weekday() - weekday) % 7)


def us_market_holidays(year: int, calendar: TradingCalendarName = TradingCalendarName.US_EQUITY) -> frozenset[date]:
    """Return the major NYSE/CBOE full-day holidays for a year.

    The set intentionally uses only deterministic exchange-wide holidays; an
    early-close schedule is represented by the session close policy rather
    than pretending it is a full holiday.
    """
    holidays = {
        _observed_fixed_holiday(year, 1, 1),
        _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),  # Presidents' Day
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed_fixed_holiday(year, 6, 19),  # Juneteenth
        _observed_fixed_holiday(year, 7, 4),
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed_fixed_holiday(year, 12, 25),
    }
    # Good Friday is a full close for both NYSE and CBOE.  Compute Easter
    # Sunday with the Gregorian algorithm without adding a dependency.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    easter_weekday_offset = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * easter_weekday_offset) // 451
    easter = date(year, (h + easter_weekday_offset - 7 * m + 114) // 31, (h + easter_weekday_offset - 7 * m + 114) % 31 + 1)
    holidays.add(easter - timedelta(days=2))
    _ = calendar
    return frozenset(holidays)


def _coerce_local(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("calendar datetime must be timezone-aware")
        return value.astimezone(NEW_YORK)
    return datetime.combine(value, time.min, tzinfo=NEW_YORK)


def is_trading_session(value: date | datetime, calendar: TradingCalendarName = TradingCalendarName.US_EQUITY) -> bool:
    local = _coerce_local(value)
    return local.weekday() < 5 and local.date() not in us_market_holidays(local.year, calendar)


def session_open(value: date | datetime, calendar: TradingCalendarName = TradingCalendarName.US_EQUITY) -> datetime:
    local = _coerce_local(value)
    return datetime.combine(local.date(), time(9, 30), tzinfo=NEW_YORK).astimezone(UTC)


def session_close(value: date | datetime, calendar: TradingCalendarName = TradingCalendarName.US_EQUITY) -> datetime:
    local = _coerce_local(value)
    close_time = time(16, 15) if calendar is TradingCalendarName.CBOE_VIX else time(16, 0)
    return datetime.combine(local.date(), close_time, tzinfo=NEW_YORK).astimezone(UTC)


def latest_completed_session(as_of: datetime, calendar: TradingCalendarName = TradingCalendarName.US_EQUITY) -> date:
    """Return the latest session whose regular close is before ``as_of``."""
    local = _coerce_local(as_of)
    candidate = local.date()
    while True:
        if is_trading_session(candidate, calendar):
            close = session_close(candidate, calendar).astimezone(NEW_YORK)
            if local >= close:
                return candidate
        candidate -= timedelta(days=1)


def session_is_complete(as_of: datetime, calendar: TradingCalendarName = TradingCalendarName.US_EQUITY) -> bool:
    local = _coerce_local(as_of)
    return is_trading_session(local, calendar) and local >= session_close(local, calendar).astimezone(NEW_YORK)


