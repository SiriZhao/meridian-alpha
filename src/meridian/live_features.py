"""Compose the existing historical adapter and point-in-time feature engine."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from meridian.historical import (
    HistoricalBarSeries,
    HistoricalProviderError,
    YahooChartHistoricalProvider,
)
from meridian.live_quant_bridge import provisional_diagnostics
from meridian.runtime_io import atomic_write
from meridian.security_master import DEFAULT_SECURITY_MASTER
from meridian.trading_calendar import latest_completed_session, session_close


def completed_session_features(series: dict[str, HistoricalBarSeries], benchmark: str, cutoff: datetime) -> dict[str, Any]:
    if cutoff.tzinfo is None:
        raise ValueError('HISTORY_CUTOFF_TIMEZONE_REQUIRED')
    bars = {
        symbol: tuple(bar for bar in item.bars
                      if bar.available_at <= cutoff and bar.observed_at <= cutoff and session_close(bar.session) <= cutoff)
        for symbol, item in series.items()
    }
    output: dict[str, Any] = {}
    for symbol, history in bars.items():
        diagnostic = provisional_diagnostics(series[symbol], cutoff)
        complete = len(history) >= 61 and history[-1].session == latest_completed_session(cutoff)
        item = series[symbol]
        output[symbol] = {
            'status': 'PASS' if complete else 'INSUFFICIENT_OR_STALE_HISTORY',
            'source': item.provider, 'source_mode': item.source_mode,
            'input_hash': item.stable_hash, 'available_at': item.as_of.isoformat(),
            'market_as_of': session_close(history[-1].session).isoformat() if history else None,
            'bar_count': len(history), 'history_pit_certified': False,
            'values': diagnostic,
            'limitations': ['PUBLIC_UNCERTIFIED_OHLCV', 'COMPLETED_SESSIONS_ONLY', 'NO_INTRADAY_VOLUME_NORMALIZATION'],
        }
    return output


def collect_live_features(symbols: list[str], benchmark: str, *, evidence_directory: Path | None = None,
                          include_series: bool = False) -> dict[str, Any]:
    provider = YahooChartHistoricalProvider(DEFAULT_SECURITY_MASTER, timeout_seconds=4)
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
            'method': 'PUBLIC_WITHIN_SESSION_DIAGNOSTICS_NO_UNRESOLVED_RETURN', 'retrieval': 'NETWORK_NOT_LIVE_QUOTE',
            **({'_series': series} if include_series else {})}
