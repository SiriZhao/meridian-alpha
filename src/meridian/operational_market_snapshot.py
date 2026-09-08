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
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from meridian.historical import (
    HistoricalBar,
    HistoricalBarSeries,
    HistoricalProviderError,
    HistoricalProviderMalformed,
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
        self, symbol: str, start: date, end: date, *, as_of: datetime, live: bool = False
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
    data_quality_mode: str = "NORMAL"
    provider_probes: dict[str, dict[str, object]] = field(default_factory=dict)

    @property
    def snapshot_hash(self) -> str:
        payload = {
            "analysis_time": self.analysis_time.isoformat(),
            "information_cutoff": self.information_cutoff.isoformat(),
            "quotes": {
                key: value.model_dump(mode="json") for key, value in sorted(self.quotes.items())
            },
            "provider_health": self.provider_health,
            "provider_probes": self.provider_probes,
            "cache": self.cache,
            "conflicts": self.conflicts,
            "missing_symbols": self.missing_symbols,
            "data_mode": self.data_mode,
            "data_quality_mode": self.data_quality_mode,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()

    @property
    def status(self) -> str:
        if self.missing_symbols or not self.quotes:
            return "BLOCKED_MARKET_DATA"
        return "DATA_DEGRADED" if self.data_quality_mode == "DATA_DEGRADED" else "OPERATIONAL_READY"

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
            "data_quality_mode": self.data_quality_mode,
            "market_snapshot_hash": self.snapshot_hash,
            "information_cutoff": self.information_cutoff.isoformat(),
            "provider_health": self.provider_health,
            "provider_probes": self.provider_probes,
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
        cls, paths: RuntimePaths, *, timeout_seconds: float = 4.0, policy: FreshnessPolicy | None = None
    ) -> OperationalMarketSnapshotService:
        policy = policy or FreshnessPolicy()
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
        self, symbols: Iterable[str], *, analysis_time: datetime, live: bool = False
    ) -> OperationalMarketSnapshot:
        if analysis_time.tzinfo is None or analysis_time.utcoffset() is None:
            raise ValueError("ANALYSIS_TIME_TIMEZONE_REQUIRED")
        requested = tuple(sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()}))
        quotes: dict[str, MarketSnapshot] = {}
        health: dict[str, dict[str, str]] = {}
        cache: dict[str, bool] = {}
        conflicts: dict[str, str] = {}
        missing: dict[str, str] = {}
        probes: dict[str, dict[str, object]] = {}
        observations: dict[str, OperationalSnapshot] = {}
        data_quality_mode = "NORMAL"
        for symbol in requested:
            refresh = self.refresh.refresh(symbol, analysis_time=analysis_time, live=True) if live else self.refresh.refresh(symbol, analysis_time=analysis_time)
            if live:
                analysis_time = refresh.analysis_time
            health[symbol] = {
                "primary": refresh.primary.status.value,
                "secondary": refresh.secondary.status.value,
            }
            observations[symbol] = refresh
            if refresh.data_quality_mode == "DATA_DEGRADED":
                data_quality_mode = "DATA_DEGRADED"
            probes[symbol] = {
                "primary": {"provider": refresh.primary.provider, "status": refresh.primary.status.value, "detail": refresh.primary.detail},
                "secondary": {"provider": refresh.secondary.provider, "status": refresh.secondary.status.value, "detail": refresh.secondary.detail},
                "selected_provider": refresh.selected.provider if refresh.selected else None,
                "selection": refresh.selected_lane,
                "cache": {"status": refresh.cache_status, "hit": refresh.cache_hit},
                "data_quality_mode": refresh.data_quality_mode,
                "history": {"status": "NOT_RUN"},
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
                quotes[symbol] = self._market_snapshot(symbol, refresh, analysis_time, live=live, diagnostic=probes[symbol])
            except (HistoricalProviderError, OSError, ValueError) as error:
                missing[symbol] = self._historical_code(error)
                probes[symbol]["history"] = {"status": "BLOCKED", "code": missing[symbol]}
        if live:
            analysis_time = datetime.now(UTC)
        for symbol, observation in observations.items():
            for lane, result in (("primary", observation.primary), ("secondary", observation.secondary)):
                if result.quote is not None:
                    probes[symbol][lane] = {**self.policy.describe(result.quote, as_of=analysis_time), "requested_provider": result.provider, "detail": result.detail}
                lane_payload = probes[symbol][lane]
                if isinstance(lane_payload, dict):
                    health[symbol][lane] = str(lane_payload["status"])
                    lane_payload.update({"attempted_at": result.attempted_at.isoformat() if result.attempted_at else None,
                                         "completed_at": result.completed_at.isoformat() if result.completed_at else None,
                                         "request_mode": "LIVE" if live else "REPLAY",
                                         "error_category": None if lane_payload["status"] == "OK" else "DATA_QUALITY" if result.quote is not None else "PROVIDER_FAILURE"})
            if observation.selected is not None:
                probes[symbol]["selected"] = self.policy.describe(observation.selected, as_of=analysis_time)
                if self.policy.quote_status(observation.selected, as_of=analysis_time) is not OperationalProviderStatus.OK:
                    quotes.pop(symbol, None)
                    missing[symbol] = "MARKET_DATA_STALE_OR_AFTER_CUTOFF"
            probes[symbol]["final_market_status"] = "BLOCKED" if symbol in missing else "PASS"
            probes[symbol]["analysis_cutoff"] = analysis_time.isoformat()
        return OperationalMarketSnapshot(
            provider_probes=probes,
            analysis_time=analysis_time,
            information_cutoff=analysis_time,
            quotes=quotes,
            provider_health=health,
            cache=cache,
            conflicts=conflicts,
            missing_symbols=missing,
            data_quality_mode="DATA_DEGRADED" if missing else data_quality_mode,
        )

    def _market_snapshot(
        self, symbol: str, refresh: OperationalSnapshot, analysis_time: datetime, *, live: bool = False, diagnostic: dict[str, object] | None = None
    ) -> MarketSnapshot:
        selected = refresh.selected
        if selected is None:
            raise ValueError("SYMBOL_MISSING")
        series = self.historical.get_series(
            symbol,
            analysis_time.date() - timedelta(days=self.lookback_days),
            analysis_time.date(),
            as_of=analysis_time,
            live=live,
        )
        if live:
            analysis_time = datetime.now(UTC)
        bars = tuple(bar for bar in series.bars if bar.available_at <= analysis_time and bar.retrieved_at <= analysis_time)
        completed = latest_completed_session(analysis_time)
        completed_bars = tuple(bar for bar in bars if bar.session <= completed)
        if len(completed_bars) < 2:
            raise ValueError("SYMBOL_MISSING")
        latest = completed_bars[-1]
        if not self.policy.daily_bar_is_current(latest.session, as_of=analysis_time):
            raise ValueError("HISTORICAL_DATA_STALE")
        if diagnostic is not None:
            diagnostic["history"] = {"status": "PASS", "provider": series.provider, "latest_session": latest.session.isoformat(), "received_at": latest.retrieved_at.isoformat(), "available_at": latest.available_at.isoformat(), "cutoff": analysis_time.isoformat(), "certification": "UNVERIFIED"}
        previous = completed_bars[-2] if latest.session == completed else latest
        if previous.close <= 0:
            raise ValueError("INVALID_RESPONSE")
        atr = self._atr(completed_bars)
        money_unit = Decimal("0.0001")
        return MarketSnapshot(
            ticker=symbol,
            timestamp=selected.timestamp,
            last=selected.price.quantize(money_unit),
            previous_close=previous.close.quantize(money_unit),
            volume=int(latest.volume),
            atr14=atr.quantize(money_unit) if atr is not None else None,
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
        if refresh.primary.status is OperationalProviderStatus.STALE or refresh.secondary.status is OperationalProviderStatus.STALE:
            return "MARKET_DATA_STALE"
        if "timeout" in details:
            return "NETWORK_TIMEOUT"
        return "PRIMARY_PROVIDER_UNAVAILABLE_AND_SECONDARY_PROVIDER_UNAVAILABLE"

    @staticmethod
    def _historical_code(error: Exception) -> str:
        if str(error) == "HISTORICAL_DATA_STALE":
            return "HISTORICAL_DATA_STALE"
        if "timed out" in str(error).lower():
            return "NETWORK_TIMEOUT"
        if str(error) == "SYMBOL_MISSING":
            return "SYMBOL_MISSING"
        if isinstance(error, HistoricalProviderMalformed):
            return "INVALID_RESPONSE"
        return "INVALID_RESPONSE"
