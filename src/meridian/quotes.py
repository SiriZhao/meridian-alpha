"""Provider-neutral quote contracts and a conservative public shadow adapter."""

from __future__ import annotations

import csv
import io
import json
import time as _time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import quote as url_quote
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from meridian.schemas import StableModel
from meridian.security_master import SecurityIdentityUnavailable, SecurityMaster
from meridian.trading_calendar import (
    TradingCalendarName,
    is_trading_session,
    session_close,
    session_open,
)


class QuoteQualityStatus(StrEnum):
    VERIFIED = "VERIFIED"
    STALE = "STALE"
    FUTURE = "FUTURE"
    INVALID = "INVALID"
    BID_ASK_UNAVAILABLE = "BID_ASK_UNAVAILABLE"
    MARKET_DATA_CONFLICT = "MARKET_DATA_CONFLICT"
    UNVERIFIED = "UNVERIFIED"


class MarketSessionStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


class QuoteProviderError(RuntimeError):
    code = "PROVIDER_ERROR"


class QuoteProviderTimeout(QuoteProviderError):
    code = "PROVIDER_TIMEOUT"


class QuoteProviderMalformed(QuoteProviderError):
    code = "PROVIDER_MALFORMED_RESPONSE"


class MarketDataCapabilityCertificate(StableModel):
    provider_name: str = Field(min_length=1, max_length=128)
    supports_live: bool = False
    supports_historical: bool = False
    supports_point_in_time: bool = False
    supports_bid: bool = False
    supports_ask: bool = False
    supports_last: bool = False
    supports_ohlcv: bool = False
    supports_adjusted_data: bool = False
    supports_corporate_actions: bool = False
    timestamp_semantics: str = "UNVERIFIED"
    authentication_required: bool = False
    research_grade: bool = False
    execution_quote_grade: bool = False


# Short alias used by adapters and callers.
QuoteProviderCapabilities = MarketDataCapabilityCertificate


class QuoteObservation(StableModel):
    canonical_asset_id: str = Field(min_length=1, max_length=128)
    canonical_symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,15}$")
    provider: str = Field(min_length=1, max_length=128)
    provider_symbol: str = Field(min_length=1, max_length=128)
    observed_at: datetime
    available_at: datetime
    retrieved_at: datetime
    bid: Decimal | None = Field(default=None, ge=Decimal("0"))
    ask: Decimal | None = Field(default=None, ge=Decimal("0"))
    last: Decimal | None = Field(default=None, ge=Decimal("0"))
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    market_status: MarketSessionStatus = MarketSessionStatus.UNKNOWN
    source: str = Field(min_length=1, max_length=256)
    quality_status: QuoteQualityStatus = QuoteQualityStatus.UNVERIFIED
    stale_age_seconds: Decimal | None = Field(default=None, ge=Decimal("0"))
    shadow_only: bool = True

    @model_validator(mode="after")
    def validate_quote(self) -> QuoteObservation:
        for name, value in (
            ("observed_at", self.observed_at),
            ("retrieved_at", self.retrieved_at),
            ("available_at", self.available_at),
        ):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware")
        if self.available_at is not None and self.available_at > self.retrieved_at:
            raise ValueError("available_at must not be after retrieved_at")
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("bid must not exceed ask")
        if self.bid is None or self.ask is None:
            if self.quality_status is QuoteQualityStatus.VERIFIED:
                object.__setattr__(self, "quality_status", QuoteQualityStatus.BID_ASK_UNAVAILABLE)
        if self.last is None and self.bid is None and self.ask is None:
            raise ValueError("quote must contain at least one price")
        return self

    @property
    def executable_quote_grade(self) -> bool:
        return False


class MarketQuoteProvider(Protocol):
    provider_name: str
    capabilities: MarketDataCapabilityCertificate

    def get_quote(self, symbol: str, *, as_of: datetime | None = None) -> QuoteObservation: ...


class ShadowMarketDataPolicy:
    """Mechanical boundary: real observations remain non-executable in 3B.1."""

    mode = "REAL_SHADOW_MARKET_DATA"

    @staticmethod
    def allows_executable_authorization(quote: QuoteObservation) -> bool:
        _ = quote
        return False

    @staticmethod
    def require_non_executable(quote: QuoteObservation) -> None:
        if not quote.shadow_only:
            raise ValueError("Gate 3B.1 quotes must be marked shadow_only")
        raise ValueError("REAL_SHADOW_MARKET_DATA cannot authorize executable research")


