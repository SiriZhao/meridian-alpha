"""SEC accession/acceptance metadata contracts for PIT certification.

Network retrieval is intentionally outside this pure join: only metadata with an
actual SEC acceptance timestamp can promote an existing Company Facts item.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import Field

from meridian.schemas import EvidenceItem, EvidencePointInTimeStatus, StableModel


class SECFilingMetadata(StableModel):
    cik: str = Field(pattern=r"^\d{10}$")
    accession_number: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    form: str = Field(min_length=1, max_length=32)
    primary_document: str = Field(min_length=1, max_length=256)
    filing_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    report_period: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    acceptance_datetime: datetime
    retrieved_at: datetime
    source_uri: str = Field(min_length=1, max_length=2000)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class SECAccessionCertifiedFactsAdapter:
    """Promote only exact accession-matched SEC facts with acceptance metadata."""

    provider_name = "sec-edgar-accession-certified"

    def certify(
        self, fact: EvidenceItem, metadata: SECFilingMetadata, decision_as_of: datetime
    ) -> EvidenceItem | None:
        if fact.provider not in {"sec-edgar", self.provider_name}:
            raise ValueError("SEC_PROVIDER_MISMATCH")
        if fact.document_id != metadata.accession_number:
            raise ValueError("SEC_ACCESSION_MISMATCH")
        if metadata.acceptance_datetime > decision_as_of:
            return None
        if metadata.acceptance_datetime > metadata.retrieved_at:
            raise ValueError("SEC_ACCEPTANCE_AFTER_RETRIEVAL")
        digest = hashlib.sha256(
            f"{fact.stable_id}|{metadata.accession_number}|{metadata.content_hash}".encode()
        ).hexdigest()
        return fact.model_copy(
            update={
                "provider": self.provider_name,
                "source": "SEC:EDGAR_ACCEPTANCE_METADATA",
                "observed_at": metadata.acceptance_datetime,
                "available_at": metadata.acceptance_datetime,
                "retrieved_at": metadata.retrieved_at,
                "uri": metadata.source_uri,
                "content_hash": digest,
                "point_in_time_status": EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
            }
        )