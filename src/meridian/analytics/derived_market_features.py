"""Point-in-time market features derived locally from accepted OHLCV evidence."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from meridian.market import Bar, atr14, rsi14, simple_moving_average

TRADING_DAYS_YEAR = Decimal("252")


def _return(bars: tuple[Bar, ...], sessions: int) -> Decimal | None:
    if len(bars) <= sessions or bars[-sessions - 1].close <= 0:
        return None
    return bars[-1].close / bars[-sessions - 1].close - Decimal("1")


def _ema(bars: tuple[Bar, ...], window: int) -> Decimal | None:
    if len(bars) < window:
        return None
    multiplier = Decimal("2") / Decimal(window + 1)
    value = sum((bar.close for bar in bars[:window]), Decimal("0")) / Decimal(window)
    for bar in bars[window:]:
        value = (bar.close - value) * multiplier + value
    return value


def _returns(bars: tuple[Bar, ...], window: int | None = None) -> tuple[Decimal, ...]:
    selected = bars[-(window + 1) :] if window is not None else bars
    return tuple(
        selected[index].close / selected[index - 1].close - Decimal("1")
        for index in range(1, len(selected))
        if selected[index - 1].close > 0
    )


def _realized_volatility(bars: tuple[Bar, ...], window: int) -> Decimal | None:
    values = _returns(bars, window)
    if len(values) < window:
        return None
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum(((value - mean) ** 2 for value in values), Decimal("0")) / Decimal(
        len(values) - 1
    )
    return variance.sqrt() * TRADING_DAYS_YEAR.sqrt()


def _sample_covariance(left: tuple[Decimal, ...], right: tuple[Decimal, ...]) -> Decimal | None:
    size = min(len(left), len(right))
    if size < 2:
        return None
    left, right = left[-size:], right[-size:]
    left_mean = sum(left, Decimal("0")) / Decimal(size)
    right_mean = sum(right, Decimal("0")) / Decimal(size)
    return sum(
        ((left[index] - left_mean) * (right[index] - right_mean) for index in range(size)),
        Decimal("0"),
    ) / Decimal(size - 1)


def _paired_returns(asset: tuple[Bar, ...], benchmark: tuple[Bar, ...], window: int) -> tuple[tuple[Decimal, ...], tuple[Decimal, ...]]:
    """Align returns by session date; independent provider arrays must not be index-zipped."""
    asset_close = {bar.timestamp.date(): bar.close for bar in asset}
    benchmark_close = {bar.timestamp.date(): bar.close for bar in benchmark}
    sessions = sorted(set(asset_close) & set(benchmark_close))[-(window + 1) :]
    if len(sessions) < 3:
        return (), ()
    asset_returns: list[Decimal] = []
    benchmark_returns: list[Decimal] = []
    for previous, current in zip(sessions, sessions[1:], strict=False):
        left_previous, right_previous = asset_close[previous], benchmark_close[previous]
        if left_previous <= 0 or right_previous <= 0:
            continue
        asset_returns.append(asset_close[current] / left_previous - Decimal("1"))
        benchmark_returns.append(benchmark_close[current] / right_previous - Decimal("1"))
    return tuple(asset_returns), tuple(benchmark_returns)


def _relative_performance(asset: tuple[Bar, ...], benchmark: tuple[Bar, ...], sessions: int) -> Decimal | None:
    asset_returns, benchmark_returns = _paired_returns(asset, benchmark, sessions)
    if len(asset_returns) != sessions or len(benchmark_returns) != sessions:
        return None
    asset_total = Decimal("1")
    benchmark_total = Decimal("1")
    for value in asset_returns:
        asset_total *= Decimal("1") + value
    for value in benchmark_returns:
        benchmark_total *= Decimal("1") + value
    return asset_total / benchmark_total - Decimal("1") if benchmark_total > 0 else None


def _max_drawdown(bars: tuple[Bar, ...]) -> Decimal | None:
    if not bars:
        return None
    peak: Decimal | None = None
    drawdown = Decimal("0")
    for bar in bars:
        if peak is None or bar.close > peak:
            peak = bar.close
        if peak > 0:
            drawdown = min(drawdown, bar.close / peak - Decimal("1"))
    return drawdown


def derive_market_features(
    bars: tuple[Bar, ...],
    *,
    as_of: datetime,
    benchmark_bars: tuple[Bar, ...] = (),
    qqq_bars: tuple[Bar, ...] = (),
) -> dict[str, Decimal | None]:
    """Return deterministic features without forward fills, estimates, or LLM input."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("DERIVED_FEATURE_AS_OF_TIMEZONE_REQUIRED")
    eligible = tuple(sorted((bar for bar in bars if bar.timestamp <= as_of), key=lambda x: x.timestamp))
    if not eligible:
        return {}

    close = eligible[-1].close
    window_52w = eligible[-252:]
    maximum = max(bar.high for bar in window_52w)
    minimum = min(bar.low for bar in window_52w)
    prior_year = tuple(bar for bar in eligible if bar.timestamp.year < as_of.year)
    ytd_return = close / prior_year[-1].close - Decimal("1") if prior_year and eligible[-1].timestamp.year == as_of.year and prior_year[-1].close > 0 else None
    prior_volume = eligible[-21:-1]
    adv20 = sum((Decimal(bar.volume) for bar in prior_volume), Decimal("0")) / Decimal(20) if len(prior_volume) == 20 else None
    relative_volume = Decimal(eligible[-1].volume) / adv20 if adv20 and adv20 > 0 else None
    spy = tuple(sorted((bar for bar in benchmark_bars if bar.timestamp <= as_of), key=lambda x: x.timestamp))
    qqq = tuple(sorted((bar for bar in qqq_bars if bar.timestamp <= as_of), key=lambda x: x.timestamp))
    asset_returns, spy_returns = _paired_returns(eligible, spy, 60)
    if len(asset_returns) != 60:
        asset_returns, spy_returns = (), ()
    covariance = _sample_covariance(asset_returns, spy_returns)
    spy_variance = _sample_covariance(spy_returns, spy_returns)
    asset_variance = _sample_covariance(asset_returns, asset_returns)
    beta = (covariance / spy_variance if covariance is not None and spy_variance is not None and spy_variance != 0 else None)
    correlation = (covariance / (asset_variance * spy_variance).sqrt() if covariance is not None and asset_variance and spy_variance and asset_variance > 0 and spy_variance > 0 else None)
    gap = eligible[-1].open / eligible[-2].close - Decimal("1") if len(eligible) >= 2 and eligible[-2].close > 0 else None

    return {
        "return_1d": _return(eligible, 1), "return_5d": _return(eligible, 5),
        "return_20d": _return(eligible, 20), "return_60d": _return(eligible, 60),
        "return_1y": _return(eligible, 252), "return_ytd": ytd_return,
        "sma20": simple_moving_average(eligible, 20), "sma50": simple_moving_average(eligible, 50),
        "sma200": simple_moving_average(eligible, 200), "ema20": _ema(eligible, 20),
        "ema50": _ema(eligible, 50), "rsi14": rsi14(eligible), "atr14": atr14(eligible),
        "realized_volatility_20d": _realized_volatility(eligible, 20),
        "realized_volatility_60d": _realized_volatility(eligible, 60),
        "average_volume_20d": adv20, "relative_volume": relative_volume,
        "drawdown": close / max(bar.close for bar in window_52w) - Decimal("1"),
        "max_drawdown": _max_drawdown(window_52w),
        "distance_52w_high": close / maximum - Decimal("1") if len(window_52w) == 252 and maximum > 0 else None,
        "distance_52w_low": close / minimum - Decimal("1") if len(window_52w) == 252 and minimum > 0 else None,
        "gap": gap, "beta_60d": beta, "rolling_correlation_60d": correlation,
        "relative_performance_spy_20d": _relative_performance(eligible, spy, 20),
        "relative_performance_spy_60d": _relative_performance(eligible, spy, 60),
        "relative_performance_qqq_20d": _relative_performance(eligible, qqq, 20),
        "relative_performance_qqq_60d": _relative_performance(eligible, qqq, 60),
    }