def _decimal(value: Any, field: str) -> Decimal | None:
    if value is None or value == "" or str(value).upper() in {"N/D", "NA", "NONE"}:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"invalid numeric {field}") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"invalid numeric {field}")
    return parsed


class QuoteNormalizer:
    """Normalize raw provider mappings into Meridian-owned observations."""

    def __init__(self, security_master: SecurityMaster, *, max_age_seconds: int = 900):
        if max_age_seconds < 0:
            raise ValueError("max_age_seconds must be non-negative")
        self.security_master = security_master
        self.max_age_seconds = max_age_seconds

    def normalize(
        self,
        raw: Mapping[str, Any],
        *,
        symbol: str,
        provider: str,
        retrieved_at: datetime,
        source: str | None = None,
        as_of: datetime | None = None,
    ) -> QuoteObservation:
        if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        security = self.security_master.resolve(symbol)
        provider_symbol = str(raw.get("provider_symbol", "")).strip()
        expected_symbol = security.provider_symbols.get(provider)
        if not provider_symbol or expected_symbol != provider_symbol:
            raise SecurityIdentityUnavailable("SECURITY_IDENTITY_UNAVAILABLE:provider-symbol-mismatch")
        observed = self._timestamp(raw.get("observed_at"))
        if observed > retrieved_at:
            raise ValueError("quote observed_at cannot be in the future")
        if as_of is not None:
            if as_of.tzinfo is None or as_of.utcoffset() is None:
                raise ValueError("as_of must be timezone-aware")
            if observed > as_of:
                raise ValueError("quote observed_at is after as_of")
        available = self._timestamp(raw.get("available_at", observed))
        if available > retrieved_at or (as_of is not None and available > as_of):
            raise ValueError("quote available_at cannot be in the future")
        currency = str(raw.get("currency", "")).upper()
        if currency != security.currency:
            raise ValueError("quote currency does not match security master")
        bid = _decimal(raw.get("bid"), "bid")
        ask = _decimal(raw.get("ask"), "ask")
        last = _decimal(raw.get("last"), "last")
        if bid is not None and ask is not None and bid > ask:
            raise ValueError("bid must not exceed ask")
        age = max(Decimal("0"), Decimal(str((retrieved_at - observed).total_seconds())))
        quality = QuoteQualityStatus.VERIFIED
        if age > self.max_age_seconds:
            quality = QuoteQualityStatus.STALE
        elif bid is None or ask is None:
            quality = QuoteQualityStatus.BID_ASK_UNAVAILABLE
        market_status = MarketSessionStatus.UNKNOWN
        try:
            local = observed.astimezone(ZoneInfo(security.timezone))
            local_date = local.date()
            cal = TradingCalendarName(security.trading_calendar)
            if not is_trading_session(local_date, cal):
                market_status = MarketSessionStatus.CLOSED
            elif local < session_open(local_date, cal).astimezone(local.tzinfo):
                market_status = MarketSessionStatus.CLOSED
            elif local >= session_close(local_date, cal).astimezone(local.tzinfo):
                market_status = MarketSessionStatus.CLOSED
            else:
                market_status = MarketSessionStatus.INCOMPLETE
        except Exception:
            market_status = MarketSessionStatus.UNKNOWN
        return QuoteObservation(
            canonical_asset_id=security.canonical_asset_id,
            canonical_symbol=security.canonical_symbol,
            provider=provider,
            provider_symbol=provider_symbol,
            observed_at=observed,
            available_at=available,
            retrieved_at=retrieved_at,
            bid=bid,
            ask=ask,
            last=last,
            currency=currency,
            market_status=market_status,
            source=source or provider,
            quality_status=quality,
            stale_age_seconds=age,
            shadow_only=True,
        )

    @staticmethod
    def _timestamp(value: Any) -> datetime:
        if isinstance(value, datetime):
            result = value
        elif isinstance(value, str):
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            raise ValueError("quote timestamp is required")
        if result.tzinfo is None or result.utcoffset() is None:
            raise ValueError("quote timestamp must be timezone-aware")
        return result


