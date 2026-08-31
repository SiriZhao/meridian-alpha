"""Execution-quote certification contracts.

Yahoo/Stooq observations remain research-shadow data.  The types in this
module are intentionally disjoint from those observations and require a
provider capability certificate before a manual-ticket quote can be created.
There are no trade, account, or broker methods here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum
from typing import Any, Protocol

from pydantic import Field, model_validator

from meridian.schemas import Side, StableModel
from meridian.security_master import AssetType, SecurityMaster


class ExecutionQuoteStatus(StrEnum):
    VALID = "VALID"
    MISSING_BID = "MISSING_BID"
    MISSING_ASK = "MISSING_ASK"
    NON_POSITIVE = "NON_POSITIVE"
    INVERTED = "INVERTED"
    WIDE_SPREAD = "WIDE_SPREAD"
    STALE = "STALE"
    FUTURE = "FUTURE"
    WRONG_TICKER = "WRONG_TICKER"
    WRONG_CURRENCY = "WRONG_CURRENCY"
    UNKNOWN_SESSION = "UNKNOWN_SESSION"
    EXTENDED_HOURS_UNSUPPORTED = "EXTENDED_HOURS_UNSUPPORTED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    UNVERIFIED_PROVIDER = "UNVERIFIED_PROVIDER"
    UNSUPPORTED_ASSET_CLASS = "UNSUPPORTED_ASSET_CLASS"


class ExecutionSession(StrEnum):
    REGULAR = "REGULAR"
    PRE_MARKET = "PRE_MARKET"
    AFTER_HOURS = "AFTER_HOURS"
    CLOSED = "CLOSED"


class ExecutionQuoteCapabilityCertificate(StableModel):
    """Documented provider capabilities; all execution fields are explicit."""

    provider: str = Field(min_length=1, max_length=128)
    # Compatibility spellings used by the provider-neutral certificate while
    # retaining the concise gate fields above.
    supports_bid: bool = False
    supports_ask: bool = False
    supports_last: bool = False
    bid: bool = False
    ask: bool = False
    last: bool = False
    timestamp_semantics_verified: bool = False
    freshness_policy: str = Field(default="UNVERIFIED", min_length=1, max_length=512)
    session_semantics: str = Field(default="UNVERIFIED", min_length=1, max_length=512)
    supports_stocks: bool = False
    supports_etfs: bool = False
    supports_indices: bool = False
    supports_extended_hours: bool = False
    authentication: str = Field(default="UNVERIFIED", max_length=256)
    rate_limits: str = Field(default="UNVERIFIED", max_length=256)
    licensing: str = Field(default="UNVERIFIED", max_length=512)
    source_uri: str | None = Field(default=None, max_length=2000)
    certified_at: datetime | None = None
    execution_quote_grade: bool = False
    certificate_id: str = "UNSPECIFIED"
    feed: str = "UNVERIFIED"
    plan: str = "UNVERIFIED"
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    symbol_scope: tuple[str, ...] = ()
    currency_scope: tuple[str, ...] = ()
    capability_hash: str | None = None

    @model_validator(mode="after")
    def enforce_grade(self) -> ExecutionQuoteCapabilityCertificate:
        if self.supports_bid:
            object.__setattr__(self, "bid", True)
        if self.supports_ask:
            object.__setattr__(self, "ask", True)
        if self.supports_last:
            object.__setattr__(self, "last", True)
        required = self.bid and self.ask and self.last and self.timestamp_semantics_verified
        if self.execution_quote_grade and not required:
            raise ValueError("execution quote certificate is missing required capabilities")
        if self.execution_quote_grade:
            if self.source_uri is None or not self.source_uri.startswith("https://"):
                raise ValueError("execution quote certificate requires documented HTTPS source")
            if self.certified_at is None:
                raise ValueError("execution quote certificate requires certified_at")
            if self.freshness_policy == "UNVERIFIED" or self.session_semantics == "UNVERIFIED":
                raise ValueError("execution quote certificate requires freshness and session semantics")
        return self

    @property
    def is_certified(self) -> bool:
        return self.execution_quote_grade


    @property
    def computed_capability_hash(self) -> str:
        """Digest of declared capabilities, excluding the self-reported hash."""
        payload = self.model_dump(mode="json", exclude={"capability_hash"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ExecutionQuote(StableModel):
    """A current, identity-bound quote suitable for deterministic ticket pricing."""

    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,15}$")
    provider_symbol: str = Field(min_length=1, max_length=128)
    bid: Decimal = Field(gt=Decimal("0"), max_digits=18, decimal_places=8)
    ask: Decimal = Field(gt=Decimal("0"), max_digits=18, decimal_places=8)
    last: Decimal = Field(gt=Decimal("0"), max_digits=18, decimal_places=8)
    timestamp: datetime
    session: ExecutionSession
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    provider: str = Field(min_length=1, max_length=128)
    retrieved_at: datetime
    available_at: datetime | None = None
    extended_hours: bool = False
    certificate_id: str = Field(min_length=1, max_length=128)
    # Optional feed/plan binding lets a certificate prove the exact stream
    # used for this observation while preserving provider-neutral fixtures.
    feed: str | None = Field(default=None, max_length=128)
    plan: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def validate_quote(self) -> ExecutionQuote:
        for name in ("timestamp", "retrieved_at", "available_at"):
            value = getattr(self, name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware")
        if self.timestamp > self.retrieved_at:
            raise ValueError("execution quote timestamp cannot be in the future of retrieval")
        if self.available_at is not None and self.available_at > self.retrieved_at:
            raise ValueError("execution quote available_at cannot be after retrieval")
        if self.bid > self.ask:
            raise ValueError("execution quote bid must not exceed ask")
        if self.session in {ExecutionSession.PRE_MARKET, ExecutionSession.AFTER_HOURS} and not self.extended_hours:
            raise ValueError("extended-hours quote requires explicit extended_hours=true")
        return self

    @property
    def spread(self) -> Decimal:
        return (self.ask - self.bid) / self.last

    @property
    def spread_bps(self) -> Decimal:
        return self.spread * Decimal("10000")

    @property
    def executable_quote_grade(self) -> bool:
        """True only for this strict type; provider certification is separate."""
        return True

    def is_fresh(self, as_of: datetime, *, max_age_seconds: int = 30) -> bool:
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        age = (as_of - self.timestamp).total_seconds()
        return 0 <= age <= max_age_seconds


class ExecutionQuoteValidation(StableModel):
    valid: bool
    status: ExecutionQuoteStatus
    reason: str
    quote: ExecutionQuote | None = None


class ExecutionQuoteProvider(Protocol):
    provider_name: str
    capabilities: ExecutionQuoteCapabilityCertificate

    def get_quote(self, symbol: str, *, as_of: datetime | None = None) -> ExecutionQuote: ...


class ExecutionQuoteValidator:
    """Pure validator for provider output; it has no network behavior."""

    def __init__(
        self,
        security_master: SecurityMaster,
        *,
        max_age_seconds: int = 30,
        max_spread: Decimal = Decimal("0.02"),
    ) -> None:
        if max_age_seconds < 0 or max_spread <= 0:
            raise ValueError("invalid quote validation policy")
        self.security_master = security_master
        self.max_age_seconds = max_age_seconds
        self.max_spread = max_spread

    def validate(
        self,
        raw: ExecutionQuote | dict[str, Any],
        *,
        symbol: str,
        now: datetime,
        certificate: ExecutionQuoteCapabilityCertificate,
    ) -> ExecutionQuoteValidation:
        try:
            security = self.security_master.resolve(symbol)
        except ValueError as error:
            return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.WRONG_TICKER, reason=str(error))
        if not certificate.execution_quote_grade:
            return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.UNVERIFIED_PROVIDER, reason="provider capability is not execution-certified")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("quote validation now must be timezone-aware")
        try:
            data = raw.model_dump() if isinstance(raw, ExecutionQuote) else dict(raw)
            requested = str(data.get("symbol", "")).upper()
            if requested != security.canonical_symbol:
                return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.WRONG_TICKER, reason="quote ticker does not match canonical security")
            if str(data.get("currency", "")).upper() != security.currency:
                return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.WRONG_CURRENCY, reason="quote currency does not match security")
            if str(data.get("provider", "")) != certificate.provider:
                return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.UNVERIFIED_PROVIDER, reason="quote provider does not match capability certificate")
            if security.asset_type is AssetType.EQUITY and not certificate.supports_stocks:
                return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.UNSUPPORTED_ASSET_CLASS, reason="provider has no certified equity coverage")
            if security.asset_type is AssetType.ETF and not certificate.supports_etfs:
                return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.UNSUPPORTED_ASSET_CLASS, reason="provider has no certified ETF coverage")
            if security.asset_type is AssetType.INDEX and not certificate.supports_indices:
                return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.UNSUPPORTED_ASSET_CLASS, reason="provider has no certified index coverage")
            expected_provider_symbol = security.provider_symbols.get(certificate.provider, security.canonical_symbol)
            if str(data.get("provider_symbol", "")) != expected_provider_symbol:
                return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.WRONG_TICKER, reason="provider symbol does not match certified mapping")
            if data.get("bid") is None:
                return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.MISSING_BID, reason="bid is required")
            if data.get("ask") is None:
                return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.MISSING_ASK, reason="ask is required")
            quote = ExecutionQuote.model_validate({**data, "symbol": requested, "currency": security.currency})
        except ValueError as error:
            message = str(error)
            if "future of retrieval" in message or "after retrieval" in message:
                status = ExecutionQuoteStatus.FUTURE
            elif "must not exceed" in message:
                status = ExecutionQuoteStatus.INVERTED
            elif "greater than 0" in message:
                status = ExecutionQuoteStatus.NON_POSITIVE
            elif "session" in message:
                status = ExecutionQuoteStatus.UNKNOWN_SESSION
            else:
                status = ExecutionQuoteStatus.PROVIDER_UNAVAILABLE
            return ExecutionQuoteValidation(valid=False, status=status, reason=message)
        age = (now - quote.timestamp).total_seconds()
        if age < 0:
            return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.FUTURE, reason="quote timestamp is in the future")
        if age > self.max_age_seconds:
            return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.STALE, reason="quote exceeds freshness policy")
        if quote.spread > self.max_spread:
            return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.WIDE_SPREAD, reason="quote spread exceeds policy")
        if quote.session in {ExecutionSession.PRE_MARKET, ExecutionSession.AFTER_HOURS} and not certificate.supports_extended_hours:
            return ExecutionQuoteValidation(valid=False, status=ExecutionQuoteStatus.EXTENDED_HOURS_UNSUPPORTED, reason="provider has no certified extended-hours semantics")
        return ExecutionQuoteValidation(valid=True, status=ExecutionQuoteStatus.VALID, reason="quote passed certified provider and freshness checks", quote=quote)

    def require_valid(self, raw: ExecutionQuote | dict[str, Any], **kwargs: Any) -> ExecutionQuote:
        result = self.validate(raw, **kwargs)
        if not result.valid or result.quote is None:
            raise ValueError(f"EXECUTION_QUOTE_REJECTED:{result.status.value}:{result.reason}")
        return result.quote


class ResearchMarketPrice(StableModel):
    """A last-price observation for research; never an order quote."""

    symbol: str
    price: Decimal = Field(gt=Decimal("0"))
    observed_at: datetime
    provider: str


class ValuationMark(StableModel):
    """A portfolio valuation mark; never a manual-ticket quote."""

    symbol: str
    price: Decimal = Field(gt=Decimal("0"))
    as_of: datetime
    source: str


class ManualLimitPricePolicy:
    """Deterministic limit from a certified quote; an LLM cannot call this."""

    @staticmethod
    def calculate(
        quote: ExecutionQuote,
        side: Side,
        *,
        aggressiveness: Decimal = Decimal("0.0"),
        tick_size: Decimal = Decimal("0.01"),
    ) -> Decimal:
        if not Decimal("0") <= aggressiveness <= Decimal("1"):
            raise ValueError("aggressiveness must be between 0 and 1")
        if tick_size <= 0:
            raise ValueError("tick_size must be positive")
        if side is Side.BUY:
            value = quote.ask - (quote.ask - quote.bid) * aggressiveness
        else:
            value = quote.bid + (quote.ask - quote.bid) * aggressiveness
        units = (value / tick_size).quantize(Decimal("1"), rounding=ROUND_DOWN)
        return units * tick_size


class DiagnosticManualOrderDraft(StableModel):
    """A human-facing draft, explicitly not an execution request."""

    symbol: str
    side: Side
    quantity: Decimal = Field(gt=Decimal("0"))
    limit: Decimal = Field(gt=Decimal("0"))
    time_in_force_recommendation: str
    quote_timestamp: datetime
    quote_provider: str
    reason: str
    risk_checks: tuple[str, ...] = ()
    status: str = "NOT_EXECUTED"


# Compatibility alias for diagnostic callers.  Production-shaped drafts live
# exclusively in meridian.manual_authority.build_manual_order_draft.
ManualOrderDraft = DiagnosticManualOrderDraft


def create_manual_order_draft(
    quote: ExecutionQuote,
    *,
    side: Side,
    quantity: Decimal,
    readiness: Mapping[str, str],
    time_in_force_recommendation: str = "DAY",
    aggressiveness: Decimal = Decimal("0.0"),
    tick_size: Decimal = Decimal("0.01"),
    reason: str = "Deterministic draft for human review.",
    risk_checks: tuple[str, ...] = (),
) -> DiagnosticManualOrderDraft:
    """Reject the legacy helper; use the sealed authority instead."""
    _ = (quote, side, quantity, time_in_force_recommendation, aggressiveness, tick_size, reason, risk_checks)
    required = (
        "ACCOUNT_READY", "SECURITY_READY", "MARKET_READY", "RESEARCH_READY",
        "QUOTE_READY", "RISK_READY", "RECONCILIATION_READY",
    )
    missing = tuple(name for name in required if readiness.get(name) != "PASS")
    if missing:
        raise ValueError(f"MANUAL_ENTRY_BLOCKED:{','.join(missing)}")
    raise ValueError("MANUAL_ENTRY_BLOCKED:SEALED_MANUAL_READINESS_CERTIFICATE_REQUIRED")


class StaticReadOnlyExecutionQuoteProvider:
    """A deterministic test adapter; it has no trade methods or network calls."""

    def __init__(self, quotes: dict[str, ExecutionQuote], certificate: ExecutionQuoteCapabilityCertificate):
        self.provider_name = certificate.provider
        self.capabilities = certificate
        self._quotes = dict(quotes)

    def get_quote(self, symbol: str, *, as_of: datetime | None = None) -> ExecutionQuote:
        quote = self._quotes.get(symbol.upper())
        if quote is None:
            raise RuntimeError("PROVIDER_UNAVAILABLE")
        if as_of is not None and quote.timestamp > as_of:
            raise ValueError("quote timestamp is after as_of")
        return quote


ExecutionQuoteCertificate = ExecutionQuoteCapabilityCertificate
ReadOnlyExecutionQuoteProvider = ExecutionQuoteProvider
