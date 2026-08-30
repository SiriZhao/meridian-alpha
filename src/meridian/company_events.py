"""Primary-source company-event contracts built from exact SEC filings."""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum

from pydantic import Field, model_validator

from meridian.schemas import EvidencePointInTimeStatus, StableModel
from meridian.sec_filing_metadata import SECFilingMetadata


class CompanyEventCategory(StrEnum):
    PERIODIC_REPORT = "PERIODIC_REPORT"
    MATERIAL_EVENT_FILING = "MATERIAL_EVENT_FILING"
    AMENDMENT_FILING = "AMENDMENT_FILING"


class CompanyEventObservation(StableModel):
    """An event is filing presence, never model-assigned sentiment."""

    event_id: str | None = Field(default=None, max_length=128)
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,15}$")
    category: CompanyEventCategory
    cik: str = Field(pattern=r"^\d{10}$")
    accession_number: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    form: str = Field(min_length=1, max_length=32)
    document: str = Field(min_length=1, max_length=256)
    accepted_at: datetime
    available_at: datetime
    source: str = Field(min_length=1, max_length=256)
    source_uri: str = Field(min_length=1, max_length=2000)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    pit_status: EvidencePointInTimeStatus

    @model_validator(mode="after")
    def validate_event(self) -> CompanyEventObservation:
        if self.available_at != self.accepted_at:
            raise ValueError("SEC_EVENT_AVAILABLE_AT_MUST_EQUAL_ACCEPTANCE")
        if self.pit_status is not EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT:
            raise ValueError("SEC_EVENT_REQUIRES_CERTIFIED_HISTORICAL_PIT")
        if self.event_id is None:
            object.__setattr__(
                self,
                "event_id",
                "sec_event_"
                + hashlib.sha256(
                    f"{self.ticker}|{self.accession_number}|{self.category}".encode()
                ).hexdigest()[:24],
            )
        return self

    def available_for(self, cutoff: datetime) -> bool:
        if cutoff.tzinfo is None or cutoff.utcoffset() is None:
            raise ValueError("event cutoff must be timezone-aware")
        return self.available_at <= cutoff


class ExtractedCompanyEvent(StableModel):
    event_id: str
    ticker: str
    category: str
    document_accession: str
    source_uri: str
    extraction: str


def category_for_form(form: str) -> CompanyEventCategory:
    normalized = form.upper().strip()
    if normalized.endswith("/A"):
        return CompanyEventCategory.AMENDMENT_FILING
    if normalized == "8-K":
        return CompanyEventCategory.MATERIAL_EVENT_FILING
    if normalized in {"10-Q", "10-K"}:
        return CompanyEventCategory.PERIODIC_REPORT
    raise ValueError("SEC_FORM_NOT_IN_COMPANY_EVENT_LANE")


def company_event_from_metadata(
    ticker: str, metadata: SECFilingMetadata
) -> CompanyEventObservation:
    """Seal a metadata observation without guessing document content."""
    return CompanyEventObservation(
        ticker=ticker.upper(),
        category=category_for_form(metadata.form),
        cik=metadata.cik,
        accession_number=metadata.accession_number,
        form=metadata.form,
        document=metadata.primary_document,
        accepted_at=metadata.acceptance_datetime,
        available_at=metadata.acceptance_datetime,
        source="SEC:EDGAR_SUBMISSIONS",
        source_uri=metadata.source_uri,
        source_hash=metadata.content_hash,
        pit_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
    )


def extract_company_event(observation: CompanyEventObservation) -> ExtractedCompanyEvent:
    """Emit only deterministic filing-presence facts with document lineage."""
    text = {
        CompanyEventCategory.PERIODIC_REPORT: "PERIODIC_FINANCIAL_FILING_AVAILABLE",
        CompanyEventCategory.MATERIAL_EVENT_FILING: "MATERIAL_EVENT_FILING_AVAILABLE",
        CompanyEventCategory.AMENDMENT_FILING: "AMENDMENT_FILING_AVAILABLE",
    }[observation.category]
    return ExtractedCompanyEvent(
        event_id=observation.event_id or "",
        ticker=observation.ticker,
        category=observation.category.value,
        document_accession=observation.accession_number,
        source_uri=observation.source_uri,
        extraction=text,
    )
