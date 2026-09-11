import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest

from meridian.fundamentals import (
    CanonicalMetric,
    CertifiedFundamentalFact,
    SECCompanyFactsNumericProvider,
    SECNumericObservation,
    build_snapshot,
    snapshot_to_evidence_items,
)
from meridian.research import DeepSeekGroundedResearchNormalizer, GroundedResearchRequest
from meridian.schemas import EvidencePointInTimeStatus
from meridian.sec_filing_metadata import SECFilingMetadata

T = datetime(2026, 8, 30, 12, tzinfo=UTC)
ACC = "0000320193-26-000001"


class Response:
    def __init__(self, payload: object):
        self.payload = json.dumps(payload).encode()

    def read(self):
        return self.payload


def companyfacts_payload(cik: str = "0000320193") -> dict[str, object]:
    return {
        "cik": cik,
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {
                        "USD": [
                            {"val": 90, "start": "2025-04-01", "end": "2025-06-30", "accn": ACC, "fy": 2025, "fp": "Q2", "form": "10-Q", "filed": "2026-07-01"},
                            {"val": 100, "start": "2026-04-01", "end": "2026-06-30", "accn": ACC, "fy": 2026, "fp": "Q2", "form": "10-Q", "filed": "2026-07-01"},
                        ]
                    }
                },
                "EarningsPerShareDiluted": {"units": {"USD/shares": [{"val": "1.25", "start": "2026-04-01", "end": "2026-06-30", "accn": ACC, "form": "10-Q", "filed": "2026-07-01"}]}}
            }
        },
    }


class AppleResolver:
    def resolve(self, ticker: str):
        assert ticker == "AAPL"
        return ("0000320193", "Apple Inc.", None, T)


def metadata(accepted: datetime = T, accession: str = ACC, cik: str = "0000320193") -> SECFilingMetadata:
    return SECFilingMetadata(
        cik=cik,
        accession_number=accession,
        form="10-Q",
        primary_document="q.htm",
        filing_date="2026-07-01",
        report_period="2026-06-30",
        acceptance_datetime=accepted,
        retrieved_at=T + timedelta(hours=1),
        source_uri="https://data.sec.gov/submissions/CIK0000320193.json",
        content_hash=hashlib.sha256(b"metadata").hexdigest(),
    )


def observation(metric: str, value: str, *, start: date | None, end: date, accession: str = ACC, cik: str = "0000320193") -> SECNumericObservation:
    return SECNumericObservation(
        observation_id=f"obs-{metric}-{value}-{end}", ticker="AAPL", cik=cik,
        taxonomy="us-gaap", concept=metric, value=Decimal(value), unit="USD",
        period_start=start, period_end=end, form="10-Q", filed_at=end,
        accession_number=accession, source_uri="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
        retrieved_at=T, source_hash="a" * 64,
    )


def test_numeric_provider_preserves_values_and_contexts():
    provider = SECCompanyFactsNumericProvider(
        opener=lambda *_, **__: Response(companyfacts_payload()), clock=lambda: T,
        resolver=AppleResolver(),
    )
    observations = provider.get_observations("AAPL")
    assert len(observations) == 3
    assert any(item.value == Decimal("100") and item.raw_concept == "RevenueFromContractWithCustomerExcludingAssessedTax" for item in observations)
    assert all(item.accession_number == ACC and item.retrieved_at == T for item in observations)


def test_numeric_provider_rejects_wrong_cik():
    provider = SECCompanyFactsNumericProvider(
        opener=lambda *_, **__: Response(companyfacts_payload("0000789019")), clock=lambda: T,
        resolver=AppleResolver(),
    )
    with pytest.raises(ValueError, match="SEC_CIK_MISMATCH"):
        provider.get_observations("AAPL")


def test_unknown_concept_stays_raw_but_is_excluded_from_certified_canonical_analysis():
    payload = companyfacts_payload()
    facts = cast(dict[str, object], payload["facts"])
    us_gaap = cast(dict[str, object], facts["us-gaap"])
    us_gaap["AmbiguousCustomConcept"] = {"units": {"USD": [{"val": 7, "start": "2026-04-01", "end": "2026-06-30", "accn": ACC, "form": "10-Q", "filed": "2026-07-01"}]}}
    provider = SECCompanyFactsNumericProvider(
        opener=lambda *_, **__: Response(payload), clock=lambda: T, resolver=AppleResolver(),
    )
    observations = provider.get_observations("AAPL")
    assert any(item.concept == "AmbiguousCustomConcept" for item in observations)
    class Metadata:
        def get_metadata(self, cik, accession):
            return metadata()
    facts = provider.certify_observations(observations, metadata_provider=Metadata(), decision_as_of=T)
    assert all(item.canonical_metric is not None for item in facts)
    assert any("UNKNOWN_CANONICAL_MAPPING" in item for item in provider.last_exclusions)


