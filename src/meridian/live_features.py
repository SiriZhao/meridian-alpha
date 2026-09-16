"""Compose the existing historical adapter and point-in-time feature engine."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from meridian.analytics.derived_market_features import derive_market_features
from meridian.historical import (
    HistoricalBarSeries,
    HistoricalProviderError,
    YahooChartHistoricalProvider,
)
from meridian.market import Bar
from meridian.runtime_io import atomic_write
from meridian.security_master import DEFAULT_SECURITY_MASTER
from meridian.trading_calendar import latest_completed_session, session_close


def completed_session_features(series: dict[str, HistoricalBarSeries], benchmark: str, cutoff: datetime) -> dict[str, Any]:
    if cutoff.tzinfo is None:
        raise ValueError('HISTORY_CUTOFF_TIMEZONE_REQUIRED')
    bars = {
        symbol: tuple(Bar(session_close(bar.session), bar.open, bar.high, bar.low, bar.close, int(bar.volume))
                      for bar in sorted(item.bars, key=lambda row: row.session)
                      if bar.available_at <= cutoff and session_close(bar.session) <= cutoff)
        for symbol, item in series.items()
    }
    output: dict[str, Any] = {}
    for symbol, history in bars.items():
        complete = len(history) >= 61 and history[-1].timestamp.date() == latest_completed_session(cutoff)
        item = series[symbol]
        output[symbol] = {
            'status': 'PASS' if complete else 'INSUFFICIENT_OR_STALE_HISTORY',
            'source': item.provider, 'source_mode': item.source_mode,
            'input_hash': item.stable_hash, 'available_at': item.as_of.isoformat(),
            'market_as_of': history[-1].timestamp.isoformat() if history else None,
            'bar_count': len(history), 'history_pit_certified': False,
            'values': derive_market_features(history, as_of=cutoff, benchmark_bars=bars.get(benchmark, ())),
            'limitations': ['PUBLIC_UNCERTIFIED_OHLCV', 'COMPLETED_SESSIONS_ONLY', 'NO_INTRADAY_VOLUME_NORMALIZATION'],
        }
    return output


def collect_live_features(symbols: list[str], benchmark: str, *, evidence_directory: Path | None = None) -> dict[str, Any]:
    provider = YahooChartHistoricalProvider(DEFAULT_SECURITY_MASTER)
    series: dict[str, HistoricalBarSeries] = {}
    errors: dict[str, str] = {}
    for symbol in symbols:
        now = datetime.now(UTC)
        end = latest_completed_session(now)
        try:
            series[symbol] = provider.get_series(symbol, end-timedelta(days=400), end, as_of=now, live=True)
        except (HistoricalProviderError, OSError, ValueError) as error:
            errors[symbol] = type(error).__name__ + ':' + str(error)
    cutoff = datetime.now(UTC)
    features = completed_session_features(series, benchmark, cutoff)
    if evidence_directory is not None:
        for symbol, item in series.items():
            path = evidence_directory / (symbol + '.json')
            atomic_write(path, item.stable_json())
            features[symbol]['evidence_path'] = str(path)
    passed = len(features) == len(symbols) and all(row['status'] == 'PASS' for row in features.values())
    return {'status': 'PASS' if passed else 'FAILED', 'calculated_at': cutoff.isoformat(),
            'features': features, 'errors': errors, 'benchmark': benchmark,
            'method': 'MERIDIAN_DERIVED_MARKET_FEATURES', 'retrieval': 'NETWORK_NOT_LIVE_QUOTE'}
