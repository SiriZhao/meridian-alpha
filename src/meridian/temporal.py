"""Canonical temporal context shared by research-facing operations."""

from __future__ import annotations

from datetime import date

from pydantic import AwareDatetime, Field, model_validator

from meridian.schemas import StableModel


class ResearchTemporalContext(StableModel):
    """Immutable point-in-time contract for one research run."""

    run_id: str = Field(min_length=1, max_length=128)
    trading_date: date
    as_of: AwareDatetime
    information_cutoff: AwareDatetime
    market_session: str = Field(min_length=1, max_length=64)
    timezone: str = Field(min_length=1, max_length=64)
    portfolio_snapshot_id: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def cutoff_is_consistent(self) -> ResearchTemporalContext:
        if self.information_cutoff > self.as_of:
            raise ValueError("INFORMATION_CUTOFF_AFTER_AS_OF")
        if self.as_of.date() < self.trading_date:
            raise ValueError("AS_OF_BEFORE_TRADING_DATE")
        return self
