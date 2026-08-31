"""Stable, strongly typed domain contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[Decimal, Field(ge=Decimal("0"), max_digits=18, decimal_places=4)]
Weight = Annotated[Decimal, Field(ge=Decimal("0"), le=Decimal("1"), max_digits=8, decimal_places=6)]
Quantity = Annotated[Decimal, Field(ge=Decimal("0"), max_digits=18, decimal_places=6)]


class FreshnessState(StrEnum):
    VERIFIED = "VERIFIED"
    RECENT = "RECENT"
    UNKNOWN = "UNKNOWN"
    STALE = "STALE"


class EvidencePointInTimeStatus(StrEnum):
    VERIFIED_LIVE_AS_OF = "VERIFIED_LIVE_AS_OF"
    CERTIFIED_HISTORICAL_PIT = "CERTIFIED_HISTORICAL_PIT"
    VERIFIED = "VERIFIED"
    RECENT = "RECENT"
    SYNTHETIC = "SYNTHETIC"
    REPLAY_UNSAFE = "REPLAY_UNSAFE"
    HISTORICAL_REPLAY_UNSAFE = "HISTORICAL_REPLAY_UNSAFE"
    UNVERIFIED = "UNVERIFIED"
    UNKNOWN = "UNKNOWN"

class RunStatus(StrEnum):
    NO_CAPITAL = "NO_CAPITAL"
    ANALYSIS_ONLY = "ANALYSIS_ONLY"
    DRAFT = "DRAFT"
    READY_FOR_MANUAL_ENTRY = "READY_FOR_MANUAL_ENTRY"
    NO_ACTION = "NO_ACTION"
    BLOCKED_STALE_ACCOUNT = "BLOCKED_STALE_ACCOUNT"
    BLOCKED_STALE_MARKET = "BLOCKED_STALE_MARKET"
    FAILED = "FAILED"


class Side(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class AccountSyncState(StrEnum):
    SYNCED = "SYNCED"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"


class StableModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, ser_json_timedelta="iso8601")

    @model_validator(mode="after")
    def require_timezone_aware_datetimes(self):
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            if isinstance(value, datetime) and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{field_name} must be timezone-aware")
        return self

    def stable_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


class Holding(StableModel):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    quantity: Quantity
    market_value: Money
    cost_basis: Money | None = None
    average_cost: Money | None = None
    price: Money | None = None


class InvestmentTransaction(StableModel):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    side: Side
    quantity: Quantity
    price: Money | None = None
    amount: Money | None = None
    timestamp: datetime


class AccountSnapshot(StableModel):
    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

    snapshot_id: str = Field(min_length=1, max_length=128)
    account_alias: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    as_of: datetime
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    total_equity: Money
    cash: Money
    buying_power: Money | None = None
    holdings: tuple[Holding, ...] = ()
    recent_investment_transactions: tuple[InvestmentTransaction, ...] = ()
    sync_state: AccountSyncState
    freshness_state: FreshnessState

    @model_validator(mode="after")
    def unique_holdings_and_equity(self):
        if len({holding.ticker for holding in self.holdings}) != len(self.holdings):
            raise ValueError("holdings must not contain duplicate tickers")
        if self.total_equity < self.cash:
            raise ValueError("total_equity must be at least cash for long-only accounts")
        return self


class MarketSnapshot(StableModel):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    timestamp: datetime
    last: Money
    bid: Money | None = None
    ask: Money | None = None
    previous_close: Money
    volume: int = Field(ge=0)
    atr14: Money | None = None
    vwap: Money | None = None
    daily_return: Decimal = Field(ge=Decimal("-1"), le=Decimal("10"))
    gap_percent: Decimal | None = Field(default=None, ge=Decimal("-1"), le=Decimal("10"))
    freshness_state: FreshnessState

    @model_validator(mode="after")
    def quote_ordering(self):
        if self.bid is not None and self.ask is not None and self.bid > self.ask:
            raise ValueError("bid must not exceed ask")
        return self


class EvidenceItem(StableModel):
    """Timestamped evidence with explicit provenance."""

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

    evidence_id: str | None = Field(default=None, min_length=1, max_length=128)
    ticker: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    source: str = Field(min_length=1, max_length=256)
    provider: str | None = Field(default=None, min_length=1, max_length=128)
    published_at: datetime | None = None
    observed_at: datetime
    available_at: datetime | None = None
    retrieved_at: datetime | None = None
    title: str | None = Field(default=None, max_length=1000)
    uri: str | None = Field(default=None, max_length=2000)
    document_id: str | None = Field(default=None, max_length=256)
    content_hash: str | None = Field(default=None, max_length=128)
    evidence_type: str = Field(min_length=1, max_length=128)
    summary: str | None = Field(default=None, max_length=5000)
    structured_payload: dict[str, Any] | None = None
    point_in_time_status: EvidencePointInTimeStatus = EvidencePointInTimeStatus.UNVERIFIED

    @model_validator(mode="after")
    def normalize_availability(self):
        if self.available_at is None:
            object.__setattr__(self, "available_at", self.observed_at)
        for name, value in (
            ("published_at", self.published_at),
            ("observed_at", self.observed_at),
            ("available_at", self.available_at),
            ("retrieved_at", self.retrieved_at),
        ):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware")
        if self.published_at is not None and self.available_at is not None:
            if self.published_at > self.available_at:
                raise ValueError("published_at must not be after available_at")
        return self

    @property
    def stable_id(self) -> str:
        """Return a deterministic provenance identifier without secrets."""
        if self.evidence_id:
            return self.evidence_id
        provenance = "|".join(
            (
                self.provider or "UNVERIFIED",
                self.source,
                self.document_id or self.uri or self.title or "NO_DOCUMENT_ID",
                self.ticker or "NO_TICKER",
                self.available_at.isoformat() if self.available_at is not None else "NO_TIME",
                self.evidence_type,
            )
        )
        digest = hashlib.sha256(provenance.encode("utf-8")).hexdigest()
        return f"ev_{digest[:24]}"


class AgentSignal(StableModel):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    as_of: datetime
    direction: str = Field(pattern=r"^(BULLISH|BEARISH|NEUTRAL)$")
    conviction: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    fundamental_score: Decimal | None = Field(default=None, ge=-1, le=1)
    technical_score: Decimal | None = Field(default=None, ge=-1, le=1)
    sentiment_score: Decimal | None = Field(default=None, ge=-1, le=1)
    news_score: Decimal | None = Field(default=None, ge=-1, le=1)
    risk_score: Decimal | None = Field(default=None, ge=0, le=1)
    thesis: str = Field(min_length=1, max_length=10000)
    risks: tuple[str, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    source: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def evidence_is_point_in_time(self):
        for item in self.evidence:
            if item.observed_at > self.as_of:
                raise ValueError("evidence timestamp must not be after signal as_of")
            if item.available_at is not None and item.available_at > self.as_of:
                raise ValueError("evidence available_at must not be after signal as_of")
        return self


class TargetPosition(StableModel):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    target_weight: Weight
    conviction: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    rationale: str = Field(min_length=1, max_length=10000)


class TargetPortfolio(StableModel):
    as_of: datetime
    cash_weight: Weight
    positions: tuple[TargetPosition, ...]
    allocator_name: str = Field(min_length=1, max_length=128)
    allocator_version: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def valid_total_weight(self):
        if len({position.ticker for position in self.positions}) != len(self.positions):
            raise ValueError("positions must not contain duplicate tickers")
        invested = sum((position.target_weight for position in self.positions), Decimal("0"))
        if invested + self.cash_weight != Decimal("1"):
            raise ValueError("position weights plus cash_weight must equal 1")
        return self


class OrderDraft(StableModel):
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    side: Side
    quantity: Quantity
    preferred_limit: Money | None = None
    max_acceptable_buy_price: Money | None = None
    min_acceptable_sell_price: Money | None = None
    target_weight: Weight
    current_weight: Weight
    estimated_notional: Money
    time_in_force: str = Field(pattern=r"^(DAY|GTC)$")
    status: RunStatus
    reason: str = Field(min_length=1, max_length=10000)

    @model_validator(mode="after")
    def price_side_consistency(self):
        if self.side is Side.BUY and self.min_acceptable_sell_price is not None:
            raise ValueError("buy draft cannot have a sell floor")
        if self.side is Side.SELL and self.max_acceptable_buy_price is not None:
            raise ValueError("sell draft cannot have a buy cap")
        return self


class DailyDecision(StableModel):
    run_id: str = Field(min_length=1, max_length=128)
    as_of: datetime
    account_snapshot_status: FreshnessState
    account_sync_state: AccountSyncState = AccountSyncState.SYNCED
    market_data_status: FreshnessState
    regime: str = Field(min_length=1, max_length=128)
    target_portfolio: TargetPortfolio | None = None
    orders: tuple[OrderDraft, ...] = ()
    warnings: tuple[str, ...] = ()
    blocked_reasons: tuple[str, ...] = ()
    overall_status: RunStatus

    @model_validator(mode="after")
    def enforce_final_status_invariants(self):
        if self.overall_status is RunStatus.NO_CAPITAL and self.orders:
            raise ValueError("NO_CAPITAL decisions must not contain orders")
        if self.overall_status is RunStatus.NO_ACTION and self.orders:
            raise ValueError("NO_ACTION decisions must not contain orders")
        if self.overall_status is RunStatus.READY_FOR_MANUAL_ENTRY:
            if self.target_portfolio is None:
                raise ValueError("ready decision requires a target portfolio")
            if not self.orders:
                raise ValueError(
                    "ready decision requires at least one order; use NO_ACTION for no trades"
                )
            if self.account_snapshot_status not in {FreshnessState.VERIFIED, FreshnessState.RECENT}:
                raise ValueError("ready decision requires a fresh account snapshot")
            if self.account_sync_state is not AccountSyncState.SYNCED:
                raise ValueError("ready decision requires a synchronized account snapshot")
            if self.market_data_status not in {FreshnessState.VERIFIED, FreshnessState.RECENT}:
                raise ValueError("ready decision requires fresh market data")
            if any(
                order.status is not RunStatus.READY_FOR_MANUAL_ENTRY
                or order.preferred_limit is None
                for order in self.orders
            ):
                raise ValueError("ready decision contains a non-executable order draft")
        return self


class AlphaScore(StableModel):
    ticker: str
    score: Decimal = Field(ge=-1, le=1)
    confidence: Decimal = Field(ge=0, le=1)
    expected_direction: str = Field(pattern=r"^(BULLISH|BEARISH|NEUTRAL)$")
    risk_penalty: Decimal = Field(ge=0, le=1)
    evidence_quality: Decimal = Field(ge=0, le=1)
    model_source: str


def as_decimal(value: Any) -> Decimal:
    return Decimal(str(value))