class StooqQuoteProvider:
    """Free public last-price adapter for shadow observation only.

    Stooq supplies delayed/last data in a compact CSV response and does not
    expose a dependable bid/ask stream here; the capability certificate is
    therefore explicitly non-execution-grade.
    """

    provider_name = "stooq-public"
    network_capable = True
    capabilities = MarketDataCapabilityCertificate(
        provider_name=provider_name,
        supports_live=False,
        supports_historical=False,
        supports_point_in_time=False,
        supports_last=True,
        timestamp_semantics="provider quote date/time; freshness must be measured locally",
        authentication_required=False,
        research_grade=False,
        execution_quote_grade=False,
    )

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

    def get_quote(self, symbol: str, *, as_of: datetime | None = None) -> QuoteObservation:
        security = self.security_master.resolve(symbol)
        provider_symbol = security.provider_symbols.get(self.provider_name.removesuffix("-public"))
        if provider_symbol is None:
            provider_symbol = security.provider_symbols.get("stooq")
        if not provider_symbol:
            raise SecurityIdentityUnavailable("SECURITY_IDENTITY_UNAVAILABLE:stooq-symbol")
        url = f"https://stooq.com/q/l/?s={url_quote(provider_symbol)}&f=sd2t2ohlcv&h&e=csv"
        request = Request(url, headers={"User-Agent": "MeridianAlpha/0.1 shadow-data"})
        started = _time.monotonic()
        try:
            response = self.opener(request, timeout=self.timeout_seconds)
            payload = response.read()
        except TimeoutError as error:
            raise QuoteProviderTimeout("Stooq request timed out") from error
        except OSError as error:
            raise QuoteProviderError("Stooq request failed") from error
        if _time.monotonic() - started > self.timeout_seconds * 2:
            raise QuoteProviderTimeout("Stooq response exceeded timeout budget")
        try:
            text = payload.decode("utf-8") if isinstance(payload, bytes) else str(payload)
            row = next(csv.DictReader(io.StringIO(text)))
            if not row or row.get("Close") in {None, "N/D", ""}:
                raise ValueError("missing Stooq close")
            quote_time = datetime.fromisoformat(f"{row['Date']}T{row['Time']}").replace(tzinfo=UTC)
        except (StopIteration, KeyError, ValueError) as error:
            raise QuoteProviderMalformed("Stooq response is malformed") from error
        retrieved = self.clock()
        return QuoteNormalizer(self.security_master).normalize(
            {"provider_symbol": provider_symbol, "observed_at": quote_time, "last": row["Close"], "currency": security.currency},
            symbol=symbol,
            provider="stooq",
            retrieved_at=retrieved,
            source="stooq-public-csv",
            as_of=as_of,
        )


class QuoteComparison(StableModel):
    symbol: str
    providers: tuple[str, ...]
    differing_fields: tuple[str, ...] = ()
    status: QuoteQualityStatus = QuoteQualityStatus.VERIFIED
    warnings: tuple[str, ...] = ()


def compare_quotes(quotes: tuple[QuoteObservation, ...], *, last_tolerance: Decimal = Decimal("0.01")) -> QuoteComparison:
    if not quotes:
        raise ValueError("at least one quote is required")
    symbol = quotes[0].canonical_symbol
    differing: list[str] = []
    for quote in quotes[1:]:
        if quote.canonical_asset_id != quotes[0].canonical_asset_id:
            differing.append("identity")
        if quote.currency != quotes[0].currency:
            differing.append("currency")
        if quote.last is not None and quotes[0].last is not None and abs(quote.last - quotes[0].last) > last_tolerance:
            differing.append("last")
        if quote.bid != quotes[0].bid:
            differing.append("bid")
        if quote.ask != quotes[0].ask:
            differing.append("ask")
        if quote.observed_at != quotes[0].observed_at:
            differing.append("timestamp")
        if quote.market_status != quotes[0].market_status:
            differing.append("session")
    fields = tuple(sorted(set(differing)))
    return QuoteComparison(
        symbol=symbol,
        providers=tuple(quote.provider for quote in quotes),
        differing_fields=fields,
        status=QuoteQualityStatus.MARKET_DATA_CONFLICT if fields else QuoteQualityStatus.VERIFIED,
        warnings=("MARKET_DATA_CONFLICT",) if fields else (),
    )









