"""Build daily ``MarketSnapshot`` objects from the operational data plane.

This module is deliberately an integration boundary.  It owns bounded public
retrieval, provenance, cache-aware health, and conversion to the existing
domain snapshot; allocation, risk, limit pricing, and orders remain in the
daily closure service.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from meridian.historical import (
    HistoricalBar,
    HistoricalBarSeries,
    HistoricalProviderError,
    YahooChartHistoricalProvider,
)
from meridian.operational_data import (
    FreshnessPolicy,
    OperationalCache,
    OperationalProviderStatus,
    OperationalRefreshService,
    OperationalSnapshot,
)
from meridian.quotes import StooqQuoteProvider, YahooChartQuoteProvider
from meridian.runtime import RuntimePaths
from meridian.schemas import FreshnessState, MarketSnapshot
from meridian.security_master import DEFAULT_SECURITY_MASTER
from meridian.trading_calendar import latest_completed_session


class HistoricalSeriesProvider(Protocol):
    def get_series(
        self, symbol: str, start: date, end: date, *, as_of: datetime
    ) -> HistoricalBarSeries: ...


@dataclass(frozen=True)
class OperationalMarketSnapshot:
    """Immutable operational input for one daily closure run.

    Public observations are explicitly not PIT-certified research nor
    execution quotes.  A missing or invalid symbol remains visible in
    ``missing_symbols`` instead of being silently substituted.
    """

    analysis_time: datetime
    information_cutoff: datetime
    quotes: dict[str, MarketSnapshot]
    provider_health: dict[str, dict[str, str]]
    cache: dict[str, bool]
    conflicts: dict[str, str]
    missing_symbols: dict[str, str]
    data_mode: str = "OPERATIONAL_PUBLIC"

    @property
    def snapshot_hash(self) -> str:
        payload = {
            "analysis_time": self.analysis_time.isoformat(),
            "information_cutoff": self.information_cutoff.isoformat(),
            "quotes": {
                key: value.model_dump(mode="json") for key, value in sorted(self.quotes.items())
            },
            "provider_health": self.provider_health,
            "cache": self.cache,
            "conflicts": self.conflicts,
            "missing_symbols": self.missing_symbols,
            "data_mode": self.data_mode,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()

    @property
    def status(self) -> str:
        return "BLOCKED_MARKET_DATA" if self.missing_symbols else "OPERATIONAL_READY"

    def data_status(self) -> dict[str, object]:
        statuses = [value["primary"] for value in self.provider_health.values()]
        secondary = [value["secondary"] for value in self.provider_health.values()]
        return {
            "market_calendar": "OK",
            "primary_price": "OK"
            if statuses and all(value == "OK" for value in statuses)
            else "DEGRADED",
            "secondary_price": "OK"
            if secondary and all(value == "OK" for value in secondary)
            else "DEGRADED",
            "latest_quote": "FRESH"
            if self.quotes and not self.missing_symbols
            else "STALE_OR_UNAVAILABLE",
            "latest_daily_bar": "FRESH" if self.quotes and not self.missing_symbols else "UNKNOWN",
            "operational": self.status,
            "research": "RESEARCH_BLOCKED",
            "historical_universe": "BLOCKED",
            "certification": "OPERATIONAL_DATA_IS_NOT_CERTIFIED_RESEARCH",
            "data_mode": self.data_mode,
            "market_snapshot_hash": self.snapshot_hash,
            "information_cutoff": self.information_cutoff.isoformat(),
            "provider_health": self.provider_health,
            "cache": self.cache,
            "provider_conflicts": self.conflicts,
            "symbols_missing": self.missing_symbols,
        }


class OperationalMarketSnapshotService:
    """Compose existing operational providers into daily domain snapshots."""

    def __init__(
        self,
        refresh: OperationalRefreshService,
        historical: HistoricalSeriesProvider,
        *,
        policy: FreshnessPolicy | None = None,
        lookback_days: int = 35,
    ) -> None:
        if lookback_days < 15:
            raise ValueError("operational lookback must retain at least 15 calendar days")
        self.refresh = refresh
        self.historical = historical
        self.policy = policy or refresh.policy
        self.lookback_days = lookback_days

    @classmethod
    def from_runtime(
        cls, paths: RuntimePaths, *, timeout_seconds: float = 4.0
    ) -> OperationalMarketSnapshotService:
        policy = FreshnessPolicy()
        primary = YahooChartQuoteProvider(DEFAULT_SECURITY_MASTER, timeout_seconds=timeout_seconds)
        secondary = StooqQuoteProvider(DEFAULT_SECURITY_MASTER, timeout_seconds=timeout_seconds)
        refresh = OperationalRefreshService(
            primary, secondary, policy=policy, cache=OperationalCache(paths.cache)
        )
        historical = YahooChartHistoricalProvider(
            DEFAULT_SECURITY_MASTER, timeout_seconds=timeout_seconds
        )
        return cls(refresh, historical, policy=policy)

    def build(
        self, symbols: Iterable[str], *, analysis_time: datetime
    ) -> OperationalMarketSnapshot:
        if analysis_time.tzinfo is None or analysis_time.utcoffset() is None:
            raise ValueError("ANALYSIS_TIME_TIMEZONE_REQUIRED")
        requested = tuple(sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()}))
        quotes: dict[str, MarketSnapshot] = {}
        health: dict[str, dict[str, str]] = {}
        cache: dict[str, bool] = {}
        conflicts: dict[str, str] = {}
        missing: dict[str, str] = {}
        for symbol in requested:
            refresh = self.refresh.refresh(symbol, analysis_time=analysis_time)
            health[symbol] = {
                "primary": refresh.primary.status.value,
                "secondary": refresh.secondary.status.value,
            }
            cache[symbol] = refresh.cache_hit
            if (
                refresh.conflict_percent is not None
                and refresh.conflict_percent > self.refresh.discrepancy_tolerance_percent
            ):
                conflicts[symbol] = "MARKET_DATA_CONFLICT"
                missing[symbol] = "MARKET_DATA_CONFLICT"
                continue
            if refresh.selected is None:
                missing[symbol] = self._missing_code(refresh)
                continue
            if (
                self.policy.quote_status(refresh.selected, as_of=analysis_time)
                is not OperationalProviderStatus.OK
            ):
                missing[symbol] = "MARKET_DATA_STALE"
                continue
            try:
                quotes[symbol] = self._market_snapshot(symbol, refresh, analysis_time)
            except (HistoricalProviderError, OSError, ValueError) as error:
                missing[symbol] = self._historical_code(error)
        return OperationalMarketSnapshot(
            analysis_time=analysis_time,
            information_cutoff=analysis_time,
            quotes=quotes,
            provider_health=health,
            cache=cache,
            conflicts=conflicts,
            missing_symbols=missing,
        )

    def _market_snapshot(
        self, symbol: str, refresh: OperationalSnapshot, analysis_time: datetime
    ) -> MarketSnapshot:
        selected = refresh.selected
        if selected is None:
            raise ValueError("SYMBOL_MISSING")
        series = self.historical.get_series(
            symbol,
            analysis_time.date() - timedelta(days=self.lookback_days),
            analysis_time.date(),
            as_of=analysis_time,
        )
        bars = tuple(bar for bar in series.bars if bar.available_at <= analysis_time)
        completed = latest_completed_session(analysis_time)
        completed_bars = tuple(bar for bar in bars if bar.session <= completed)
        if len(completed_bars) < 2:
            raise ValueError("SYMBOL_MISSING")
        latest = completed_bars[-1]
        previous = completed_bars[-2] if latest.session == completed else latest
        if previous.close <= 0:
            raise ValueError("INVALID_RESPONSE")
        atr = self._atr(completed_bars)
        return MarketSnapshot(
            ticker=symbol,
            timestamp=selected.timestamp,
            last=selected.price,
            previous_close=previous.close,
            volume=int(latest.volume),
            atr14=atr,
            # Public shadow providers do not supply an execution-grade VWAP or spread.
            vwap=None,
            bid=None,
            ask=None,
            daily_return=(selected.price / previous.close) - Decimal("1"),
            gap_percent=(latest.open / previous.close) - Decimal("1"),
            freshness_state=FreshnessState.VERIFIED,
        )

    @staticmethod
    def _atr(bars: tuple[HistoricalBar, ...]) -> Decimal | None:
        if len(bars) < 15:
            return None
        ranges = []
        for index in range(-14, 0):
            bar = bars[index]
            prior = bars[index - 1]
            ranges.append(
                max(bar.high - bar.low, abs(bar.high - prior.close), abs(bar.low - prior.close))
            )
        return sum(ranges, Decimal("0")) / Decimal(len(ranges))

    @staticmethod
    def _missing_code(refresh: OperationalSnapshot) -> str:
        details = {refresh.primary.detail, refresh.secondary.detail}
        if (
            refresh.primary.status is OperationalProviderStatus.INVALID_RESPONSE
            or refresh.secondary.status is OperationalProviderStatus.INVALID_RESPONSE
        ):
            return "INVALID_RESPONSE"
        if "timeout" in details:
            return "NETWORK_TIMEOUT"
        return "PRIMARY_PROVIDER_UNAVAILABLE_AND_SECONDARY_PROVIDER_UNAVAILABLE"

    @staticmethod
    def _historical_code(error: Exception) -> str:
        if "timed out" in str(error).lower():
            return "NETWORK_TIMEOUT"
        return "SYMBOL_MISSING"