def test_accession_join_uses_acceptance_and_missing_metadata_is_unverified():
    provider = SECCompanyFactsNumericProvider(clock=lambda: T)
    obs = (observation("RevenueFromContractWithCustomerExcludingAssessedTax", "100", start=date(2026, 4, 1), end=date(2026, 6, 30)),)
    class Metadata:
        def get_metadata(self, cik, accession):
            return metadata()
    facts = provider.certify_observations(obs, metadata_provider=Metadata(), decision_as_of=T)
    assert facts[0].available_at == T
    assert facts[0].accepted_at == T
    assert facts[0].point_in_time_status is EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT
    missing = provider.certify_observations(obs, metadata_provider=type("M", (), {"get_metadata": lambda *_: None})(), decision_as_of=T)
    assert missing == ()
    assert any("UNVERIFIED_MISSING_ACCESSION_METADATA" in item for item in provider.last_exclusions)


def _fact(metric: CanonicalMetric, value: str, period_end: datetime, *, accepted: datetime = T, start: datetime | None = None, unit: str = "USD", accession: str = ACC) -> CertifiedFundamentalFact:
    return CertifiedFundamentalFact(
        fact_id=f"{metric}-{value}-{period_end.date()}", ticker="AAPL", cik="0000320193", accession_number=accession,
        form="10-Q", taxonomy="us-gaap", concept=metric.value, canonical_metric=metric, value=Decimal(value), unit=unit,
        period_start=start, period_end=period_end, accepted_at=accepted, available_at=accepted, retrieved_at=T,
        source_uri="https://sec.example", source_hash="b" * 64, provider="sec-edgar-companyfacts-numeric",
        point_in_time_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
    )


def test_cutoff_selects_known_fact_not_last_array_element_and_preserves_yoy_lineage():
    old = _fact(CanonicalMetric.REVENUE, "90", datetime(2025, 6, 30, tzinfo=UTC), start=datetime(2025, 4, 1, tzinfo=UTC), accepted=T - timedelta(days=2), accession="0000320193-26-000001")
    current = _fact(CanonicalMetric.REVENUE, "100", datetime(2026, 6, 30, tzinfo=UTC), start=datetime(2026, 4, 1, tzinfo=UTC), accession="0000320193-26-000001")
    future = _fact(CanonicalMetric.REVENUE, "999", datetime(2026, 7, 31, tzinfo=UTC), start=datetime(2026, 7, 1, tzinfo=UTC), accepted=T + timedelta(days=1), accession="0000320193-26-000002")
    snapshot = build_snapshot("AAPL", (future, current, old), T)
    assert snapshot.facts[0].value == Decimal("100")
    assert snapshot.comparable_series[0].prior_value == Decimal("90")
    assert snapshot.derived[0].input_fact_ids == (snapshot.comparable_series[0].current_fact_id, snapshot.comparable_series[0].prior_fact_id)


def test_quarter_ytd_and_units_do_not_derive_margin():
    revenue = _fact(CanonicalMetric.REVENUE, "100", datetime(2026, 6, 30, tzinfo=UTC), start=datetime(2026, 4, 1, tzinfo=UTC))
    ytd_income = _fact(CanonicalMetric.OPERATING_INCOME, "20", datetime(2026, 6, 30, tzinfo=UTC), start=datetime(2026, 1, 1, tzinfo=UTC))
    wrong_unit = _fact(CanonicalMetric.GROSS_PROFIT, "50", datetime(2026, 6, 30, tzinfo=UTC), start=datetime(2026, 4, 1, tzinfo=UTC), unit="EUR")
    snapshot = build_snapshot("AAPL", (revenue, ytd_income, wrong_unit), T)
    assert all(item.metric != "OPERATING_MARGIN" for item in snapshot.derived)
    assert all(item.metric != "GROSS_MARGIN" for item in snapshot.derived)


def test_enriched_prompt_contains_structured_certified_values_only():
    from meridian.evidence import ProviderCapabilities
    from meridian.research import (
        CertifiedEvidenceView,
        GraphResearchSummary,
        PointInTimeStatus,
        ResearchContextPacket,
        ResearchStatus,
    )
    snapshot = build_snapshot("AAPL", (_fact(CanonicalMetric.REVENUE, "100", datetime(2026, 6, 30, tzinfo=UTC), start=datetime(2026, 4, 1, tzinfo=UTC)),), T)
    item = snapshot_to_evidence_items(snapshot)[0]
    context = ResearchContextPacket(context_id="numeric", ticker="AAPL", as_of=T, created_at=T, items=(item,))
    assert item.provider is not None
    view = CertifiedEvidenceView.from_context(context, provider_registry={item.provider: ProviderCapabilities(provider_name=item.provider, supports_historical=True, supports_point_in_time=True, research_grade=True)}, clock=lambda: T)
    request = GroundedResearchRequest(graph_summary=GraphResearchSummary(ticker="AAPL", as_of=T, status=ResearchStatus.GRAPH_SUMMARY_ONLY, provider="fixture", model="none", framework_version="1", started_at=T, completed_at=T, point_in_time_status=PointInTimeStatus.LIVE_RESEARCH_OK), evidence_packet=view.packet, as_of=T)
    prompt = DeepSeekGroundedResearchNormalizer._prompt(request)
    assert "100" in prompt and "structured_payload" in prompt and "yahoo" not in prompt.lower()
