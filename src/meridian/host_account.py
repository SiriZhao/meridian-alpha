"""Provider-independent, sanitized Host account boundary.

This module accepts facts supplied by a Host but contains no connector, broker,
or finance SDK.  It never stores account identifiers, credentials, or a raw
connector response.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import Field, model_validator

from meridian.schemas import (
    AccountSnapshot,
    AccountSyncState,
    FreshnessState,
    Holding,
    StableModel,
)
from meridian.security_master import DEFAULT_SECURITY_MASTER, SecurityMaster


class HostCoverageStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"
    CONFLICTING = "CONFLICTING"


class HostPosition(StableModel):
    canonical_asset_id: str | None = Field(default=None, min_length=1, max_length=128)
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    quantity: Decimal = Field(ge=Decimal("0"), max_digits=18, decimal_places=6)
    market_value: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=18, decimal_places=4)
    cost_basis: Decimal | None = Field(default=None, ge=Decimal("0"), max_digits=18, decimal_places=4)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")


class HostAccountSnapshotEnvelope(StableModel):
    """Minimal host-supplied facts; deliberately excludes account identifiers."""

    schema_version: str = Field(default="1", pattern=r"^1$")
    snapshot_id: str = Field(min_length=1, max_length=128)
    source_kind: str = Field(min_length=1, max_length=64)
    source_name: str = Field(min_length=1, max_length=128)
    as_of: datetime
    retrieved_at: datetime
    coverage_status: HostCoverageStatus
    base_currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    cash: Decimal = Field(ge=Decimal("0"), max_digits=18, decimal_places=4)
    total_equity: Decimal = Field(ge=Decimal("0"), max_digits=18, decimal_places=4)
    positions: tuple[HostPosition, ...] = ()
    pending_or_unknown_state: str | None = Field(default=None, max_length=1000)
    provenance_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_envelope(self):
        if self.retrieved_at < self.as_of:
            raise ValueError("retrieved_at must not precede as_of")
        if self.total_equity < self.cash:
            raise ValueError("total_equity must be at least cash")
        if len({position.ticker for position in self.positions}) != len(self.positions):
            raise ValueError("positions must not contain duplicate tickers")
        if self.provenance_digest is None:
            payload = self.model_dump(mode="json", exclude={"provenance_digest"})
            object.__setattr__(self, "provenance_digest", hashlib.sha256(
                str(sorted(payload.items())).encode()
            ).hexdigest())
        return self

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.stable_json().encode()).hexdigest()


class HostSnapshotRegistry:
    """In-memory duplicate-ID guard; only hashes are retained."""

    def __init__(self) -> None:
        self._hashes: dict[str, str] = {}

    def register(self, envelope: HostAccountSnapshotEnvelope) -> None:
        previous = self._hashes.get(envelope.snapshot_id)
        if previous is not None and previous != envelope.content_hash:
            raise ValueError("DUPLICATE_SNAPSHOT_ID_CONTENT_CONFLICT")
        self._hashes[envelope.snapshot_id] = envelope.content_hash


def normalize_host_snapshot(
    envelope: HostAccountSnapshotEnvelope,
    *,
    security_master: SecurityMaster = DEFAULT_SECURITY_MASTER,
    registry: HostSnapshotRegistry | None = None,
    max_age_seconds: int = 900,
    trusted_now: datetime | None = None,
    replay: bool = False,
    max_retrieved_skew_seconds: int = 30,
) -> AccountSnapshot:
    """Validate host facts with a system clock; only REPLAY can inject time."""

    if trusted_now is not None and not replay:
        raise ValueError("trusted_now injection is allowed only for REPLAY")
    reference = trusted_now if replay else datetime.now(UTC)
    if reference is None or reference.tzinfo is None or reference.utcoffset() is None:
        raise ValueError("trusted current time must be timezone-aware")
    if envelope.as_of > reference:
        raise ValueError("HOST_ACCOUNT_AS_OF_IN_FUTURE")
    if (envelope.retrieved_at - reference).total_seconds() > max_retrieved_skew_seconds:
        raise ValueError("HOST_ACCOUNT_RETRIEVED_AT_IN_FUTURE")
    if registry is not None:
        registry.register(envelope)
    if envelope.coverage_status is HostCoverageStatus.CONFLICTING:
        raise ValueError("HOST_ACCOUNT_CONFLICTING")
    if envelope.coverage_status is HostCoverageStatus.UNAVAILABLE:
        raise ValueError("HOST_ACCOUNT_UNAVAILABLE")
    holdings: list[Holding] = []
    for position in envelope.positions:
        record = security_master.resolve(position.ticker)
        if position.canonical_asset_id is not None and position.canonical_asset_id != record.canonical_asset_id:
            raise ValueError("SECURITY_IDENTITY_UNAVAILABLE:canonical_asset_id_mismatch")
        if position.currency != envelope.base_currency or record.currency != envelope.base_currency:
            raise ValueError("HOST_ACCOUNT_CURRENCY_MISMATCH")
        if position.market_value is None:
            raise ValueError("HOST_POSITION_MARKET_VALUE_REQUIRED")
        holdings.append(Holding(
            ticker=record.canonical_symbol, quantity=position.quantity,
            market_value=position.market_value, cost_basis=position.cost_basis,
        ))
    stale = (reference - envelope.as_of).total_seconds() > max_age_seconds
    if envelope.coverage_status is HostCoverageStatus.STALE or stale:
        freshness, sync = FreshnessState.STALE, AccountSyncState.PARTIAL
    elif envelope.coverage_status is HostCoverageStatus.PARTIAL:
        freshness, sync = FreshnessState.VERIFIED, AccountSyncState.PARTIAL
    else:
        freshness, sync = FreshnessState.VERIFIED, AccountSyncState.SYNCED
    return AccountSnapshot(
        snapshot_id=envelope.snapshot_id,
        account_alias="host-sanitized",
        provider="host-envelope",
        as_of=envelope.as_of,
        currency=envelope.base_currency,
        total_equity=envelope.total_equity,
        cash=envelope.cash,
        holdings=tuple(holdings),
        sync_state=sync,
        freshness_state=freshness,
    )