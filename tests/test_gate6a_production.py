"""Gate 6A production-path convergence tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from meridian.alpha_fusion import fuse_production_decision
from meridian.authorization import EvidenceAuthorizationService
from meridian.evidence import ProviderCapabilities
from meridian.fundamentals import (
    CanonicalMetric,
    CertifiedFundamentalFact,
    build_snapshot,
    snapshot_to_evidence_items,
)
from meridian.research import GroundedResearchSignal, ResearchEvidencePacket
from meridian.schemas import EvidenceItem, EvidencePointInTimeStatus

T = datetime(2026, 8, 30, tzinfo=UTC)


def _fact(metric: CanonicalMetric, value: str, accepted: datetime, period_end: datetime) -> CertifiedFundamentalFact:
    return CertifiedFundamentalFact(
        fact_id=f"{metric.value}-{accepted.isoformat()}-{period_end.date()}", ticker="AAPL", cik="0000320193",
        accession_number="0000320193-26-000001", form="10-Q", taxonomy="us-gaap",
        concept=metric.value, canonical_metric=metric, value=Decimal(value), unit="USD",
        period_start=period_end - timedelta(days=90), period_end=period_end,
        accepted_at=accepted, available_at=accepted, retrieved_at=T + timedelta(days=2),
        source_uri="https://data.sec.gov", source_hash="a" * 64,
        provider="sec-edgar-accession-certified", point_in_time_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
    )


def test_production_fusion_is_directional_and_not_quant_only() -> None:
    item = EvidenceItem(
        evidence_id="e1", ticker="AAPL", provider="sec-edgar-accession-certified", source="SEC",
        observed_at=T, available_at=T, retrieved_at=T, evidence_type="certified_fundamental",
        point_in_time_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT,
    )
    packet = ResearchEvidencePacket(packet_id="p1", ticker="AAPL", as_of=T, items=(item,), point_in_time_status=EvidencePointInTimeStatus.CERTIFIED_HISTORICAL_PIT)
    signal = GroundedResearchSignal(
        ticker="AAPL", as_of=T, direction="BULLISH", conviction=Decimal("0.82"), thesis="certified",
        cited_evidence_ids=("e1",),
    )
    certified = EvidenceAuthorizationService().authorize(
        signal, packet, provider_registry={"sec-edgar-accession-certified": ProviderCapabilities(
            provider_name="sec-edgar-accession-certified", supports_historical=True,
            supports_point_in_time=True, research_grade=True,
        )},
    )
    decision = fuse_production_decision(
        certified, run_id="run", quant_score=Decimal("0.2"), policy_hash="b" * 64,
    )
    assert decision.research_modifier != 0
    assert decision.final_alpha != decision.quant_only_alpha
    assert decision.combined_research_modifier == decision.research_modifier + decision.dislocation_modifier


def test_bundle_availability_is_maximum_input_availability() -> None:
    current = _fact(CanonicalMetric.REVENUE, "100", T + timedelta(hours=1), datetime(2026, 6, 30, tzinfo=UTC))
    prior = _fact(CanonicalMetric.REVENUE, "90", T, datetime(2025, 6, 30, tzinfo=UTC))
    snapshot = build_snapshot("AAPL", (current, prior), T + timedelta(days=2))
    series = snapshot.comparable_series[0]
    assert series.available_at == current.available_at
    item = snapshot_to_evidence_items(snapshot)[1]
    assert item.available_at == current.available_at


def test_security_manifest_sidecar_is_required_for_verified_loader() -> None:
    from meridian.identity_certification import load_verified_security_certificates

    path = Path(__file__).parents[1] / "reports" / "gate4f-security-master.json"
    master = load_verified_security_certificates(path)
    assert master.authoritative_count() == 11
