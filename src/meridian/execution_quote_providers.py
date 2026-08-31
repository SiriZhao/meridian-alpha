"""Read-only execution-quote candidate adapters and safe preflight diagnostics.

These adapters deliberately stop at market-data retrieval.  They do not expose
orders, accounts, authentication flows, or mutation methods.  Capability
certificates remain non-execution-grade until a supervised plan/feed review
proves timestamp, session, delay, rate-limit, and licensing semantics.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from datetime import time as dt_time
from decimal import Decimal
from enum import StrEnum
from typing import Any
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from meridian.execution_quotes import (
    ExecutionQuote,
    ExecutionQuoteCapabilityCertificate,
    ExecutionSession,
)
from meridian.schemas import StableModel
from meridian.security_master import DEFAULT_SECURITY_MASTER, SecurityMaster


class QuotePreflightResult(StableModel):
    """Sanitized provider-health output; credentials and headers never appear."""

    class Status(StrEnum):
        AVAILABLE = "AVAILABLE"
        DEGRADED = "DEGRADED"
        STALE = "STALE"
        UNAVAILABLE = "UNAVAILABLE"
        UNVERIFIED = "UNVERIFIED"

    provider: str = Field(min_length=1, max_length=128)
    configured: bool
    endpoint_reachable: bool
    plan_or_feed: str | None = None
    quote_returned: bool
    certificate_eligible: bool
    status: Status = Status.UNVERIFIED
    reason: str = Field(min_length=1, max_length=512)
    checked_at: datetime
    symbols_checked: tuple[str, ...] = ()

    @model_validator(mode="after")
    def classify(self) -> QuotePreflightResult:
        if not self.configured:
            value = self.Status.UNAVAILABLE
        elif not self.endpoint_reachable:
            value = self.Status.UNVERIFIED if self.reason.startswith("PROBE_NOT_REQUESTED") else self.Status.UNAVAILABLE
        elif self.certificate_eligible:
            value = self.Status.AVAILABLE
        else:
            value = self.Status.UNVERIFIED
        object.__setattr__(self, "status", value)
        return self


ProviderHealthStatus = QuotePreflightResult.Status

def _utc_from_epoch(value: Any) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str) and ("T" in value or value.endswith("Z")):
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        number = float(value)
        # Alpaca and Polygon use nanoseconds; tolerate milliseconds/seconds too.
        if number > 10**17:
            number /= 1_000_000_000
        elif number > 10**14:
            number /= 1_000_000
        elif number > 10**11:
            number /= 1_000
        result = datetime.fromtimestamp(number, tz=UTC)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("provider timestamp must be timezone-aware")
    return result.astimezone(UTC)


def _session(timestamp: datetime, *, timezone: str = "America/New_York") -> tuple[ExecutionSession, bool]:
    """Conservative US-equity session classification for quote diagnostics."""

    local = timestamp.astimezone(ZoneInfo(timezone))
    if local.weekday() >= 5:
        return ExecutionSession.CLOSED, False
    value = local.time()
    if value < dt_time(4, 0):
        return ExecutionSession.CLOSED, False
    if value < dt_time(9, 30):
        return ExecutionSession.PRE_MARKET, True
    if value < dt_time(16, 0):
        return ExecutionSession.REGULAR, False
    if value < dt_time(20, 0):
        return ExecutionSession.AFTER_HOURS, True
    return ExecutionSession.CLOSED, False


def _first(mapping: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None


class _CandidateBase:
    """Shared, network-only read path for candidate market-data providers."""

    network_capable = True
    provider_name: str
    feed_name: str
    capabilities: ExecutionQuoteCapabilityCertificate

    def __init__(
        self,
        security_master: SecurityMaster = DEFAULT_SECURITY_MASTER,
        *,
        timeout_seconds: float = 8.0,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.security_master = security_master
        self.timeout_seconds = timeout_seconds
        self.opener = opener
        self.clock = clock or (lambda: datetime.now(UTC))

    @property
    def configured(self) -> bool:
        return bool(self._credential())

    def _credential(self) -> str | None:
        raise NotImplementedError

    def get_quote(self, symbol: str, *, as_of: datetime | None = None) -> ExecutionQuote:
        raise NotImplementedError

    def _request_json(self, url: str, *, headers: Mapping[str, str]) -> dict[str, Any]:
        request = Request(url, headers={"User-Agent": "MeridianAlpha/0.1 read-only", **headers})
        started = time.monotonic()
        try:
            response = self.opener(request, timeout=self.timeout_seconds)
            payload = response.read()
        except (OSError, TimeoutError) as error:
            raise RuntimeError("PROVIDER_UNAVAILABLE") from error
        if time.monotonic() - started > self.timeout_seconds * 2:
            raise RuntimeError("PROVIDER_TIMEOUT")
        try:
            value = json.loads(payload.decode("utf-8") if isinstance(payload, bytes) else str(payload))
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise RuntimeError("PROVIDER_MALFORMED_RESPONSE") from error
        if not isinstance(value, dict):
            raise RuntimeError("PROVIDER_MALFORMED_RESPONSE")
        return value

    def _identity(self, symbol: str) -> tuple[str, str, str]:
        security = self.security_master.resolve(symbol)
        return security.canonical_symbol, security.currency, security.timezone

    def _quote(
        self,
        *,
        symbol: str,
        provider_symbol: str,
        bid: Any,
        ask: Any,
        last: Any,
        timestamp: Any,
        certificate_id: str,
        timezone: str,
        as_of: datetime | None,
    ) -> ExecutionQuote:
        canonical, currency, _ = self._identity(symbol)
        if bid is None or ask is None or last is None or timestamp is None:
            raise RuntimeError("PROVIDER_MALFORMED_RESPONSE:bid_ask_last_timestamp_required")
        observed = _utc_from_epoch(timestamp)
        retrieved = self.clock().astimezone(UTC)
        if as_of is not None and observed > as_of:
            raise ValueError("quote timestamp is after as_of")
        session, extended = _session(observed, timezone=timezone)
        return ExecutionQuote(
            symbol=canonical,
            provider_symbol=provider_symbol,
            bid=Decimal(str(bid)),
            ask=Decimal(str(ask)),
            last=Decimal(str(last)),
            timestamp=observed,
            session=session,
            currency=currency,
            provider=self.provider_name,
            retrieved_at=retrieved,
            available_at=observed,
            extended_hours=extended,
            certificate_id=certificate_id,
        )

    def preflight(self, *, symbols: tuple[str, ...] = ("AAPL",), probe: bool = False) -> QuotePreflightResult:
        checked = tuple(symbol.upper() for symbol in symbols)
        now = self.clock().astimezone(UTC)
        if not self.configured:
            return QuotePreflightResult(
                provider=self.provider_name,
                configured=False,
                endpoint_reachable=False,
                plan_or_feed=None,
                quote_returned=False,
                certificate_eligible=False,
                reason="NO_LOCAL_PROVIDER_CREDENTIAL_CONFIGURED",
                checked_at=now,
                symbols_checked=checked,
            )
        if not probe:
            return QuotePreflightResult(
                provider=self.provider_name,
                configured=True,
                endpoint_reachable=False,
                plan_or_feed=self.feed_name,
                quote_returned=False,
                certificate_eligible=False,
                reason="PROBE_NOT_REQUESTED_READ_ONLY_CONFIGURATION_ONLY",
                checked_at=now,
                symbols_checked=checked,
            )
        for symbol in checked:
            try:
                self.get_quote(symbol, as_of=now)
            except Exception as error:  # noqa: BLE001 - sanitized provider diagnostic
                return QuotePreflightResult(
                    provider=self.provider_name,
                    configured=True,
                    endpoint_reachable=False,
                    plan_or_feed=self.feed_name,
                    quote_returned=False,
                    certificate_eligible=False,
                    reason=f"{type(error).__name__}:{str(error)[:400]}",
                    checked_at=self.clock().astimezone(UTC),
                    symbols_checked=checked,
                )
        return QuotePreflightResult(
            provider=self.provider_name,
            configured=True,
            endpoint_reachable=True,
            plan_or_feed=self.feed_name,
            quote_returned=True,
            certificate_eligible=self.capabilities.execution_quote_grade,
            reason=(
                "QUOTE_RETURNED_BUT_CAPABILITY_CERTIFICATE_REVIEW_REQUIRED"
                if not self.capabilities.execution_quote_grade
                else "CAPABILITY_CERTIFICATE_ELIGIBLE"
            ),
            checked_at=self.clock().astimezone(UTC),
            symbols_checked=checked,
        )


class AlpacaExecutionQuoteProvider(_CandidateBase):
    """Alpaca market-data candidate; latest quote/trade only, no trading API."""

    provider_name = "alpaca-market-data"
    feed_name = "ALPACA_DATA_FEED_UNVERIFIED"
    capabilities = ExecutionQuoteCapabilityCertificate(
        provider=provider_name,
        bid=True,
        ask=True,
        last=True,
        timestamp_semantics_verified=False,
        freshness_policy="UNVERIFIED_PLAN_FEED",
        session_semantics="UNVERIFIED",
        supports_stocks=True,
        supports_etfs=True,
        source_uri="https://docs.alpaca.markets/reference/stocklatestquotes-1",
        execution_quote_grade=False,
    )

    def _credential(self) -> str | None:
        return os.getenv("APCA_API_KEY_ID") or os.getenv("ALPACA_API_KEY")

    @property
    def configured(self) -> bool:
        return bool(self._credential() and self._secret)

    @property
    def _secret(self) -> str | None:
        return os.getenv("APCA_API_SECRET_KEY") or os.getenv("ALPACA_API_SECRET")

    def get_quote(self, symbol: str, *, as_of: datetime | None = None) -> ExecutionQuote:
        canonical, currency, timezone = self._identity(symbol)
        key = self._credential()
        secret = self._secret
        if not key or not secret:
            raise RuntimeError("PROVIDER_UNAVAILABLE:NO_LOCAL_PROVIDER_CREDENTIAL_CONFIGURED")
        base = os.getenv("ALPACA_DATA_ENDPOINT", "https://data.alpaca.markets").rstrip("/")
        encoded = quote(canonical, safe="")
        headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        quote_doc = self._request_json(f"{base}/v2/stocks/{encoded}/quotes/latest", headers=headers)
        trade_doc = self._request_json(f"{base}/v2/stocks/{encoded}/trades/latest", headers=headers)
        quote_row = quote_doc.get("quote") if isinstance(quote_doc.get("quote"), dict) else quote_doc
        trade_row = trade_doc.get("trade") if isinstance(trade_doc.get("trade"), dict) else trade_doc
        if not isinstance(quote_row, dict) or not isinstance(trade_row, dict):
            raise RuntimeError("PROVIDER_MALFORMED_RESPONSE")
        timestamp = _first(quote_row, "t", "timestamp")
        trade_timestamp = _first(trade_row, "t", "timestamp")
        if trade_timestamp is not None:
            timestamp = max(_utc_from_epoch(timestamp), _utc_from_epoch(trade_timestamp)) if timestamp is not None else trade_timestamp
        return self._quote(
            symbol=canonical,
            provider_symbol=canonical,
            bid=_first(quote_row, "bp", "bid_price", "bid"),
            ask=_first(quote_row, "ap", "ask_price", "ask"),
            last=_first(trade_row, "p", "price", "last"),
            timestamp=timestamp,
            certificate_id="alpaca-market-data-candidate-v1",
            timezone=timezone,
            as_of=as_of,
        )


class PolygonExecutionQuoteProvider(_CandidateBase):
    """Polygon market-data candidate; v3 quote plus last-trade read only."""

    provider_name = "polygon-market-data"
    feed_name = "POLYGON_PLAN_FEED_UNVERIFIED"
    capabilities = ExecutionQuoteCapabilityCertificate(
        provider=provider_name,
        bid=True,
        ask=True,
        last=True,
        timestamp_semantics_verified=False,
        freshness_policy="UNVERIFIED_PLAN_FEED",
        session_semantics="UNVERIFIED",
        supports_stocks=True,
        supports_etfs=True,
        source_uri="https://polygon.io/docs/stocks/get_v3_quotes__stockticker",
        execution_quote_grade=False,
    )

    def _credential(self) -> str | None:
        return os.getenv("POLYGON_API_KEY") or os.getenv("POLYGON_KEY")

    def get_quote(self, symbol: str, *, as_of: datetime | None = None) -> ExecutionQuote:
        canonical, currency, timezone = self._identity(symbol)
        key = self._credential()
        if not key:
            raise RuntimeError("PROVIDER_UNAVAILABLE:NO_LOCAL_PROVIDER_CREDENTIAL_CONFIGURED")
        base = os.getenv("POLYGON_DATA_ENDPOINT", "https://api.polygon.io").rstrip("/")
        encoded = quote(canonical, safe="")
        # API keys are sent only in the request URL and never included in diagnostics.
        quote_url = f"{base}/v3/quotes/{encoded}?{urlencode({'limit': 1, 'sort': 'timestamp', 'order': 'desc', 'apiKey': key})}"
        trade_url = f"{base}/v2/last/trade/{encoded}?{urlencode({'apiKey': key})}"
        quote_doc = self._request_json(quote_url, headers={})
        trade_doc = self._request_json(trade_url, headers={})
        rows = quote_doc.get("results")
        trade_row = trade_doc.get("results")
        quote_row = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else None
        if not isinstance(quote_row, dict) or not isinstance(trade_row, dict):
            raise RuntimeError("PROVIDER_MALFORMED_RESPONSE")
        quote_time = _first(quote_row, "sip_timestamp", "participant_timestamp", "timestamp")
        trade_time = _first(trade_row, "sip_timestamp", "participant_timestamp", "timestamp", "t")
        timestamp = quote_time
        if trade_time is not None:
            timestamp = max(_utc_from_epoch(quote_time), _utc_from_epoch(trade_time)) if quote_time is not None else trade_time
        return self._quote(
            symbol=canonical,
            provider_symbol=canonical,
            bid=_first(quote_row, "bid_price", "bp"),
            ask=_first(quote_row, "ask_price", "ap"),
            last=_first(trade_row, "price", "p"),
            timestamp=timestamp,
            certificate_id="polygon-market-data-candidate-v1",
            timezone=timezone,
            as_of=as_of,
        )


def provider_preflight(*, probe: bool = False, symbols: tuple[str, ...] = ("AAPL", "NVDA", "SPY")) -> tuple[QuotePreflightResult, ...]:
    """Return bounded, sanitized diagnostics for both candidate providers."""

    return tuple(provider.preflight(symbols=symbols, probe=probe) for provider in (AlpacaExecutionQuoteProvider(), PolygonExecutionQuoteProvider()))


def provider_endpoint_host(provider: str) -> str | None:
    """Expose only endpoint host metadata for review reports."""

    value = {
        "alpaca-market-data": os.getenv("ALPACA_DATA_ENDPOINT", "https://data.alpaca.markets"),
        "polygon-market-data": os.getenv("POLYGON_DATA_ENDPOINT", "https://api.polygon.io"),
    }.get(provider)
    return urlparse(value).hostname if value else None


__all__ = [
    "AlpacaExecutionQuoteProvider",
    "PolygonExecutionQuoteProvider",
    "ProviderHealthStatus",
    "QuotePreflightResult",
    "provider_endpoint_host",
    "provider_preflight",
]