class YahooChartQuoteProvider:
    """Public Yahoo chart quote adapter for bounded SHADOW observations.

    The chart endpoint exposes a last/regular-market price but no dependable
    bid/ask stream in this contract.  We therefore advertise last-only,
    non-execution capabilities and retain the provider timestamp semantics as
    unverified until supervised review.
    """

    provider_name = "yahoo"
    network_capable = True
    capabilities = MarketDataCapabilityCertificate(
        provider_name=provider_name,
        supports_live=True,
        supports_historical=True,
        supports_point_in_time=False,
        supports_last=True,
        supports_ohlcv=True,
        supports_adjusted_data=False,
        supports_corporate_actions=False,
        timestamp_semantics="Yahoo chart regularMarketTime; exchange timezone/delay requires review",
        authentication_required=False,
        research_grade=False,
        execution_quote_grade=False,
    )

    def __init__(
        self,
        security_master: SecurityMaster,
        *,
        timeout_seconds: float = 8.0,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.security_master = security_master
        self.timeout_seconds = timeout_seconds
        self.opener = opener
        self.clock = clock or (lambda: datetime.now(UTC))

    def get_quote(self, symbol: str, *, as_of: datetime | None = None) -> QuoteObservation:
        security = self.security_master.resolve(symbol)
        provider_symbol = security.provider_symbols.get(self.provider_name)
        if not provider_symbol:
            raise SecurityIdentityUnavailable("SECURITY_IDENTITY_UNAVAILABLE:yahoo-symbol")
        query = urlencode({"range": "5d", "interval": "1d", "events": "div,splits"})
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{url_quote(provider_symbol)}?{query}"
        request = Request(url, headers={"User-Agent": "MeridianAlpha/0.1 shadow-data"})
        started = _time.monotonic()
        try:
            response = self.opener(request, timeout=self.timeout_seconds)
            status = getattr(response, "status", getattr(response, "code", None))
            try:
                status_code = int(status) if status is not None else None
            except (TypeError, ValueError):
                status_code = None
            if status_code is not None and status_code >= 400:
                raise QuoteProviderError(f"Yahoo chart HTTP error: {status_code}")
            payload = response.read()
        except TimeoutError as error:
            raise QuoteProviderTimeout("Yahoo chart request timed out") from error
        except OSError as error:
            raise QuoteProviderError("Yahoo chart request failed") from error
        if _time.monotonic() - started > self.timeout_seconds * 2:
            raise QuoteProviderTimeout("Yahoo chart response exceeded timeout budget")
        try:
            document = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else str(payload))
            result = document["chart"]["result"][0]
            meta = result["meta"]
            price = meta.get("regularMarketPrice")
            epoch = meta.get("regularMarketTime")
            if price is None or epoch is None:
                timestamps = result.get("timestamp") or []
                closes = ((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
                valid = [(ts, close) for ts, close in zip(timestamps, closes, strict=False) if close is not None]
                if not valid:
                    raise ValueError("Yahoo chart response has no last price")
                epoch, price = valid[-1]
            observed = datetime.fromtimestamp(float(epoch), tz=UTC)
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise QuoteProviderMalformed("Yahoo chart response is malformed") from error
        retrieved = self.clock()
        return QuoteNormalizer(self.security_master).normalize(
            {
                "provider_symbol": provider_symbol,
                "observed_at": observed,
                "available_at": observed,
                "last": price,
                "currency": str(meta.get("currency") or security.currency),
            },
            symbol=symbol,
            provider=self.provider_name,
            retrieved_at=retrieved,
            source="yahoo-chart-public",
            as_of=as_of,
        )


# Gate 4G keeps execution quotes in a separate module/type hierarchy. These
# aliases are convenience imports only; Yahoo/Stooq observations remain
# research-shadow and cannot be converted implicitly.
from meridian.execution_quotes import (  # noqa: E402,F401
    ExecutionQuote,
    ExecutionQuoteCapabilityCertificate,
    ExecutionQuoteProvider,
    ExecutionQuoteStatus,
    ExecutionQuoteValidation,
    ExecutionQuoteValidator,
    ExecutionSession,
    ManualLimitPricePolicy,
    ManualOrderDraft,
    ResearchMarketPrice,
    ValuationMark,
)

ExecutionQuoteCertificate = ExecutionQuoteCapabilityCertificate
