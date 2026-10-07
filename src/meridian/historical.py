"""Point-in-time historical OHLCV contracts and deterministic shadow features."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import quote as url_quote
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import Field, model_validator

from meridian.market import Bar, feature_set
from meridian.schemas import StableModel
from meridian.security_master import SecurityIdentityUnavailable, SecurityMaster
from meridian.trading_calendar import (
    TradingCalendarName,
    is_trading_session,
    session_close,
    session_is_complete,
)


class HistoricalAdjustmentStatus(StrEnum):
    RAW = "RAW"
    ADJUSTED_CLOSE = "ADJUSTED_CLOSE"
    FULLY_ADJUSTED_OHLCV = "FULLY_ADJUSTED_OHLCV"


class HistoricalBarCertification(StrEnum):
    CERTIFIED_MARKET_SESSION = "CERTIFIED_MARKET_SESSION"
    UNVERIFIED = "UNVERIFIED"
    SYNTHETIC = "SYNTHETIC"
    REPLAY_UNSAFE = "REPLAY_UNSAFE"


class HistoricalQuality(StrEnum):
    VERIFIED = "VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    MISSING = "MISSING"
    INVALID = "INVALID"
    CONFLICT = "CONFLICT"


class HistoricalBar(StableModel):
    canonical_asset_id: str = Field(min_length=1, max_length=128)
    canonical_symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,15}$")
    provider_symbol: str = Field(min_length=1, max_length=128)
    session: date
    calendar: TradingCalendarName
    open: Decimal = Field(ge=Decimal("0"))
    high: Decimal = Field(ge=Decimal("0"))
    low: Decimal = Field(ge=Decimal("0"))
    close: Decimal = Field(ge=Decimal("0"))
    volume: Decimal = Field(ge=Decimal("0"))
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    adjustment_status: HistoricalAdjustmentStatus
    provider: str = Field(min_length=1, max_length=128)
    observed_at: datetime
    available_at: datetime
    retrieved_at: datetime
    source: str = Field(min_length=1, max_length=256)
    quality: HistoricalQuality = HistoricalQuality.UNVERIFIED
    certification: HistoricalBarCertification = HistoricalBarCertification.UNVERIFIED

    @model_validator(mode="after")
    def validate_bar(self) -> HistoricalBar:
        for name, value in (
            ("observed_at", self.observed_at),
            ("available_at", self.available_at),
            ("retrieved_at", self.retrieved_at),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
        if self.available_at > self.retrieved_at:
            raise ValueError("available_at must not be after retrieved_at")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be at least open, close and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must not exceed open, close and high")
        if not is_trading_session(self.session, self.calendar):
            raise ValueError("historical bar session is not a valid trading session")
        if (
            self.adjustment_status is not HistoricalAdjustmentStatus.RAW
            and self.certification is HistoricalBarCertification.CERTIFIED_MARKET_SESSION
        ):
            raise ValueError("adjusted bars cannot be certified as raw market session facts")
        if (
            self.certification is HistoricalBarCertification.CERTIFIED_MARKET_SESSION
            and self.quality is not HistoricalQuality.VERIFIED
        ):
            raise ValueError("certified market session bars require VERIFIED quality")
        return self

    @property
    def execution_price_eligible(self) -> bool:
        """Historical adjusted prices are never valid execution quotes."""
        return False

    @property
    def stable_id(self) -> str:
        raw = "|".join(
            (
                self.canonical_asset_id,
                self.provider,
                self.provider_symbol,
                self.session.isoformat(),
                self.adjustment_status.value,
            )
        )
        return f"bar_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


class HistoricalBarSeries(StableModel):
    canonical_asset_id: str
    canonical_symbol: str
    provider: str
    as_of: datetime
    bars: tuple[HistoricalBar, ...] = Field(default=(), max_length=5000)
    source_mode: str = "REPLAY"
    content_hash: str | None = None
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_series(self) -> HistoricalBarSeries:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("series as_of must be timezone-aware")
        if any(bar.canonical_asset_id != self.canonical_asset_id for bar in self.bars):
            raise ValueError("series contains a cross-asset bar")
        sessions = [bar.session for bar in self.bars]
        if len(set(sessions)) != len(sessions):
            raise ValueError("series contains duplicate sessions")
        if any(bar.available_at > self.as_of for bar in self.bars):
            raise ValueError("historical bar available_at is after series as_of")
        return self

    @property
    def stable_hash(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


class HistoricalOHLCVProvider(Protocol):
    provider_name: str

    def get_bars(
        self, symbol: str, start: date, end: date, *, as_of: datetime
    ) -> Sequence[Mapping[str, Any]]: ...


class HistoricalDataNormalizer:
    """Normalize provider rows only after identity and PIT checks."""

    def __init__(self, security_master: SecurityMaster, *, provider: str):
        self.security_master = security_master
        self.provider = provider

    def normalize(
        self,
        rows: Sequence[Mapping[str, Any]],
        *,
        symbol: str,
        as_of: datetime,
        retrieved_at: datetime,
        adjustment_status: HistoricalAdjustmentStatus = HistoricalAdjustmentStatus.RAW,
        certification: HistoricalBarCertification = HistoricalBarCertification.UNVERIFIED,
        quality: HistoricalQuality = HistoricalQuality.UNVERIFIED,
        source_mode: str = "REPLAY",
    ) -> HistoricalBarSeries:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        security = self.security_master.resolve(symbol)
        provider_symbol = security.provider_symbols.get(self.provider)
        if not provider_symbol:
            raise SecurityIdentityUnavailable(
                "SECURITY_IDENTITY_UNAVAILABLE:historical-provider-symbol"
            )
        bars: list[HistoricalBar] = []
        for row in rows:
            row_symbol = str(row.get("provider_symbol", ""))
            if row_symbol != provider_symbol:
                raise SecurityIdentityUnavailable(
                    "SECURITY_IDENTITY_UNAVAILABLE:provider-symbol-mismatch"
                )
            session = self._date(row.get("session"))
            observed_at = self._timestamp(row.get("observed_at", row.get("session")))
            available_at = self._timestamp(row.get("available_at", observed_at))
            if session > as_of.astimezone(UTC).date() or available_at > as_of:
                raise ValueError("historical row is after as_of")
            currency = str(row.get("currency", "")).upper()
            if currency != security.currency:
                raise ValueError("historical currency does not match security master")
            bars.append(
                HistoricalBar(
                    canonical_asset_id=security.canonical_asset_id,
                    canonical_symbol=security.canonical_symbol,
                    provider_symbol=provider_symbol,
                    session=session,
                    calendar=TradingCalendarName(security.trading_calendar),
                    open=self._decimal(row.get("open"), "open"),
                    high=self._decimal(row.get("high"), "high"),
                    low=self._decimal(row.get("low"), "low"),
                    close=self._decimal(row.get("close"), "close"),
                    volume=self._decimal(row.get("volume"), "volume"),
                    currency=currency,
                    adjustment_status=adjustment_status,
                    provider=self.provider,
                    observed_at=observed_at,
                    available_at=available_at,
                    retrieved_at=retrieved_at,
                    source=str(row.get("source", self.provider)),
                    quality=quality,
                    certification=certification,
                )
            )
        ordered = tuple(sorted(bars, key=lambda bar: bar.session))
        digest = hashlib.sha256("|".join(bar.stable_id for bar in ordered).encode()).hexdigest()
        return HistoricalBarSeries(
            canonical_asset_id=security.canonical_asset_id,
            canonical_symbol=security.canonical_symbol,
            provider=self.provider,
            as_of=as_of,
            bars=ordered,
            source_mode=source_mode,
            content_hash=digest,
        )

    @staticmethod
    def _date(value: Any) -> date:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            return date.fromisoformat(value[:10])
        raise ValueError("historical session is required")

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        if isinstance(value, datetime):
            result = value
        elif isinstance(value, str):
            try:
                result = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                result = datetime.combine(
                    date.fromisoformat(value[:10]), datetime.min.time(), tzinfo=UTC
                )
        elif isinstance(value, date):
            result = datetime.combine(value, datetime.min.time(), tzinfo=UTC)
        else:
            raise ValueError("historical timestamp is required")
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError("historical timestamp must be timezone-aware")
        return result

    @staticmethod
    def _decimal(value: Any, name: str) -> Decimal:
        try:
            parsed = Decimal(str(value))
        except Exception as error:  # noqa: BLE001
            raise ValueError(f"invalid historical {name}") from error
        if not parsed.is_finite() or parsed < 0:
            raise ValueError(f"invalid historical {name}")
        return parsed


class HistoricalDataQualityDiagnostics(StableModel):
    total_sessions: int
    expected_sessions: int | None = None
    coverage_ratio: Decimal | None = None
    missing_sessions: tuple[date, ...] = ()
    duplicate_sessions: tuple[date, ...] = ()
    impossible_rows: int = 0
    zero_volume_rows: int = 0
    adjustment_discontinuities: tuple[str, ...] = ()
    provider_disagreements: tuple[str, ...] = ()
    stale_rows: int = 0
    abnormal_volume_rows: int = 0
    warnings: tuple[str, ...] = ()


def inspect_series(
    series: HistoricalBarSeries,
    *,
    expected_sessions: Sequence[date] = (),
    stale_before: datetime | None = None,
    abnormal_volume_threshold: Decimal | None = None,
) -> HistoricalDataQualityDiagnostics:
    sessions = [bar.session for bar in series.bars]
    duplicates = tuple(sorted({item for item in sessions if sessions.count(item) > 1}))
    expected = tuple(expected_sessions)
    missing = tuple(item for item in expected if item not in set(sessions))
    coverage = (
        (Decimal(len(set(sessions) & set(expected))) / Decimal(len(expected))) if expected else None
    )
    zero_volume = sum(1 for bar in series.bars if bar.volume == 0)
    stale_rows = sum(
        1 for bar in series.bars if stale_before is not None and bar.available_at < stale_before
    )
    abnormal_volume = sum(
        1
        for bar in series.bars
        if abnormal_volume_threshold is not None and bar.volume > abnormal_volume_threshold
    )
    return HistoricalDataQualityDiagnostics(
        total_sessions=len(sessions),
        expected_sessions=len(expected) if expected else None,
        coverage_ratio=coverage,
        missing_sessions=missing,
        duplicate_sessions=duplicates,
        zero_volume_rows=zero_volume,
        stale_rows=stale_rows,
        abnormal_volume_rows=abnormal_volume,
        warnings=tuple(
            item
            for item in (
                "MISSING_SESSIONS" if missing else None,
                "STALE_SERIES" if stale_rows else None,
            )
            if item
        ),
    )


class HistoricalProviderComparison(StableModel):
    canonical_symbol: str
    differing_sessions: tuple[str, ...] = ()
    differing_fields: tuple[str, ...] = ()
    status: str = "MATCH"


def compare_historical_series(
    series: Sequence[HistoricalBarSeries],
) -> HistoricalProviderComparison:
    if not series:
        raise ValueError("at least one historical series is required")
    baseline = {bar.session: bar for bar in series[0].bars}
    differing_sessions: set[str] = set()
    differing_fields: set[str] = set()
    for other in series[1:]:
        current = {bar.session: bar for bar in other.bars}
        for session in set(baseline) | set(current):
            left, right = baseline.get(session), current.get(session)
            if left is None or right is None:
                differing_sessions.add(session.isoformat())
                continue
            for field in (
                "open",
                "high",
                "low",
                "close",
                "volume",
                "adjustment_status",
                "currency",
            ):
                if getattr(left, field) != getattr(right, field):
                    differing_fields.add(field)
    status = "MARKET_DATA_CONFLICT" if differing_sessions or differing_fields else "MATCH"
    return HistoricalProviderComparison(
        canonical_symbol=series[0].canonical_symbol,
        differing_sessions=tuple(sorted(differing_sessions)),
        differing_fields=tuple(sorted(differing_fields)),
        status=status,
    )


class ShadowFeatureLineage(StableModel):
    canonical_symbol: str
    cutoff: datetime
    sessions_used: tuple[date, ...]
    input_hash: str
    source_mode: str = "REPLAY"
    promoted: bool = False


def generate_shadow_features(
    series: HistoricalBarSeries, cutoff: datetime
) -> tuple[dict[str, Decimal | None], ShadowFeatureLineage]:
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("feature cutoff must be timezone-aware")
    eligible = tuple(
        bar
        for bar in series.bars
        if bar.available_at <= cutoff
        and (bar.session < cutoff.date() or session_is_complete(cutoff, bar.calendar))
    )
    bars = tuple(
        Bar(
            datetime.combine(bar.session, datetime.min.time(), tzinfo=UTC),
            bar.open,
            bar.high,
            bar.low,
            bar.close,
            int(bar.volume),
        )
        for bar in eligible
    )
    features = feature_set(bars, cutoff)
    input_hash = hashlib.sha256("|".join(bar.stable_id for bar in eligible).encode()).hexdigest()
    lineage = ShadowFeatureLineage(
        canonical_symbol=series.canonical_symbol,
        cutoff=cutoff,
        sessions_used=tuple(bar.session for bar in eligible if bar.session <= cutoff.date()),
        input_hash=input_hash,
        source_mode=series.source_mode,
    )
    return features, lineage


OHLCVBar = HistoricalBar
HistoricalSeries = HistoricalBarSeries


class HistoricalProviderError(RuntimeError):
    """Base error for real historical provider observations."""


class HistoricalProviderTimeout(HistoricalProviderError):
    pass


class HistoricalProviderMalformed(HistoricalProviderError):
    pass


class YahooChartHistoricalProvider:
    """Bounded public Yahoo chart OHLCV adapter for SHADOW use.

    Yahoo's chart response is a current retrieval of historical exchange
    sessions; it does not establish when the row was historically available.
    Rows therefore retain ``available_at=retrieved_at`` and remain
    ``UNVERIFIED`` for historical information PIT.
    """

    provider_name = "yahoo"
    network_capable = True

    def __init__(
        self,
        security_master: SecurityMaster,
        *,
        timeout_seconds: float = 10.0,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.security_master = security_master
        self.timeout_seconds = timeout_seconds
        self.opener = opener
        self.clock = clock or (lambda: datetime.now(UTC))

    def get_bars(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        as_of: datetime,
    ) -> tuple[Mapping[str, Any], ...]:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("historical provider as_of must be timezone-aware")
        if end < start:
            raise ValueError("historical provider end must not precede start")
        security = self.security_master.resolve(symbol)
        provider_symbol = security.provider_symbols.get(self.provider_name)
        if not provider_symbol:
            raise SecurityIdentityUnavailable("SECURITY_IDENTITY_UNAVAILABLE:yahoo-symbol")
        period1 = int(datetime.combine(start, datetime.min.time(), tzinfo=UTC).timestamp())
        period2 = int(datetime.combine(end, datetime.min.time(), tzinfo=UTC).timestamp()) + 86400
        query = urlencode(
            {
                "period1": period1,
                "period2": period2,
                "interval": "1d",
                "events": "div,splits",
                "includeAdjustedClose": "true",
            }
        )
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{url_quote(provider_symbol)}?{query}"
        request = Request(url, headers={"User-Agent": "MeridianAlpha/0.1 shadow-data"})
        started = time.perf_counter()
        try:
            response = self.opener(request, timeout=self.timeout_seconds)
            try:
                status = getattr(response, "status", getattr(response, "code", None))
                try:
                    status_code = int(status) if status is not None else None
                except (TypeError, ValueError):
                    status_code = None
                if status_code is not None and status_code >= 400:
                    raise HistoricalProviderError(f"Yahoo historical HTTP error: {status_code}")
                payload = response.read()
            finally:
                close = getattr(response, "close", None)
                if close is not None:
                    close()
        except TimeoutError as error:
            raise HistoricalProviderTimeout("Yahoo historical request timed out") from error
        except OSError as error:
            raise HistoricalProviderError("Yahoo historical request failed") from error
        if time.perf_counter() - started > self.timeout_seconds * 2:
            raise HistoricalProviderTimeout("Yahoo historical response exceeded timeout budget")
        try:
            document = json.loads(
                payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
            )
            result = document["chart"]["result"][0]
            timestamps = result["timestamp"]
            quote = result["indicators"]["quote"][0]
            currency = str(result["meta"].get("currency") or security.currency).upper()
            opens, highs, lows = quote["open"], quote["high"], quote["low"]
            closes, volumes = quote["close"], quote["volume"]
        except (KeyError, IndexError, TypeError, AttributeError, ValueError) as error:
            raise HistoricalProviderMalformed("Yahoo historical response is malformed") from error
        retrieved = self.clock()
        if retrieved.tzinfo is None or retrieved.utcoffset() is None:
            raise ValueError("historical provider clock must be timezone-aware")
        rows: list[Mapping[str, Any]] = []
        if not isinstance(timestamps, list) or not all(isinstance(values, list) and len(values) == len(timestamps) for values in (opens, highs, lows, closes, volumes)):
            raise HistoricalProviderMalformed("Yahoo historical array schema drift")
        for timestamp, opening, high, low, close, volume in zip(
            timestamps, opens, highs, lows, closes, volumes, strict=False
        ):
            if any(value is None for value in (timestamp, opening, high, low, close, volume)):
                continue
            try:
                session = datetime.fromtimestamp(float(timestamp), tz=UTC).date()
            except (ValueError, TypeError, OverflowError, OSError) as error:
                raise HistoricalProviderMalformed("Yahoo historical timestamp invalid") from error
            calendar = TradingCalendarName(security.trading_calendar)
            if session < start or session > end or session > as_of.astimezone(UTC).date():
                continue
            # A bar for the current exchange session is not complete until the
            # session close; exclude it rather than forward-filling or guessing.
            if session_close(session, calendar) > as_of:
                continue
            rows.append(
                {
                    "provider_symbol": provider_symbol,
                    "session": session,
                    "open": opening,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                    "currency": currency,
                    "observed_at": session_close(
                        session, TradingCalendarName(security.trading_calendar)
                    ),
                    "available_at": retrieved,
                    "source": "yahoo-chart-public",
                }
            )
        if not rows:
            raise HistoricalProviderMalformed("Yahoo historical response contains no usable rows")
        return tuple(rows)

    def get_series(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        as_of: datetime,
        live: bool = False,
    ) -> HistoricalBarSeries:
        rows = self.get_bars(symbol, start, end, as_of=as_of)
        retrieved = self.clock()
        return HistoricalDataNormalizer(
            self.security_master, provider=self.provider_name
        ).normalize(
            rows,
            symbol=symbol,
            as_of=max(as_of, retrieved) if live else as_of,
            retrieved_at=retrieved,
            adjustment_status=HistoricalAdjustmentStatus.RAW,
            certification=HistoricalBarCertification.UNVERIFIED,
            quality=HistoricalQuality.UNVERIFIED,
            source_mode="LIVE_SHADOW",
        )


class NasdaqHistoricalProvider:
    """Public Nasdaq daily-table fallback, normalized through Meridian's OHLCV gate."""

    provider_name = "nasdaq"
    network_capable = True

    def __init__(
        self,
        security_master: SecurityMaster,
        *,
        timeout_seconds: float = 10.0,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.security_master, self.timeout_seconds, self.opener = (
            security_master,
            timeout_seconds,
            opener,
        )
        self.clock = clock or (lambda: datetime.now(UTC))

    def get_series(
        self, symbol: str, start: date, end: date, *, as_of: datetime, live: bool = False
    ) -> HistoricalBarSeries:
        security = self.security_master.resolve(symbol)
        provider_symbol = security.provider_symbols.get(self.provider_name)
        if not provider_symbol:
            raise SecurityIdentityUnavailable("SECURITY_IDENTITY_UNAVAILABLE:nasdaq-symbol")
        assetclass = "etf" if security.asset_type.value == "ETF" else "stocks"
        query = urlencode(
            {
                "assetclass": assetclass,
                "fromdate": start.isoformat(),
                "todate": end.isoformat(),
                "limit": "5000",
            }
        )
        request = Request(
            f"https://api.nasdaq.com/api/quote/{url_quote(provider_symbol)}/historical?{query}",
            headers={"User-Agent": "Mozilla/5.0 MeridianAlpha/0.1", "Accept": "application/json"},
        )
        try:
            response = self.opener(request, timeout=self.timeout_seconds)
            try:
                payload = response.read()
            finally:
                close = getattr(response, "close", None)
                if close is not None:
                    close()
        except TimeoutError as error:
            raise HistoricalProviderTimeout("Nasdaq historical request timed out") from error
        except OSError as error:
            raise HistoricalProviderError("Nasdaq historical request failed") from error
        try:
            document = json.loads(
                payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
            )
            rows = ((document.get("data") or {}).get("tradesTable") or {}).get("rows") or []
            if not isinstance(rows, list) or not rows:
                raise ValueError("no historical rows")
        except (TypeError, ValueError, AttributeError) as error:
            raise HistoricalProviderMalformed("Nasdaq historical response is malformed") from error
        retrieved = self.clock()
        normalized: list[Mapping[str, Any]] = []

        def value(row: Mapping[str, Any], *keys: str) -> Any:
            for key in keys:
                candidate = row.get(key)
                if candidate not in (None, "", "N/A"):
                    return str(candidate).replace("$", "").replace(",", "")
            raise ValueError("Nasdaq historical field missing")

        try:
            for row in rows:
                if not isinstance(row, Mapping):
                    raise ValueError("Nasdaq historical row malformed")
                required_values = (
                    row.get("open") or row.get("openPrice"),
                    row.get("high") or row.get("highPrice"),
                    row.get("low") or row.get("lowPrice"),
                    row.get("close") or row.get("closePrice"),
                    row.get("volume") if row.get("volume") is not None else row.get("shareVolume"),
                )
                if any(value in (None, "", "N/A") for value in required_values):
                    continue
                raw_date = str(row.get("date") or row.get("tradeDate") or "")
                try:
                    session = datetime.strptime(raw_date, "%m/%d/%Y").date()
                except ValueError:
                    session = date.fromisoformat(raw_date[:10])
                if session < start or session > end or session > as_of.date():
                    continue
                if session_close(session, TradingCalendarName(security.trading_calendar)) > as_of:
                    continue
                normalized.append(
                    {
                        "provider_symbol": provider_symbol,
                        "session": session,
                        "open": value(row, "open", "openPrice"),
                        "high": value(row, "high", "highPrice"),
                        "low": value(row, "low", "lowPrice"),
                        "close": value(row, "close", "closePrice"),
                        "volume": value(row, "volume", "shareVolume"),
                        "currency": security.currency,
                        "observed_at": session_close(
                            session, TradingCalendarName(security.trading_calendar)
                        ),
                        "available_at": retrieved,
                        "source": "nasdaq-public-api",
                    }
                )
        except (TypeError, ValueError) as error:
            raise HistoricalProviderMalformed(
                "Nasdaq historical response has invalid OHLCV"
            ) from error
        if not normalized:
            raise HistoricalProviderMalformed("Nasdaq historical response contains no usable rows")
        return HistoricalDataNormalizer(
            self.security_master, provider=self.provider_name
        ).normalize(
            normalized,
            symbol=symbol,
            as_of=max(as_of, retrieved) if live else as_of,
            retrieved_at=retrieved,
            adjustment_status=HistoricalAdjustmentStatus.RAW,
            certification=HistoricalBarCertification.UNVERIFIED,
            quality=HistoricalQuality.UNVERIFIED,
            source_mode="LIVE_SHADOW",
        )
