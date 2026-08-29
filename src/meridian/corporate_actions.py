"""Corporate-action events, first-seen ledger, and historical availability rules."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator

from meridian.schemas import StableModel


class CorporateActionType(StrEnum):
    SPLIT = "SPLIT"
    CASH_DIVIDEND = "CASH_DIVIDEND"
    STOCK_DIVIDEND = "STOCK_DIVIDEND"
    SYMBOL_CHANGE = "SYMBOL_CHANGE"
    DELISTING = "DELISTING"
    MERGER = "MERGER"
    ACQUISITION = "ACQUISITION"


class CorporateActionPITStatus(StrEnum):
    CERTIFIED_HISTORICAL_PIT = "CERTIFIED_HISTORICAL_PIT"
    NOT_CERTIFIED_FOR_HISTORICAL_INFORMATION_EVENT = "NOT_CERTIFIED_FOR_HISTORICAL_INFORMATION_EVENT"
    LIVE_FORWARD_FIRST_SEEN = "LIVE_FORWARD_FIRST_SEEN"
    SYNTHETIC = "SYNTHETIC"
    REPLAY_UNSAFE = "REPLAY_UNSAFE"
    UNKNOWN = "UNKNOWN"


class CorporateActionEvent(StableModel):
    event_id: str | None = Field(default=None, max_length=128)
    canonical_asset_id: str = Field(min_length=1, max_length=128)
    canonical_symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,15}$")
    action_type: CorporateActionType
    announcement_at: datetime | None = None
    event_date: date
    effective_date: date | None = None
    record_date: date | None = None
    payable_date: date | None = None
    value: Decimal | None = Field(default=None, ge=Decimal("0"))
    ratio: Decimal | None = Field(default=None, gt=Decimal("0"))
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    provider: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=256)
    document_id: str | None = Field(default=None, max_length=256)
    first_seen_at: datetime
    payload_hash: str | None = None
    pit_status: CorporateActionPITStatus = CorporateActionPITStatus.UNKNOWN

    @model_validator(mode="after")
    def validate_event(self) -> CorporateActionEvent:
        for name, value in (("announcement_at", self.announcement_at), ("first_seen_at", self.first_seen_at)):
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{name} must be timezone-aware")
        if self.effective_date is not None and self.effective_date < self.event_date:
            raise ValueError("effective_date must not precede event_date")
        if self.announcement_at is None and self.pit_status is CorporateActionPITStatus.CERTIFIED_HISTORICAL_PIT:
            raise ValueError("historical PIT certification requires announcement_at")
        if self.event_id is None:
            raw = "|".join((self.canonical_asset_id, self.action_type.value, self.event_date.isoformat(), self.provider, self.document_id or self.source))
            object.__setattr__(self, "event_id", f"ca_{hashlib.sha256(raw.encode()).hexdigest()[:24]}")
        if self.payload_hash is None:
            object.__setattr__(self, "payload_hash", hashlib.sha256(self.stable_json().encode()).hexdigest())
        return self

    def available_for(self, as_of: datetime) -> bool:
        """Only an independently known-at announcement can certify historical availability."""
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        return (
            self.pit_status is CorporateActionPITStatus.CERTIFIED_HISTORICAL_PIT
            and self.announcement_at is not None
            and self.announcement_at <= as_of
        )


class FirstSeenLedgerRow(StableModel):
    event_id: str
    canonical_asset_id: str
    provider: str
    first_seen_at: datetime
    payload_hash: str


class FirstSeenLedger:
    """Append-only first-observed metadata ledger; it never backdates rows."""

    def __init__(self, path: Path | None = None, *, clock: Callable[[], datetime] | None = None):
        self.path = path
        self.clock = clock or (lambda: datetime.now(UTC))
        self._rows: dict[str, FirstSeenLedgerRow] = {}
        if path is not None and path.is_file():
            self._load(path)

    @property
    def rows(self) -> tuple[FirstSeenLedgerRow, ...]:
        return tuple(self._rows[key] for key in sorted(self._rows))

    def record(self, event: CorporateActionEvent) -> FirstSeenLedgerRow:
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("ledger clock must be timezone-aware")
        if event.first_seen_at > now:
            raise ValueError("first_seen_at cannot be in the future")
        existing = self._rows.get(event.event_id or "")
        if existing is not None:
            return existing
        row = FirstSeenLedgerRow(
            event_id=event.event_id or "",
            canonical_asset_id=event.canonical_asset_id,
            provider=event.provider,
            first_seen_at=now,
            payload_hash=event.payload_hash or hashlib.sha256(event.stable_json().encode()).hexdigest(),
        )
        self._rows[row.event_id] = row
        self._persist()
        return row

    def _persist(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps([row.model_dump(mode="json") for row in self.rows], sort_keys=True), encoding="utf-8")

    def _load(self, path: Path) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            raise ValueError("first-seen ledger must be a list")
        for item in payload:
            row = FirstSeenLedgerRow.model_validate(item)
            self._rows[row.event_id] = row


class CorporateActionProviderComparison(StableModel):
    event_key: str
    providers: tuple[str, ...]
    differing_fields: tuple[str, ...] = ()
    status: str = "MATCH"


def compare_corporate_actions(events: Sequence[CorporateActionEvent]) -> CorporateActionProviderComparison:
    if not events:
        raise ValueError("at least one corporate action is required")
    baseline = events[0]
    fields = tuple(
        field for field in ("action_type", "event_date", "effective_date", "value", "ratio", "currency")
        if any(getattr(item, field) != getattr(baseline, field) for item in events[1:])
    )
    return CorporateActionProviderComparison(
        event_key=baseline.event_id or "UNKNOWN",
        providers=tuple(item.provider for item in events),
        differing_fields=fields,
        status="MARKET_DATA_CONFLICT" if fields else "MATCH",
    )




CorporateAction = CorporateActionEvent

