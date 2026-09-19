"""Evidence-grounded, non-authorizing price proposal contracts."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from meridian.schemas import StableModel


class PriceProposalStatus(StrEnum):
    VALID = "VALID"
    PRICE_PROPOSAL_STALE = "PRICE_PROPOSAL_STALE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class PriceProposalPolicy(StableModel):
    maximum_age_seconds: int = Field(gt=0, le=86400)


class GroundedPriceProposal(StableModel):
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,14}$")
    reference_price: Decimal = Field(gt=0)
    entry_zone: tuple[Decimal, Decimal]
    stop: Decimal | None = Field(default=None, gt=0)
    target: Decimal | None = Field(default=None, gt=0)
    market_timestamp: AwareDatetime
    evidence_ids: tuple[str, ...] = Field(min_length=1)
    generated_at: AwareDatetime
    valid_until: AwareDatetime
    authority: str = "ADVISORY_ONLY"

    @model_validator(mode="after")
    def validate_grounding(self) -> GroundedPriceProposal:
        low, high = self.entry_zone
        if low <= 0 or high < low:
            raise ValueError("PRICE_PROPOSAL_ENTRY_ZONE_INVALID")
        if self.market_timestamp > self.generated_at:
            raise ValueError("PRICE_PROPOSAL_FUTURE_MARKET_REFERENCE")
        if self.valid_until <= self.generated_at:
            raise ValueError("PRICE_PROPOSAL_VALIDITY_INVALID")
        return self

    def status_at(self, now: datetime, policy: PriceProposalPolicy) -> PriceProposalStatus:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("PRICE_PROPOSAL_NOW_TIMEZONE_REQUIRED")
        deterministic_expiry = min(
            self.valid_until,
            self.market_timestamp + timedelta(seconds=policy.maximum_age_seconds),
        )
        return (
            PriceProposalStatus.VALID
            if now <= deterministic_expiry
            else PriceProposalStatus.PRICE_PROPOSAL_STALE
        )
