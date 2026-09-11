import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest

from meridian.schemas import EvidenceItem, EvidencePointInTimeStatus
from meridian.sec_filing_metadata import SECAccessionCertifiedFactsAdapter, SECFilingMetadata

T = datetime(2026, 8, 30, tzinfo=UTC)
ACC = "0000320193-26-000001"


def metadata(accepted: datetime = T) -> SECFilingMetadata:
    return SECFilingMetadata(cik="0000320193", accession_number=ACC, form="10-Q", primary_document="q.htm",
        filing_date="2026-08-30", report_period="2026-06-30", acceptance_datetime=accepted, retrieved_at=T,
        source_uri="https://www.sec.gov/Archives/example", content_hash=hashlib.sha256(b"fixture").hexdigest())


def fact() -> EvidenceItem:
    return EvidenceItem(ticker="AAPL", provider="sec-edgar", source="SEC:CompanyFacts", document_id=ACC,
        observed_at=T, available_at=T, evidence_type="fundamental", point_in_time_status=EvidencePointInTimeStatus.UNVERIFIED)


def test_acceptance_before_cutoff_certifies_exact_accession() -> None:
    item = SECAccessionCertifiedFactsAdapter().certify(fact(), metadata(), T)
    assert item is not None and item.point_in_time_status is EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT
    assert item.available_at == T


def test_acceptance_after_cutoff_and_accession_mismatch_fail_closed() -> None:
    assert SECAccessionCertifiedFactsAdapter().certify(fact(), metadata(T + timedelta(seconds=1)), T) is None
    with pytest.raises(ValueError, match="ACCESSION_MISMATCH"):
        SECAccessionCertifiedFactsAdapter().certify(fact().model_copy(update={"document_id": "0000320193-26-000002"}), metadata(), T)

def test_naive_times_and_cik_accession_identity_mismatch_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SECFilingMetadata.model_validate({**metadata().model_dump(), "acceptance_datetime": datetime(2026, 8, 30)})
    with pytest.raises(ValueError, match="timezone-aware"):
        SECFilingMetadata.model_validate({**metadata().model_dump(), "retrieved_at": datetime(2026, 8, 30)})
    with pytest.raises(ValueError, match="CIK_ACCESSION_MISMATCH"):
        SECFilingMetadata.model_validate({**metadata().model_dump(), "accession_issuer_cik": "0000000001"})

def test_distinct_certified_provider_emits_only_accession_certified_evidence() -> None:
    from meridian.sec_filing_metadata import SECAccessionCertifiedFactsProvider

    class Facts:
        def get_evidence(self, ticker: str, as_of: datetime):
            return (fact(),)

    class Metadata:
        def get_metadata(self, cik: str, accession: str):
            assert cik == "0000320193" and accession == ACC
            return metadata()

    class Resolver:
        def resolve(self, ticker: str):
            assert ticker == "AAPL"
            return ("0000320193", "Apple Inc.", None, T)

    items = SECAccessionCertifiedFactsProvider(
        facts_provider=Facts(), metadata_provider=Metadata(), resolver=Resolver()
    ).get_evidence("AAPL", T)
    assert len(items) == 1
    assert items[0].provider == "sec-edgar-accession-certified"
    assert items[0].point_in_time_status is EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT

def test_historical_submissions_collection_resolves_exact_accession() -> None:
    from meridian.sec_filing_metadata import SECSubmissionMetadataProvider

    class Response:
        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload
        def read(self) -> bytes:
            return json.dumps(self.payload).encode()

    def opener(request, timeout: int):
        _ = timeout
        if request.full_url.endswith("CIK0000320193.json"):
            return Response({"cik": "320193", "filings": {"recent": {"accessionNumber": []}, "files": [{"name": "CIK0000320193-submissions-001.json"}]}})
        assert request.full_url.endswith("CIK0000320193-submissions-001.json")
        return Response({
            "accessionNumber": [ACC], "form": ["10-Q"], "filingDate": ["2026-08-30"],
            "reportDate": ["2026-06-30"], "primaryDocument": ["q.htm"],
            "acceptanceDateTime": ["2026-08-30T12:00:00.000Z"],
        })

    result = SECSubmissionMetadataProvider(opener=opener, clock=lambda: T).get_metadata("320193", ACC)
    assert result is not None
    assert result.accession_number == ACC
    assert result.acceptance_datetime == datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
    assert result.source_uri.endswith("CIK0000320193-submissions-001.json")
