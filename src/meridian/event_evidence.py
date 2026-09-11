"""Bounded qualitative event evidence; facts remain source-bound."""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from meridian.schemas import StableModel


class EventType(StrEnum):
    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    PRODUCT = "product"
    REGULATORY = "regulatory"
    LEGAL = "legal"
    MANAGEMENT = "management"
    MA = "M&A"
    CAPITAL_ALLOCATION = "capital_allocation"
    COMPETITION = "competition"
    INDUSTRY = "industry"
    MACRO_SENSITIVE = "macro_sensitive"
    OTHER = "other"


class QualitativeEventEvidence(StableModel):
    event_id: str | None = Field(default=None, max_length=128)
    ticker: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9.\-]{0,15}$")
    entity: str | None = Field(default=None, max_length=256)
    headline: str = Field(min_length=1, max_length=1000)
    source: str = Field(min_length=1, max_length=256)
    published_at: datetime
    retrieved_at: datetime
    analysis_cutoff: datetime
    event_type: EventType
    source_reference: str = Field(min_length=1, max_length=2000)
    quality: str = Field(min_length=1, max_length=64)
    provenance: str = Field(min_length=1, max_length=2048)

    @model_validator(mode="after")
    def bounded_source_fact(self) -> QualitativeEventEvidence:
        if not self.ticker and not self.entity:
            raise ValueError("EVENT_REQUIRES_TICKER_OR_ENTITY")
        for name, value in (("published_at", self.published_at), ("retrieved_at", self.retrieved_at), ("analysis_cutoff", self.analysis_cutoff)):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{name.upper()}_TIMEZONE_REQUIRED")
        if self.published_at > self.analysis_cutoff:
            raise ValueError("EVENT_AFTER_CUTOFF")
        if self.retrieved_at < self.published_at:
            raise ValueError("EVENT_RETRIEVED_BEFORE_PUBLICATION")
        if self.event_id is None:
            key = f"{self.ticker}|{self.entity}|{self.source}|{self.source_reference}|{self.published_at.isoformat()}"
            object.__setattr__(self, "event_id", "event_" + hashlib.sha256(key.encode()).hexdigest()[:24])
        return self
