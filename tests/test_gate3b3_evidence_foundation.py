from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from meridian.evidence_foundation import (
    EvidencePITCertification,
    FundamentalObservation,
    MacroObservation,
    NewsObservation,
    ReplayFundamentalEvidenceProvider,
    ReplayMacroEvidenceProvider,
    ReplayNewsEvidenceProvider,
)

T = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def test_fundamental_authority_is_publication_availability_not_period_end() -> None:
    observation = FundamentalObservation(
        canonical_asset_id="US-EQ-AAPL", ticker="AAPL", filing_id="accn-1", filing_type="10-Q",
        period_end=date(2026, 6, 30), value=Decimal("100"), units="USD",
        publication_at=datetime(2026, 8, 15, tzinfo=UTC), available_at=datetime(2026, 8, 15, tzinfo=UTC),
        retrieved_at=T, source="SEC:CompanyFacts", point_in_time_status=EvidencePITCertification.UNVERIFIED,
    )
    assert observation.to_evidence_item().available_at == datetime(2026, 8, 15, tzinfo=UTC)


def test_fundamental_future_availability_rejected_for_cutoff_by_packet_builder_contract() -> None:
    observation = FundamentalObservation(
        canonical_asset_id="US-EQ-AAPL", ticker="AAPL", filing_id="accn-1", filing_type="10-Q",
        period_end=date(2026, 6, 30), value=Decimal("100"), units="USD",
        publication_at=T, available_at=T, retrieved_at=T, source="SEC:CompanyFacts",
    )
    assert observation.to_evidence_item().available_at == T


def test_news_requires_explicit_publication_and_deduplicates_by_document_identity() -> None:
    first = NewsObservation(
        ticker="AAPL", headline="Apple update", source="wire", document_id="doc-1",
        published_at=datetime(2026, 8, 28, tzinfo=UTC), available_at=datetime(2026, 8, 28, tzinfo=UTC),
        retrieved_at=T, entity_links=("AAPL",), point_in_time_status=EvidencePITCertification.UNVERIFIED,
    )
    second = NewsObservation(
        ticker="AAPL", headline="Apple update syndicated", source="wire", document_id="doc-1",
        published_at=datetime(2026, 8, 28, tzinfo=UTC), available_at=datetime(2026, 8, 28, tzinfo=UTC),
        retrieved_at=T, entity_links=("AAPL",), point_in_time_status=EvidencePITCertification.UNVERIFIED,
    )
    assert first.content_hash != second.content_hash
    assert first.document_id == second.document_id


def test_macro_without_release_vintage_is_unverified() -> None:
    macro = MacroObservation(
        series_id="CPI", observation_period=date(2026, 7, 31), value=Decimal("3.0"), units="percent",
        retrieved_at=T, source="FRED", point_in_time_status=EvidencePITCertification.UNVERIFIED,
    )
    assert macro.point_in_time_status.value == "UNVERIFIED"
    assert macro.to_evidence_item().available_at == T


@pytest.mark.parametrize("provider", [ReplayFundamentalEvidenceProvider(), ReplayNewsEvidenceProvider(), ReplayMacroEvidenceProvider()])
def test_replay_evidence_is_synthetic_and_non_executable(provider: ReplayFundamentalEvidenceProvider | ReplayNewsEvidenceProvider | ReplayMacroEvidenceProvider) -> None:
    result = provider.get_evidence("AAPL", T)
    assert result[0].point_in_time_status.value == "SYNTHETIC"
    assert provider.network_capable is False

