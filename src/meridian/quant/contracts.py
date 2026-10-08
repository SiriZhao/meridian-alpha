"""Disabled/PIT future inputs, never an internally invented alpha forecast."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from meridian.schemas import StableModel


class ExpectedReturnEstimate(StableModel):
    version: Literal["quant-expected-return.v1"] = "quant-expected-return.v1"
    horizon_sessions: int = Field(ge=1)
    prediction_target: Literal["PORTFOLIO_RETURN_IMPROVEMENT_OVER_HOLD"]
    feature_cutoff: AwareDatetime
    training_start: AwareDatetime
    training_end: AwareDatetime
    training_labels_available_at: AwareDatetime | None = None
    prediction_at: AwareDatetime
    expected_improvement: Decimal | None = None
    lower_bound: Decimal | None = None
    upper_bound: Decimal | None = None
    calibration_status: Literal["UNCALIBRATED", "INDEPENDENTLY_REVIEWED"] = "UNCALIBRATED"
    review_reference: str | None = None
    model_hash: str = Field(min_length=64, max_length=64)
    data_hash: str = Field(min_length=64, max_length=64)
    feature_hash: str = Field(min_length=64, max_length=64)
    decision_hash: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def coherent(self) -> "ExpectedReturnEstimate":
        if not self.training_start <= self.training_end < self.feature_cutoff <= self.prediction_at:
            raise ValueError("EXPECTED_RETURN_TRAINING_OR_PREDICTION_TIMING_INVALID")
        if self.calibration_status == "INDEPENDENTLY_REVIEWED":
            if self.training_labels_available_at is None or not self.training_end <= self.training_labels_available_at < self.feature_cutoff:
                raise ValueError("EXPECTED_RETURN_TRAINING_LABEL_AVAILABILITY_REQUIRED")
            if (not self.review_reference or self.expected_improvement is None or self.lower_bound is None
                    or self.upper_bound is None or not self.lower_bound <= self.expected_improvement <= self.upper_bound):
                raise ValueError("EXPECTED_RETURN_CALIBRATION_EVIDENCE_REQUIRED")
        elif any(v is not None for v in (self.expected_improvement, self.lower_bound, self.upper_bound)):
            raise ValueError("UNCALIBRATED_EXPECTED_RETURN_MUST_BE_UNKNOWN")
        return self

    def conservative_improvement(self, *, decision_at: AwareDatetime, feature_hash: str,
                                 decision_hash: str, horizon_sessions: int) -> Decimal | None:
        if (self.prediction_at > decision_at or self.feature_cutoff != decision_at
                or self.feature_hash != feature_hash or self.decision_hash != decision_hash
                or self.horizon_sessions != horizon_sessions):
            raise ValueError("EXPECTED_RETURN_CUTOFF_HORIZON_OR_FEATURE_MISMATCH")
        return self.lower_bound if self.calibration_status == "INDEPENDENTLY_REVIEWED" else None


class FundamentalObservation(StableModel):
    version: str = "quant-fundamental-observation.v1"
    symbol: str
    metric: Literal["QUALITY", "PROFITABILITY", "LEVERAGE", "VALUATION", "ANALYST_ESTIMATE"]
    fiscal_start: date
    fiscal_end: date
    release_at: AwareDatetime
    available_at: AwareDatetime
    ingested_at: AwareDatetime
    revision_id: str = Field(min_length=1)
    supersedes_revision: str | None = None
    value: Decimal | None
    unit: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_hash: str = Field(min_length=64, max_length=64)
    missing_reason: str | None = None
    certification: Literal["UNVERIFIED", "REVIEWED_PIT"] = "UNVERIFIED"

    @model_validator(mode="after")
    def coherent(self) -> "FundamentalObservation":
        if self.fiscal_start > self.fiscal_end or self.release_at.date() < self.fiscal_end:
            raise ValueError("FUNDAMENTAL_FISCAL_RELEASE_TIMING_INVALID")
        if not self.release_at <= self.available_at <= self.ingested_at:
            raise ValueError("FUNDAMENTAL_AVAILABILITY_TIMING_INVALID")
        if self.value is None and not self.missing_reason:
            raise ValueError("FUNDAMENTAL_MISSING_REASON_REQUIRED")
        if self.supersedes_revision == self.revision_id:
            raise ValueError("FUNDAMENTAL_SELF_REVISION")
        return self


class FundamentalSelection(StableModel):
    status: Literal["FUNDAMENTALS_DISABLED", "INSUFFICIENT_EVIDENCE", "AVAILABLE"]
    observations: tuple[FundamentalObservation, ...] = ()
    blocker: str | None = None


class DisabledFundamentalAdapter:
    """No data provider or score coupling; opt-in selection is a contract test seam."""

    def select(self, observations: tuple[FundamentalObservation, ...], *, cutoff: AwareDatetime,
               enabled: bool = False) -> FundamentalSelection:
        if not enabled:
            return FundamentalSelection(status="FUNDAMENTALS_DISABLED", blocker="REVIEWED_PIT_FUNDAMENTALS_UNAVAILABLE")
        identities = [(o.symbol, o.metric, o.fiscal_start, o.fiscal_end, o.revision_id) for o in observations]
        if len(set(identities)) != len(identities):
            raise ValueError("FUNDAMENTAL_DUPLICATE_REVISION")
        selected: dict[tuple[str, str, date, date], FundamentalObservation] = {}
        for row in sorted(observations, key=lambda o: (o.available_at, o.revision_id)):
            if row.available_at > cutoff or row.ingested_at > cutoff or row.certification != "REVIEWED_PIT":
                continue
            key = (row.symbol, row.metric, row.fiscal_start, row.fiscal_end)
            previous = selected.get(key)
            if previous is not None and (row.available_at == previous.available_at or row.supersedes_revision != previous.revision_id
                                         or row.unit != previous.unit):
                raise ValueError("FUNDAMENTAL_REVISION_LINEAGE_CONFLICT")
            if previous is None and row.supersedes_revision is not None:
                raise ValueError("FUNDAMENTAL_REVISION_PARENT_UNAVAILABLE")
            selected[key] = row
        if not selected:
            return FundamentalSelection(status="INSUFFICIENT_EVIDENCE", blocker="NO_QUALIFIED_PIT_FUNDAMENTALS")
        return FundamentalSelection(status="AVAILABLE", observations=tuple(selected[k] for k in sorted(selected)))
