"""SEC accession/acceptance metadata contracts for PIT certification.

Network retrieval is intentionally outside this pure join: only metadata with an
actual SEC acceptance timestamp can promote an existing Company Facts item.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.request import Request, urlopen

from pydantic import Field, model_validator

from meridian.schemas import EvidenceItem, EvidencePointInTimeStatus, StableModel


class SECFilingMetadata(StableModel):
    cik: str = Field(pattern=r"^\d{10}$")
    accession_issuer_cik: str | None = Field(default=None, pattern=r"^\d{10}$")
    accession_number: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    form: str = Field(min_length=1, max_length=32)
    primary_document: str = Field(min_length=1, max_length=256)
    filing_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    report_period: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    acceptance_datetime: datetime
    retrieved_at: datetime
    source_uri: str = Field(min_length=1, max_length=2000)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_identity(self):
        if self.accession_issuer_cik is not None and self.accession_issuer_cik != self.cik:
            raise ValueError("CIK_ACCESSION_MISMATCH")
        return self


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
class SECSubmissionMetadataProvider:
    """Bounded SEC submissions adapter; never fabricates acceptance time."""

    provider_name = "sec-edgar-submissions"
    network_capable = True

    def __init__(
        self,
        *,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], datetime] | None = None,
        user_agent: str = "MeridianAlpha research contact unavailable",
    ) -> None:
        self.opener = opener
        self.clock = clock or (lambda: datetime.now(UTC))
        self.user_agent = user_agent

    def get_metadata(self, cik: str, accession_number: str) -> SECFilingMetadata | None:
        normalized_cik = cik.zfill(10)
        request = Request(
            f"https://data.sec.gov/submissions/CIK{normalized_cik}.json",
            headers={"User-Agent": self.user_agent},
        )
        response = self.opener(request, timeout=10)
        raw = response.read()
        data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        if not isinstance(data, Mapping) or str(data.get("cik", "")).zfill(10) != normalized_cik:
            raise ValueError("SEC_CIK_MISMATCH")
        filings = data.get("filings", {})
        recent = filings.get("recent", {}) if isinstance(filings, Mapping) else {}
        if not isinstance(recent, Mapping):
            raise ValueError("SEC_SUBMISSIONS_MALFORMED")
        accessions = recent.get("accessionNumber", [])
        if not isinstance(accessions, list):
            raise ValueError("SEC_SUBMISSIONS_MALFORMED")
        try:
            index = accessions.index(accession_number)
        except ValueError:
            return None
        def value(name: str) -> str | None:
            values = recent.get(name, [])
            return str(values[index]) if isinstance(values, list) and index < len(values) and values[index] else None
        accepted = value("acceptanceDateTime")
        form = value("form")
        filing_date = value("filingDate")
        primary_document = value("primaryDocument")
        if accepted is None or form is None or filing_date is None or primary_document is None:
            return None
        acceptance = datetime.fromisoformat(accepted.replace("Z", "+00:00")).astimezone(UTC)
        retrieved = self.clock()
        source_uri = f"https://data.sec.gov/submissions/CIK{normalized_cik}.json"
        return SECFilingMetadata(
            cik=normalized_cik, accession_number=accession_number, form=form,
            primary_document=primary_document, filing_date=filing_date,
            report_period=value("reportDate"), acceptance_datetime=acceptance,
            retrieved_at=retrieved, source_uri=source_uri,
            content_hash=hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode()).hexdigest(),
        )