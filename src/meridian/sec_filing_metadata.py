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

from meridian.evidence import ProviderCapabilities
from meridian.evidence_foundation import SECCompanyFactsProvider
from meridian.fundamentals import SECTickerResolver
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
        source_uri = f"https://data.sec.gov/submissions/CIK{normalized_cik}.json"
        data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        if not isinstance(data, Mapping) or str(data.get("cik", "")).zfill(10) != normalized_cik:
            raise ValueError("SEC_CIK_MISMATCH")
        filings = data.get("filings", {})
        recent = filings.get("recent", {}) if isinstance(filings, Mapping) else {}
        if not isinstance(recent, Mapping):
            raise ValueError("SEC_SUBMISSIONS_MALFORMED") from None
        accessions = recent.get("accessionNumber", [])
        if not isinstance(accessions, list):
            raise ValueError("SEC_SUBMISSIONS_MALFORMED") from None
        try:
            index = accessions.index(accession_number)
        except ValueError:
            files = filings.get("files", []) if isinstance(filings, Mapping) else []
            if not isinstance(files, list):
                raise ValueError("SEC_SUBMISSIONS_MALFORMED") from None
            found = False
            for collection in files[:20]:
                if not isinstance(collection, Mapping) or not isinstance(collection.get("name"), str):
                    continue
                name = str(collection["name"])
                if "/" in name or "\\" in name:
                    continue
                historical_uri = f"https://data.sec.gov/submissions/{name}"
                historical_response = self.opener(Request(historical_uri, headers={"User-Agent": self.user_agent}), timeout=10)
                historical_raw = historical_response.read()
                historical = json.loads(historical_raw.decode("utf-8") if isinstance(historical_raw, bytes) else historical_raw)
                if not isinstance(historical, Mapping):
                    raise ValueError("SEC_SUBMISSIONS_MALFORMED") from None
                historical_accessions = historical.get("accessionNumber", [])
                if not isinstance(historical_accessions, list) or accession_number not in historical_accessions:
                    continue
                recent = historical
                accessions = historical_accessions
                index = accessions.index(accession_number)
                raw = historical_raw
                source_uri = historical_uri
                found = True
                break
            if not found:
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
        acceptance = datetime.fromisoformat(accepted.replace("Z", "+00:00"))
        if acceptance.tzinfo is None or acceptance.utcoffset() is None:
            raise ValueError("SEC_ACCEPTANCE_TIMEZONE_REQUIRED")
        acceptance = acceptance.astimezone(UTC)
        retrieved = self.clock()
        return SECFilingMetadata(
            cik=normalized_cik, accession_number=accession_number, form=form,
            primary_document=primary_document, filing_date=filing_date,
            report_period=value("reportDate"), acceptance_datetime=acceptance,
            retrieved_at=retrieved, source_uri=source_uri,
            content_hash=hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode()).hexdigest(),
        )
class SECAccessionCertifiedFactsProvider:
    """Distinct research-grade provider path requiring SEC acceptance metadata."""

    provider_name = "sec-edgar-accession-certified"
    network_capable = True

    def __init__(
        self,
        *,
        facts_provider: Any | None = None,
        metadata_provider: Any | None = None,
        resolver: Any | None = None,
    ) -> None:
        self.facts_provider = facts_provider or SECCompanyFactsProvider()
        self.metadata_provider = metadata_provider or SECSubmissionMetadataProvider()
        self.capabilities = ProviderCapabilities(
            provider_name=self.provider_name,
            supports_historical=True,
            supports_point_in_time=True,
            requires_api_key=False,
            execution_grade=False,
            research_grade=True,
        )
        self.resolver = resolver or SECTickerResolver()

    def get_evidence(self, ticker: str, as_of: datetime) -> tuple[EvidenceItem, ...]:
        try:
            cik, _, _, _ = self.resolver.resolve(ticker.upper())
        except (OSError, ValueError):
            return ()
        facts = self.facts_provider.get_evidence(ticker.upper(), as_of)
        adapter = SECAccessionCertifiedFactsAdapter()
        certified: list[EvidenceItem] = []
        for fact in facts:
            if not fact.document_id:
                continue
            metadata = self.metadata_provider.get_metadata(cik, fact.document_id)
            if metadata is None:
                continue
            item = adapter.certify(fact, metadata, as_of)
            if item is not None:
                certified.append(item)
        return tuple(certified)



